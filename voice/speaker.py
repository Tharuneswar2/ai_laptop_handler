"""
voice/speaker.py — Text-to-speech output.

Converts text responses to spoken audio using pyttsx3 (offline, zero-setup).
Designed with a clean interface so the TTS engine can be swapped to
Piper or Kokoro later without changing calling code.
"""

import logging

logger = logging.getLogger(__name__)

# Singleton engine
_engine = None


def _get_engine():
    """Initialize and configure the pyttsx3 engine."""
    import pyttsx3
    import config

    engine = pyttsx3.init()
    engine.setProperty("rate", config.TTS_RATE)
    engine.setProperty("volume", config.TTS_VOLUME)

    # Try to pick a pleasant voice (prefer female if available)
    voices = engine.getProperty("voices")
    if voices and len(voices) > 1:
        engine.setProperty("voice", voices[1].id)  # often female on Linux
    elif voices:
        engine.setProperty("voice", voices[0].id)

    return engine


def get_engine():
    """Return the singleton TTS engine."""
    global _engine
    if _engine is None:
        try:
            _engine = _get_engine()
            logger.info("TTS engine initialized (pyttsx3).")
        except Exception as e:
            logger.error("Failed to initialize TTS engine: %s", e)
            _engine = None
    return _engine


def speak(text: str) -> None:
    """
    Speak the given text aloud.

    Args:
        text: The text to convert to speech and play.
    """
    if not text:
        return

    engine = get_engine()
    if engine is None:
        logger.warning("TTS engine unavailable. Response: %s", text)
        print(f"[TTS unavailable] {text}")
        return

    try:
        logger.info("Speaking: '%s'", text[:80])
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        logger.error("TTS playback failed: %s", e)
        print(f"[TTS error] {text}")


def speak_async(text: str) -> None:
    """
    Speak text without blocking (starts playback and returns).

    Note: pyttsx3 doesn't natively support non-blocking well.
    This is a placeholder for future async TTS (e.g., Piper).
    Currently behaves the same as speak().
    """
    speak(text)


def set_rate(rate: int) -> None:
    """Change the speech rate (words per minute)."""
    engine = get_engine()
    if engine:
        engine.setProperty("rate", rate)
        logger.info("TTS rate set to %d WPM.", rate)


def set_volume(volume: float) -> None:
    """Change the speech volume (0.0 to 1.0)."""
    engine = get_engine()
    if engine:
        volume = max(0.0, min(1.0, volume))
        engine.setProperty("volume", volume)
        logger.info("TTS volume set to %.1f.", volume)
