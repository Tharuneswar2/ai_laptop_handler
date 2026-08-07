"""
voice/listener.py — Speech-to-text abstraction layer.

Speech recognition is handled by the browser Web Speech API (STT_PROVIDER="browser").
Transcripts arrive real-time via WebSockets at the API server endpoint (/ws).
"""

import logging

logger = logging.getLogger(__name__)


def get_stt_provider() -> str:
    """Return the configured STT provider name."""
    import config
    return config.STT_PROVIDER


def is_browser_stt() -> bool:
    """Check if the current STT provider is browser-based."""
    return get_stt_provider() == "browser"


def listen_browser() -> str:
    """
    Placeholder for browser STT mode.

    Speech recognition is handled entirely by the browser's Web Speech API.
    Text arrives via WebSocket to the API server.
    """
    logger.info("Browser STT mode active — transcription handled by the browser.")
    return ""


def listen() -> str:
    """Listen placeholder for STT provider."""
    return listen_browser()


def listen_smart() -> str:
    """Smart listen placeholder for STT provider."""
    return listen_browser()

