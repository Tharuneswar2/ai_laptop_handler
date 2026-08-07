"""
speech/browser.py — Browser-based speech provider (default).

This provider does NOT do STT itself. It acts as a bridge between the
browser's Web Speech API and the server-side speech pipeline.

The browser handles STT via Web Speech API and sends transcripts over
WebSocket. This provider receives those transcripts and yields them
as TranscriptEvent objects.
"""

import asyncio
import logging
from typing import AsyncIterator, Optional

from speech.provider import SpeechProvider, TranscriptEvent, TranscriptKind

logger = logging.getLogger(__name__)


class BrowserSpeechProvider(SpeechProvider):
    """
    Browser-based speech provider.

    Receives transcripts from the browser via WebSocket and yields
    them as TranscriptEvent objects.

    This is the default provider that maintains backward compatibility
    with the existing browser STT pipeline.
    """

    def __init__(self):
        self._running = False
        self._event_queue: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        self._connected = False

    @property
    def name(self) -> str:
        return "Browser Web Speech API"

    async def start(self) -> None:
        """Start the browser provider (no-op, browser handles STT)."""
        self._running = True
        self._connected = True
        logger.info("Browser speech provider started (browser handles STT).")

    async def stop(self) -> None:
        """Stop the browser provider."""
        self._running = False
        self._connected = False
        logger.info("Browser speech provider stopped.")

    async def stream(self) -> AsyncIterator[TranscriptEvent]:
        """
        Yield transcript events received from the browser.

        Transcripts are pushed to the queue via push_transcript().
        """
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )
                yield event
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def push_transcript(self, text: str, is_final: bool = True, confidence: float = 1.0) -> None:
        """
        Push a transcript from the browser into the provider queue.

        Called by the WebSocket handler when a browser transcript arrives.
        """
        kind = TranscriptKind.FINAL if is_final else TranscriptKind.PARTIAL
        event = TranscriptEvent(
            kind=kind,
            text=text.strip(),
            confidence=confidence,
        )
        await self._event_queue.put(event)
        logger.debug("Browser transcript pushed: [%s] %s", kind.value, text[:50])

    async def health_check(self) -> bool:
        return self._connected


# ─── Singleton ────────────────────────────────────────────────────────

_browser_provider: Optional[BrowserSpeechProvider] = None


def get_browser_provider() -> BrowserSpeechProvider:
    """Return the singleton browser speech provider."""
    global _browser_provider
    if _browser_provider is None:
        _browser_provider = BrowserSpeechProvider()
    return _browser_provider
