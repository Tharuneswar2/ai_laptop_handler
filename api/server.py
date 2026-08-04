"""
api/server.py — Minimal FastAPI server for programmatic access.

Endpoints:
  POST /command  — accept text command, return result
  GET  /history  — return command history
  GET  /status   — health check
"""

import logging
import time
from fastapi import FastAPI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Laptop Handler API",
    description="Voice-controlled laptop assistant — API interface",
    version="1.0.0",
)


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


@app.get("/status")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "ai-laptop-handler", "version": "1.0.0"}


@app.post("/command", response_model=CommandResponse)
def run_command(request: CommandRequest):
    """
    Accept a text command, parse intent, route to tool, return result.
    """
    from brain.intent_parser import parse_intent
    from router.tool_router import route

    start = time.time()

    # Parse intent
    intent = parse_intent(request.text)

    # Route to tool
    result = route(intent)

    duration_ms = int((time.time() - start) * 1000)

    # Log to memory
    try:
        from brain.memory import Memory
        memory = Memory()
        memory.add(
            user_text=request.text,
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
        from brain.memory import Memory
        memory = Memory()
        history = memory.get_history(limit=limit)
        return {"history": history}
    except Exception as e:
        logger.error("Failed to fetch history: %s", e)
        return {"history": [], "error": str(e)}


def start_server():
    """Start the API server."""
    import config
    import uvicorn

    logger.info("Starting API server on %s:%d", config.API_HOST, config.API_PORT)
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="info")


if __name__ == "__main__":
    start_server()
