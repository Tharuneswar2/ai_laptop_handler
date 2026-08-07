"""
speech/provider.py — Abstract base class for speech-to-text providers.

All providers implement the same async interface so they can be swapped
without modifying the rest of the application.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


class TranscriptKind(Enum):
    """Type of transcript event."""
    PARTIAL = "partial"
    FINAL = "final"
    SPEECH_STARTED = "speech_started"
    SPEECH_ENDED = "speech_ended"
    ERROR = "error"


@dataclass
class TranscriptEvent:
    """A single transcript event from the speech provider."""
    kind: TranscriptKind
    text: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def is_final(self) -> bool:
        return self.kind == TranscriptKind.FINAL

    @property
    def is_partial(self) -> bool:
        return self.kind == TranscriptKind.PARTIAL

    def __str__(self) -> str:
        if self.kind == TranscriptKind.ERROR:
            return f"[ERROR] {self.error}"
        label = "partial" if self.is_partial else "final"
        return f"[{label}] {self.text}"


class SpeechProvider(ABC):
    """
    Abstract base class for speech-to-text providers.

    Subclasses must implement start(), stop(), and stream().
    The stream() method yields TranscriptEvent objects.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Initialize the provider and begin capturing audio."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the provider and release resources."""
        ...

    @abstractmethod
    async def stream(self) -> AsyncIterator[TranscriptEvent]:
        """
        Yield transcript events as they arrive.

        Yields:
            TranscriptEvent objects with kind=PARTIAL, FINAL, or ERROR.
        """
        ...

    async def health_check(self) -> bool:
        """Return True if the provider is healthy and connected."""
        return True


# ─── Provider Registry ───────────────────────────────────────────────

_provider: Optional[SpeechProvider] = None


def register_provider(provider: SpeechProvider) -> None:
    """Register the global speech provider."""
    global _provider
    _provider = provider
    logger.info("Speech provider registered: %s", provider.name)


def get_provider() -> Optional[SpeechProvider]:
    """Return the registered speech provider, or None."""
    return _provider
