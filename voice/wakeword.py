"""
voice/wakeword.py — Wake word detection and text prefix parser.

Checks if incoming transcript text contains configured wake words
(e.g., "hey nova", "hey assistant") and extracts the remaining command.
"""

import logging

logger = logging.getLogger(__name__)


def check_text_for_wake_word(text: str) -> tuple[bool, str]:
    """
    Check if text contains a wake word and return the remaining command.

    Args:
        text: The transcribed text to check.

    Returns:
        Tuple of (wake_word_found, remaining_text_after_wake_word).
    """
    import config

    text_lower = text.lower().strip()

    for wake_word in config.WAKE_WORDS:
        if wake_word in text_lower:
            # Extract the part after the wake word
            idx = text_lower.index(wake_word) + len(wake_word)
            remaining = text[idx:].strip().lstrip(",").lstrip(".").strip()
            return True, remaining

    return False, text

