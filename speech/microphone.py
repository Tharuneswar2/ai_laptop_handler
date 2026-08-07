"""
speech/microphone.py — Async microphone audio capture.

Captures audio from the system microphone as 16 kHz, 16-bit PCM, mono.
Yields chunks suitable for streaming to speech providers.
"""

import asyncio
import io
import logging
import struct
import threading
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)

# Lazy import pyaudio
_pyaudio = None


def _ensure_pyaudio():
    global _pyaudio
    if _pyaudio is None:
        try:
            import pyaudio
            _pyaudio = pyaudio
        except ImportError:
            raise ImportError(
                "PyAudio is required for microphone capture. "
                "Install with: pip install pyaudio"
            )
    return _pyaudio


class MicrophoneStream:
    """
    Async microphone stream that yields raw audio chunks.

    Format: 16 kHz, 16-bit PCM, mono.
    Each chunk is approximately 100ms (1600 samples × 2 bytes = 3200 bytes).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration_ms: int = 100,
        device_index: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration_ms = chunk_duration_ms
        self.device_index = device_index

        self._pa = None
        self._stream = None
        self._audio = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def _calculate_chunk_size(self) -> int:
        """Calculate the number of frames per chunk."""
        return int(self.sample_rate * self.chunk_duration_ms / 1000)

    async def start(self) -> None:
        """Open the microphone stream."""
        if self._running:
            return

        pa = _ensure_pyaudio()
        self._pa = pa.PyAudio()

        chunk_size = self._calculate_chunk_size()

        try:
            self._stream = self._pa.open(
                format=pa.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=chunk_size,
                input_device_index=self.device_index,
            )
            self._running = True
            self._loop = asyncio.get_event_loop()
            logger.info(
                "Microphone opened (rate=%d, channels=%d, chunk=%d frames)",
                self.sample_rate, self.channels, chunk_size,
            )
        except Exception as e:
            logger.error("Failed to open microphone: %s", e)
            if self._pa:
                self._pa.terminate()
                self._pa = None
            raise

    async def stop(self) -> None:
        """Close the microphone stream."""
        self._running = False
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
        logger.info("Microphone closed.")

    async def read_chunk(self) -> bytes:
        """
        Read a single audio chunk from the microphone.

        Returns:
            Raw audio bytes (16-bit PCM).
        """
        if not self._stream or not self._running:
            raise RuntimeError("Microphone not started.")

        chunk_size = self._calculate_chunk_size()

        # Run blocking read in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: self._stream.read(chunk_size, exception_on_overflow=False)
        )
        return data

    async def chunks(self) -> AsyncIterator[bytes]:
        """Yield audio chunks continuously until stopped."""
        while self._running:
            try:
                chunk = await self.read_chunk()
                yield chunk
            except Exception as e:
                if self._running:
                    logger.warning("Microphone read error: %s", e)
                    await asyncio.sleep(0.1)
                else:
                    break

    def get_audio_level(self, chunk: bytes) -> float:
        """
        Calculate the RMS audio level of a chunk.

        Returns:
            Float between 0.0 (silence) and 1.0 (max volume).
        """
        if not chunk:
            return 0.0

        # Unpack 16-bit PCM samples
        samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
        if not samples:
            return 0.0

        # Calculate RMS
        sum_squares = sum(s * s for s in samples)
        rms = (sum_squares / len(samples)) ** 0.5

        # Normalize to 0.0-1.0 (max 16-bit value is 32768)
        return min(rms / 32768.0, 1.0)


# ─── Singleton ────────────────────────────────────────────────────────

_stream: Optional[MicrophoneStream] = None


def get_microphone_stream(**kwargs) -> MicrophoneStream:
    """Return or create the singleton microphone stream."""
    global _stream
    if _stream is None:
        _stream = MicrophoneStream(**kwargs)
    return _stream
