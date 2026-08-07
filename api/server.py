"""
api/server.py — FastAPI server with REST API + WebSocket + static file serving.

Endpoints:
  GET  /           — serves web UI (index.html)
  GET  /static/*   — serves CSS/JS assets
  WS   /ws         — WebSocket for real-time voice interaction
  POST /command    — REST: accept text command, return result
  GET  /history    — REST: return command history
  GET  /status     — REST: health check
"""

import json
import logging
import time
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from brain.intent_parser import parse_intent
from brain.memory import Memory
from conversation.conversation import get_conversation_engine
from router.tool_router import route
from voice.wakeword import check_text_for_wake_word

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Laptop Handler API",
    description="Voice-controlled laptop assistant — API + WebSocket interface",
    version="2.0.0",
)

# ─── Command Observers ────────────────────────────────────────────────
# External components can subscribe to assistant events without the server
# knowing about them. Observers are called with plain dicts from the uvicorn
# thread, so they must be thread-safe.

_observers: list[Callable[[dict[str, Any]], None]] = []


def add_command_observer(observer: Callable[[dict[str, Any]], None]) -> None:
    """
    Register a callback receiving assistant pipeline events.

    Event dicts (``type`` key):
      ``transcript``    — a final transcript arrived  {"text": ...}
      ``wake_detected`` — the wake word was heard
      ``processing``    — a command is being routed      {"text": ...}
      ``result``        — a command finished             {"success", "message", "tool", "action", "duration_ms"}
      ``error``         — something failed               {"message": ...}
    """
    _observers.append(observer)


def _emit(event: dict[str, Any]) -> None:
    for observer in _observers:
        try:
            observer(event)
        except Exception:
            logger.exception("Command observer failed: %s", event.get("type"))

# ─── Static Files ─────────────────────────────────────────────────────

# Mount static files (CSS, JS) for the web UI
app.mount("/static", StaticFiles(directory=str(config.WEB_UI_DIR)), name="static")


# ─── REST Models ──────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    """Request body for the /command endpoint."""
    text: str


class CommandResponse(BaseModel):
    """Response from the /command endpoint."""
    success: bool
    tool: str
    action: str
    message: str
    duration_ms: int


# ─── Web UI Route ─────────────────────────────────────────────────────

