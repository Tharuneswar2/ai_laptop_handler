"""
voice/speaker.py — Text-to-speech output.

Converts text responses to spoken audio using pyttsx3 (offline, zero-setup).
Designed with a clean interface so the TTS engine can be swapped to
Piper or Kokoro later without changing calling code.
"""

import logging
import sys
import threading

logger = logging.getLogger(__name__)


def _init_engine():
    """Initialize a fresh pyttsx3 engine (must be called per-thread on Windows)."""
    import pyttsx3
    import config

    # On Windows, SAPI5 requires COM initialized in the calling thread
    if sys.platform == "win32":
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

    engine = pyttsx3.init()
    engine.setProperty("rate", config.TTS_RATE)
    engine.setProperty("volume", config.TTS_VOLUME)

    # Pick Zira voice (US English female) if available
    voices = engine.getProperty("voices")
    if voices:
        selected = voices[0].id
        for v in voices:
            if "zira" in v.name.lower():
                selected = v.id
                break
        engine.setProperty("voice", selected)

    return engine


# Per-thread engines (pyttsx3 is not thread-safe)
_thread_local = threading.local()


def _get_thread_engine():
    """Get or create a pyttsx3 engine for the current thread."""
    engine = getattr(_thread_local, "engine", None)
    if engine is None:
        engine = _init_engine()
        _thread_local.engine = engine
        logger.info("TTS engine initialized for thread %s.", threading.current_thread().name)
    return engine


def speak(text: str) -> None:
    """
    Speak the given text aloud.

    Args:
        text: The text to convert to speech and play.
    """
    if not text:
        return

    try:
        engine = _get_thread_engine()
        logger.info("Speaking: '%s'", text[:80])
        engine.say(text)
        engine.runAndWait()
        logger.debug("Speech complete.")
    except Exception as e:
        logger.error("TTS playback failed: %s", e)


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
    try:
        engine = _get_thread_engine()
        engine.setProperty("rate", rate)
        logger.info("TTS rate set to %d WPM.", rate)
    except Exception as e:
        logger.error("Failed to set TTS rate: %s", e)


def set_volume(volume: float) -> None:
    """Change the speech volume (0.0 to 1.0)."""
    try:
        engine = _get_thread_engine()
        volume = max(0.0, min(1.0, volume))
        engine.setProperty("volume", volume)
        logger.info("TTS volume set to %.1f.", volume)
    except Exception as e:
        logger.error("Failed to set TTS volume: %s", e)
