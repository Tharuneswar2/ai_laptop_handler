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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from brain.intent_parser import parse_intent
from brain.memory import Memory
from router.tool_router import route
from voice.wakeword import check_text_for_wake_word

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Laptop Handler API",
    description="Voice-controlled laptop assistant — API + WebSocket interface",
    version="2.0.0",
)

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

    intent = parse_intent(text)
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
    # The browser microphone button activates listening by default. Wake-word
    # mode can be enabled through BROWSER_REQUIRE_WAKE_WORD.
    wake_active = not config.BROWSER_REQUIRE_WAKE_WORD
    memory = Memory()

    try:
        # Send initial state
        await ws.send_json({
            "type": "waiting_wake",
            "message": 'Tap to activate.',
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

            # Check for wake word
            has_wake, remaining = check_text_for_wake_word(text)

            if config.BROWSER_REQUIRE_WAKE_WORD and has_wake:
                prompt_msg = "Yes Boss, tell me Boss." if wake_active else "Yes Boss, waiting for your instruction."
                wake_active = True
                logger.info("Wake word detected in: '%s'", text)
                await ws.send_json({"type": "wake_detected", "speak": prompt_msg})

                # If there's a command after the wake word, process it immediately
                if remaining.strip():
                    text = remaining.strip()
                else:
                    # Wake word only — wait for next command
                    await ws.send_json({
                        "type": "info",
                        "message": "Listening for your command...",
                        "speak": prompt_msg,
                    })
                    continue

            elif config.BROWSER_REQUIRE_WAKE_WORD and not wake_active:
                # No wake word yet — keep waiting
                await ws.send_json({
                    "type": "waiting_wake",
                    "message": 'Tap to activate.',
                })
                continue

            # Check for explicit sleep/exit commands
            SLEEP_COMMANDS = {"sleep", "exit", "goodbye", "stop listening", "stop", "turn off", "go to sleep"}
            if text.strip().lower() in SLEEP_COMMANDS:
                wake_active = False
                await ws.send_json({
                    "type": "result",
                    "success": True,
                    "tool": "system",
                    "action": "sleep",
                    "message": "Okay Boss, going to sleep.",
                    "original_text": text,
                    "duration_ms": 0,
                    "speak": "Okay Boss, going to sleep.",
                })
                await ws.send_json({
                    "type": "waiting_wake",
                    "message": 'Tap to activate.',
                })
                continue

            # ─── Process command ──────────────────────────────────
            start = time.time()

            intent = parse_intent(text)
            result = route(intent)
            duration_ms = int((time.time() - start) * 1000)

            # Log to memory
            memory.add(
                user_text=text,
                intent=f"{intent.tool}.{intent.action}",
                result=result.message,
                status="ok" if result.success else "error",
                duration_ms=duration_ms,
            )

            # Send result back to browser
            await ws.send_json({
                "type": "result",
                "success": result.success,
                "tool": intent.tool,
                "action": intent.action,
                "message": result.message,
                "original_text": text,
                "duration_ms": duration_ms,
                "speak": result.message[:200] if result.message else ("Done Boss." if result.success else "Failed Boss."),
            })

            logger.info(
                "WS command: '%s' → %s.%s → %s (%dms)",
                text[:40], intent.tool, intent.action,
                "ok" if result.success else "error", duration_ms,
            )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ─── Server Startup ──────────────────────────────────────────────────

def start_server():
    """Start the API server."""
    import uvicorn

    logger.info("Starting API server on %s:%d", config.API_HOST, config.API_PORT)
    logger.info("Web UI: http://%s:%d", config.API_HOST, config.API_PORT)
    logger.info("API docs: http://%s:%d/docs", config.API_HOST, config.API_PORT)
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="info")


if __name__ == "__main__":
    start_server()
