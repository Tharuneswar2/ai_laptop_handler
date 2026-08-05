"""
voice/listener.py — Microphone input and speech-to-text using faster-whisper.

Records audio from the microphone, transcribes it using Whisper Tiny,
and returns clean text. Handles silence detection and errors gracefully.
"""

import logging
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _get_model():
    """Lazily load the Whisper model (downloads ~75 MB on first run)."""
    from faster_whisper import WhisperModel
    import config

    logger.info("Loading Whisper '%s' model (device=%s)...", config.WHISPER_MODEL, config.WHISPER_DEVICE)
    model = WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
    )
    logger.info("Whisper model loaded successfully.")
    return model


# Singleton — loaded once, reused across calls
_model = None


def get_model():
    """Return the singleton Whisper model instance."""
    global _model
    if _model is None:
        _model = _get_model()
    return _model


def record_audio(duration: float = 5.0, sample_rate: int = 16000) -> np.ndarray:
    """
    Record audio from the default microphone.

    Args:
        duration: Recording length in seconds.
        sample_rate: Sample rate in Hz (Whisper expects 16000).

    Returns:
        NumPy array of audio samples (mono, float32).
    """
    import sounddevice as sd

    logger.info("Recording for %.1f seconds...", duration)
    try:
        audio = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()  # block until recording is done
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
) -> np.ndarray:
    """
    Record audio until silence is detected or max duration is reached.

    Args:
        max_duration: Maximum recording time in seconds.
        silence_threshold: RMS amplitude below which audio is 'silence'.
        silence_duration: Seconds of continuous silence before stopping.
        sample_rate: Sample rate in Hz.
        chunk_size: Size of each recording chunk in seconds.

    Returns:
        NumPy array of recorded audio.
    """
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

            # Check if this chunk is silent
            rms = np.sqrt(np.mean(chunk ** 2)) * 32768  # scale to int16 range
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


def transcribe(audio: np.ndarray) -> str:
    """
    Transcribe audio to text using faster-whisper.

    Args:
        audio: NumPy array of audio samples (mono, float32, 16kHz).

    Returns:
        Transcribed text string, or empty string on failure.
    """
    if audio.size == 0:
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
    One-shot: record from microphone and transcribe to text.

    Args:
        duration: Recording duration in seconds. Uses config default if None.

    Returns:
        Transcribed text string.
    """
    import config

    if duration is None:
        duration = config.LISTEN_DURATION

    audio = record_audio(duration=duration, sample_rate=config.SAMPLE_RATE)
    return transcribe(audio)


def listen_smart() -> str:
    """
    Record with automatic silence detection and transcribe.

    Returns:
        Transcribed text string.
    """
    import config

    audio = record_until_silence(
        max_duration=config.LISTEN_MAX_DURATION,
        silence_threshold=config.SILENCE_THRESHOLD,
        sample_rate=config.SAMPLE_RATE,
    )
    return transcribe(audio)
