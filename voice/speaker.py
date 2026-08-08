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

    On Windows, uses PowerShell System.Speech in a subprocess (base voice),
    which is reliable from any thread. Falls back to pyttsx3 and then
    native OS speech tools on other platforms.
    """
    if not text:
        return

    text_clean = text.replace("*", "").replace("`", "").strip()
    if not text_clean:
        return

    # 1. Windows: PowerShell System.Speech subprocess (base/default voice)
    if sys.platform == "win32":
        try:
            import subprocess
            logger.info("Speaking (PowerShell SAPI): '%s'", text_clean[:80])
            safe_text = text_clean.replace("'", "''")
            ps_script = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate = 2; "
                f"$s.Speak('{safe_text}'); "
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                check=False,
                timeout=30,
            )
            logger.debug("Speech complete.")
            return
        except Exception as exc:
            logger.warning("PowerShell SAPI TTS failed: %s", exc)

    # 2. Try pyttsx3 engine
    try:
        engine = _get_thread_engine()
        if engine is not None:
            logger.info("Speaking (pyttsx3): '%s'", text_clean[:80])
            engine.say(text_clean)
            engine.runAndWait()
            logger.debug("Speech complete.")
            return
    except Exception as e:
        logger.debug("pyttsx3 TTS unavailable (%s), trying native OS fallback...", e)

    # 3. Other platform fallbacks (Linux: spd-say / espeak, macOS: say)
    import shutil
    import subprocess

    if sys.platform.startswith("linux"):
        if shutil.which("spd-say"):
            try:
                logger.info("Speaking (spd-say): '%s'", text_clean[:80])
                subprocess.run(["spd-say", "-t", "female1", "-r", "5", text_clean], check=False)
                return
            except Exception as exc:
                logger.warning("spd-say failed: %s", exc)
        elif shutil.which("espeak-ng"):
            try:
                logger.info("Speaking (espeak-ng): '%s'", text_clean[:80])
                subprocess.run(["espeak-ng", text_clean], check=False)
                return
            except Exception as exc:
                logger.warning("espeak-ng failed: %s", exc)
        elif shutil.which("espeak"):
            try:
                logger.info("Speaking (espeak): '%s'", text_clean[:80])
                subprocess.run(["espeak", text_clean], check=False)
                return
            except Exception as exc:
                logger.warning("espeak failed: %s", exc)

    elif sys.platform == "darwin":
        if shutil.which("say"):
            try:
                logger.info("Speaking (say): '%s'", text_clean[:80])
                subprocess.run(["say", text_clean], check=False)
                return
            except Exception as exc:
                logger.warning("macOS say failed: %s", exc)

    logger.warning("No working TTS engine available for text: %s", text_clean)


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