@app.get("/")
def serve_ui():
    """Serve the web voice interface."""
    index_path = config.WEB_UI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {"error": "Web UI not found. Ensure ui/web/index.html exists."}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Return 204 No Content for favicon requests to avoid 404 logs."""
    return Response(status_code=204)


# ─── REST Endpoints (unchanged from v1) ──────────────────────────────

@app.get("/status")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "ai-laptop-handler",
        "version": "2.0.0",
        "stt_provider": config.STT_PROVIDER,
    }


@app.post("/command", response_model=CommandResponse)
def run_command(request: CommandRequest):
    """Accept a text command, parse intent, route to tool, return result."""
    start = time.time()

    # Validate input
    text = request.text.strip()[:config.WS_MAX_TEXT_LENGTH]
    if not text:
        return CommandResponse(
            success=False, tool="", action="", message="Empty command.", duration_ms=0
        )

    # Strip wake word if present
    _, clean_text = check_text_for_wake_word(text)
    if clean_text:
        text = clean_text

    _emit({"type": "processing", "text": text})
    parsed = parse_intent(text)

    from planner.task import ExecutionPlan
    if isinstance(parsed, ExecutionPlan):
        from planner.executor import execute_plan
        result = execute_plan(parsed)
        duration_ms = int((time.time() - start) * 1000)

        _emit({
            "type": "result",
            "success": result.success,
            "message": result.message,
            "tool": "planner",
            "action": "execute_plan",
            "duration_ms": duration_ms,
        })

        return CommandResponse(
            success=result.success,
            tool="planner",
            action="execute_plan",
            message=result.message,
            duration_ms=duration_ms,
        )

    intent = parsed
    result = route(intent)
    duration_ms = int((time.time() - start) * 1000)

    # Log to memory
    try:
        memory = Memory()
        memory.add(
            user_text=text,
            intent=f"{intent.tool}.{intent.action}",
            result=result.message,
            status="ok" if result.success else "error",
            duration_ms=duration_ms,
        )
    except Exception as e:
        logger.error("Failed to log to memory: %s", e)

    _emit({
        "type": "result",
        "success": result.success,
        "message": result.message,
        "tool": intent.tool,
        "action": intent.action,
        "duration_ms": duration_ms,
    })

    return CommandResponse(
        success=result.success,
        tool=intent.tool,
        action=intent.action,
        message=result.message,
        duration_ms=duration_ms,
    )


@app.get("/history")
def get_history(limit: int = 50):
    """Get command history."""
    try:
        memory = Memory()
        history = memory.get_history(limit=limit)
        return {"history": history}
    except Exception as e:
        logger.error("Failed to fetch history: %s", e)
        return {"history": [], "error": str(e)}


# ─── WebSocket Endpoint ──────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket for real-time voice interaction.

    Protocol:
      Client → Server: {"type": "transcript", "text": "...", "is_final": true}
      Server → Client: {"type": "result", "success": bool, "tool": str, ...}
                        {"type": "wake_detected"}
                        {"type": "waiting_wake"}
                        {"type": "error", "message": str}
    """
    await ws.accept()
    logger.info("WebSocket client connected.")

    # Per-connection state
    wake_active = False  # Has the user said the wake word?
    memory = Memory()

    try:
        # Send initial state
        await ws.send_json({
            "type": "waiting_wake",
            "message": 'Say "Hey Nova" to activate.',
        })

        while True:
            # Receive message from browser
            raw = await ws.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid message format."})
                continue

            msg_type = data.get("type", "")
            text = data.get("text", "").strip()

            if msg_type != "transcript" or not text:
                continue

            # Validate: limit text length
            text = text[:config.WS_MAX_TEXT_LENGTH]
            logger.info("WS received: '%s' (wake_active=%s)", text[:80], wake_active)

            _emit({"type": "transcript", "text": text})

            # Check for wake word
            has_wake, remaining = check_text_for_wake_word(text)

            if has_wake:
                wake_active = True
                logger.info("Wake word detected in: '%s'", text)
                _emit({"type": "wake_detected"})
                await ws.send_json({"type": "wake_detected"})

                # If there's a command after the wake word, process it immediately
                if remaining.strip():
                    text = remaining.strip()
                else:
                    # Wake word only — wait for next command
                    await ws.send_json({
                        "type": "info",
                        "message": "Listening for your command...",
                    })
                    continue

            elif not wake_active:
                # No wake word yet — keep waiting
                await ws.send_json({
                    "type": "waiting_wake",
                    "message": 'Say "Hey Nova" to activate.',
                })
                continue

            # ─── Process command via conversation engine ───────────
            start = time.time()

            _emit({"type": "processing", "text": text})

            conversation = get_conversation_engine()
            response_text, result = conversation.process(text)

            duration_ms = int((time.time() - start) * 1000)

            success = result.success if result else True
            tool = result.data.get("tool", "conversation") if result and result.data else "conversation"
            action = result.data.get("action", "process") if result and result.data else "process"

            # Log to memory
            memory.add(
                user_text=text,
                intent=f"{tool}.{action}",
                result=response_text,
                status="ok" if success else "error",
                duration_ms=duration_ms,
            )

            _emit({
                "type": "result",
                "success": success,
                "message": response_text,
                "tool": tool,
                "action": action,
                "duration_ms": duration_ms,
            })

            # Send conversational response back to browser
            await ws.send_json({
                "type": "result",
                "success": success,
                "tool": tool,
                "action": action,
                "message": response_text,
                "original_text": text,
                "duration_ms": duration_ms,
                "speak": response_text[:200],
            })

            logger.info(
                "WS command: '%s' → %s (%dms) [%s]",
                text[:40], "ok" if success else "error", duration_ms,
                conversation.get_state().get("current_task", ""),
            )

            # Reset wake state — require wake word again for next command
            wake_active = False

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
        _emit({"type": "error", "message": str(e)})
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ─── Server Startup ──────────────────────────────────────────────────

def _open_browser_background(url: str) -> None:
    """Open browser in background after a short delay."""
    import threading
    import webbrowser

    def _delayed_open():
        import time
        time.sleep(2)  # Wait for server to be ready
        try:
            webbrowser.open(url)
            logger.info("Browser opened: %s", url)
        except Exception as e:
            logger.warning("Failed to open browser: %s", e)

    thread = threading.Thread(target=_delayed_open, daemon=True)
    thread.start()


def start_server():
    """Start the API server."""
    import uvicorn

    url = f"http://{config.API_HOST}:{config.API_PORT}"
    logger.info("Starting API server on %s:%d", config.API_HOST, config.API_PORT)
    logger.info("Web UI: %s", url)
    logger.info("API docs: %s/docs", url)

    # Auto-launch browser in background
    _open_browser_background(url)

    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="warning")


if __name__ == "__main__":
    start_server()
