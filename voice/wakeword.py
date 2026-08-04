"""
voice/wakeword.py — Wake word detection.

Listens in short windows and checks if the transcribed text contains
one of the configured wake words (e.g., "hey nova", "hey assistant").

Uses the same Whisper model as the main listener to avoid loading
a separate model. Can be replaced with openwakeword or Porcupine later.
"""

import logging
import time

logger = logging.getLogger(__name__)


def detect_wake_word(timeout: float = None) -> bool:
    """
    Listen continuously until a wake word is detected or timeout expires.

    Args:
        timeout: Maximum seconds to wait for wake word. None = wait forever.

    Returns:
        True if wake word was detected, False if timeout expired.
    """
    import config
    from voice.listener import record_audio, transcribe

    wake_words = config.WAKE_WORDS
    duration = config.WAKE_LISTEN_DURATION

    logger.info("Waiting for wake word: %s", wake_words)
    start_time = time.time()

    while True:
        # Check timeout
        if timeout is not None and (time.time() - start_time) > timeout:
            logger.info("Wake word detection timed out after %.1fs.", timeout)
            return False

        try:
            audio = record_audio(duration=duration, sample_rate=config.SAMPLE_RATE)
            text = transcribe(audio).lower().strip()

            if not text:
                continue

            logger.debug("Wake check heard: '%s'", text)

            for wake_word in wake_words:
                if wake_word in text:
                    logger.info("Wake word detected: '%s' in '%s'", wake_word, text)
                    return True

        except KeyboardInterrupt:
            logger.info("Wake word detection interrupted by user.")
            return False
        except Exception as e:
            logger.error("Wake word detection error: %s", e)
            time.sleep(0.5)  # brief pause before retrying


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
