"""
speech/wakeword.py — Wake word detection for server-side speech providers.

Detects wake words in transcript text and extracts commands.
This is the server-side equivalent of voice/wakeword.py.
"""

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Default wake words
DEFAULT_WAKE_WORDS = ["hey nova", "nova", "hey assistant", "innova", "hey innova"]


class WakeWordDetector:
    """
    Detects wake words in transcript text.

    Maintains state to handle split utterances:
    - "Hey Nova" → wake detected, wait for command
    - "Hey Nova open VS Code" → wake + command in one utterance
    """

    def __init__(self, wake_words: list = None, enabled: bool = True):
        self.wake_words = [w.lower() for w in (wake_words or DEFAULT_WAKE_WORDS)]
        self.enabled = enabled
        self._wake_active = False

    def reset(self) -> None:
        """Reset wake word state."""
        self._wake_active = False

    @property
    def is_wake_active(self) -> bool:
        """Whether the assistant is currently listening for a command."""
        return self._wake_active

    def check(self, text: str) -> Tuple[bool, str]:
        """
        Check if text contains a wake word and extract the command.

        Args:
            text: The transcript text to check.

        Returns:
            Tuple of (wake_detected, remaining_command_text).
        """
        if not self.enabled:
            return True, text

        text_lower = text.lower().strip()

        # Check each wake word
        for wake in self.wake_words:
            if wake in text_lower:
                # Remove wake word from text
                remaining = re.sub(re.escape(wake), "", text, flags=re.IGNORECASE).strip()
                self._wake_active = True
                logger.info("Wake word detected: '%s'", wake)
                return True, remaining

        # If wake is already active, treat this as a command
        if self._wake_active:
            return False, text

        return False, ""

    def consume_wake(self) -> None:
        """Mark that the wake state has been consumed (command received)."""
        self._wake_active = False
