"""
voice/listener.py — Speech-to-text abstraction layer.

Supports multiple STT providers:
  - "browser":        Web Speech API (handled entirely in the browser)
  - "whisper_local":  faster-whisper running locally (needs pip install)

When STT_PROVIDER is "browser", the mic/transcription is handled by
the browser's Web Speech API and sent to the backend via WebSocket.
This module is only used directly in "whisper_local" mode.
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


# ─── Browser STT (no-op — handled in browser) ────────────────────────

def listen_browser() -> str:
    """
    Placeholder for browser STT mode.

    In browser mode, speech recognition is handled entirely by the
    browser's Web Speech API. This function is never called directly;
    text arrives via WebSocket to the API server.
    """
    logger.info("Browser STT mode — transcription is handled by the browser.")
    return ""


# ─── Whisper Local STT (optional) ────────────────────────────────────

_model = None


def _get_whisper_model():
    """Lazily load the Whisper model (downloads on first run)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "faster-whisper is not installed. To use local Whisper STT, run:\n"
            "  pip install faster-whisper sounddevice scipy\n"
            "Then set STT_PROVIDER=whisper_local in your .env file."
        )

    import config
    logger.info("Loading Whisper '%s' model (device=%s)...", config.WHISPER_MODEL, config.WHISPER_DEVICE)
    model = WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
    )
    logger.info("Whisper model loaded successfully.")
    return model


def get_model():
    """Return the singleton Whisper model instance."""
    global _model
    if _model is None:
        _model = _get_whisper_model()
    return _model


def record_audio(duration: float = 5.0, sample_rate: int = 16000):
    """Record audio from the default microphone."""
    import numpy as np
    import sounddevice as sd

    logger.info("Recording for %.1f seconds...", duration)
    try:
        audio = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        logger.info("Recording complete.")
        return audio.flatten()
    except Exception as e:
        logger.error("Microphone recording failed: %s", e)
        return np.array([], dtype="float32")


def record_until_silence(
    max_duration: float = 10.0,
    silence_threshold: float = 500,
    silence_duration: float = 1.5,
    sample_rate: int = 16000,
    chunk_size: float = 0.5,
):
    """Record audio until silence is detected or max duration is reached."""
    import numpy as np
    import sounddevice as sd

    logger.info("Recording (auto-stop on silence, max %.1fs)...", max_duration)
    chunks = []
    silent_chunks = 0
    chunks_for_silence = int(silence_duration / chunk_size)

    try:
        for _ in range(int(max_duration / chunk_size)):
            chunk = sd.rec(
                int(chunk_size * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            chunk = chunk.flatten()
            chunks.append(chunk)

            rms = np.sqrt(np.mean(chunk ** 2)) * 32768
            if rms < silence_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= chunks_for_silence and len(chunks) > chunks_for_silence:
                logger.info("Silence detected, stopping recording.")
                break

        if chunks:
            return np.concatenate(chunks)
        return np.array([], dtype="float32")
    except Exception as e:
        logger.error("Recording with silence detection failed: %s", e)
        return np.array([], dtype="float32")


def transcribe(audio) -> str:
    """Transcribe audio to text using faster-whisper."""
    import numpy as np

    if not isinstance(audio, np.ndarray) or audio.size == 0:
        logger.warning("Empty audio, nothing to transcribe.")
        return ""

    model = get_model()
    try:
        segments, info = model.transcribe(audio, beam_size=1, language="en")
        text = " ".join(segment.text.strip() for segment in segments).strip()
        logger.info("Transcribed: '%s' (language=%s, prob=%.2f)", text, info.language, info.language_probability)
        return text
    except Exception as e:
        logger.error("Transcription failed: %s", e)
        return ""


def listen(duration: float = None) -> str:
    """
    Record from microphone and transcribe to text.

    In browser mode, returns empty (transcription handled by browser).
    In whisper_local mode, records and transcribes locally.
    """
    import config

    if is_browser_stt():
        return listen_browser()

    if duration is None:
        duration = config.LISTEN_DURATION
    audio = record_audio(duration=duration, sample_rate=config.SAMPLE_RATE)
    return transcribe(audio)


def listen_smart() -> str:
    """
    Record with automatic silence detection and transcribe.

    In browser mode, returns empty (transcription handled by browser).
    """
    import config

    if is_browser_stt():
        return listen_browser()

    audio = record_until_silence(
        max_duration=config.LISTEN_MAX_DURATION,
        silence_threshold=config.SILENCE_THRESHOLD,
        sample_rate=config.SAMPLE_RATE,
    )
    return transcribe(audio)
