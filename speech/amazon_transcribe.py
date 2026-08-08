"""
speech/amazon_transcribe.py — Amazon Transcribe Streaming provider.

Uses the amazon_transcribe SDK with sounddevice microphone capture.
Based on the working aws-test.py pattern.
"""

import asyncio
import logging
import time
from typing import AsyncIterator, Optional

from speech.provider import SpeechProvider, TranscriptEvent, TranscriptKind
from speech.wakeword import WakeWordDetector

logger = logging.getLogger(__name__)

# Lazy imports
_sounddevice = None
_amazon_transcribe = None


def _ensure_imports():
    """Lazy-import sounddevice and amazon_transcribe."""
    global _sounddevice, _amazon_transcribe
    if _sounddevice is None:
        try:
            import sounddevice as sd
            _sounddevice = sd
        except ImportError:
            raise ImportError(
                "sounddevice is required for Amazon Transcribe. "
                "Install with: pip install sounddevice"
            )
    if _amazon_transcribe is None:
        try:
            from amazon_transcribe.client import TranscribeStreamingClient
            from amazon_transcribe.handlers import TranscriptResultStreamHandler
            from amazon_transcribe.model import TranscriptEvent
            _amazon_transcribe = {
                "client": TranscribeStreamingClient,
                "handler": TranscriptResultStreamHandler,
                "event": TranscriptEvent,
            }
        except ImportError:
            raise ImportError(
                "amazon-transcribe-sdk is required. "
                "Install with: pip install amazon-transcribe-sdk"
            )


class TranscriptHandler:
    """
    Handles transcript events from Amazon Transcribe.

    Puts events on an asyncio queue for consumption by the provider.
    """

    def __init__(self, output_stream, event_queue: asyncio.Queue):
        self.output_stream = output_stream
        self.event_queue = event_queue
        self._handler = None

    def _create_handler_class(self):
        """Create a dynamic handler class that puts events on the queue."""
        queue = self.event_queue
        base_handler = _amazon_transcribe["handler"]

        class Handler(base_handler):
            async def handle_transcript_event(self, transcript_event):
                results = transcript_event.transcript.results

                for result in results:
                    if not result.alternatives:
                        continue

                    text = result.alternatives[0].transcript.strip()
                    confidence = result.alternatives[0].get("confidence", 0.0) if hasattr(result.alternatives[0], "get") else 0.0

                    if not text:
                        continue

                    kind = TranscriptKind.PARTIAL if result.is_partial else TranscriptKind.FINAL
                    event = TranscriptEvent(
                        kind=kind,
                        text=text,
                        confidence=confidence,
                    )
                    await queue.put(event)

        return Handler

    async def start(self):
        """Start handling transcript events."""
        handler_class = self._create_handler_class()
        self._handler = handler_class(self.output_stream)
        await self._handler.handle_events()


class AmazonTranscribeProvider(SpeechProvider):
    """
    Amazon Transcribe Streaming speech provider.

    Uses the amazon_transcribe SDK with sounddevice for microphone capture.
    """

    def __init__(
        self,
        region: str = "ap-south-1",
        language_code: str = "en-US",
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        enable_wake_word: bool = True,
        wake_words: list = None,
        max_reconnect_attempts: int = 10,
        debug: bool = False,
    ):
        self.region = region
        self.language_code = language_code
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.enable_wake_word = enable_wake_word
        self.max_reconnect_attempts = max_reconnect_attempts
        self.debug = debug

        self._wake_word: Optional[WakeWordDetector] = None
        self._running = False
        self._connected = False
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._reconnect_count = 0
        self._start_time = 0.0
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._stream = None
        self._stream_obj = None

        if enable_wake_word:
            self._wake_word = WakeWordDetector(wake_words=wake_words)

    @property
    def name(self) -> str:
        return "Amazon Transcribe Streaming"

    async def start(self) -> None:
        """Initialize — no persistent connection yet, created per session."""
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        logger.info("Amazon Transcribe provider started (region=%s)", self.region)

    async def stop(self) -> None:
        """Stop streaming and release resources."""
        self._running = False
        self._connected = False

        if self._wake_word:
            self._wake_word.reset()

        # End stream if active
        if self._stream_obj:
            try:
                await self._stream_obj.input_stream.end_stream()
            except Exception:
                pass
            self._stream_obj = None

        duration = time.time() - self._start_time
        logger.info("Amazon Transcribe provider stopped (duration: %.1fs)", duration)

    async def stream(self) -> AsyncIterator[TranscriptEvent]:
        """
        Stream audio to Amazon Transcribe and yield transcript events.

        Handles reconnection on connection loss.
        """
        while self._running:
            try:
                session_task = asyncio.create_task(self._run_session())

                while not session_task.done():
                    try:
                        event = await asyncio.wait_for(
                            self._event_queue.get(), timeout=1.0
                        )
                        yield event
                    except asyncio.TimeoutError:
                        continue

                exc = session_task.exception() if not session_task.cancelled() else None
                if exc and self._running:
                    raise exc

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break

                self._reconnect_count += 1
                if self._reconnect_count > self.max_reconnect_attempts:
                    logger.error(
                        "Max reconnect attempts (%d) reached.",
                        self.max_reconnect_attempts,
                    )
                    yield TranscriptEvent(
                        kind=TranscriptKind.ERROR,
                        error=f"Connection failed after {self.max_reconnect_attempts} attempts: {e}",
                    )
                    break

                wait_time = min(2 ** self._reconnect_count, 30)
                logger.warning(
                    "Connection lost (%s). Reconnecting in %ds (attempt %d/%d)...",
                    e, wait_time, self._reconnect_count, self.max_reconnect_attempts,
                )
                yield TranscriptEvent(
                    kind=TranscriptKind.ERROR,
                    error=f"Reconnecting ({self._reconnect_count}/{self.max_reconnect_attempts})...",
                )
                await asyncio.sleep(wait_time)

    async def _run_session(self) -> None:
        """Run a single streaming session."""
        _ensure_imports()
        sd = _sounddevice
        TranscribeStreamingClient = _amazon_transcribe["client"]

        # Create client and start stream
        client = TranscribeStreamingClient(region=self.region)

        stream = await client.start_stream_transcription(
            language_code=self.language_code,
            media_sample_rate_hz=self.sample_rate,
            media_encoding="pcm",
        )

        self._stream_obj = stream
        self._connected = True
        self._reconnect_count = 0
        logger.info("Connected to Amazon Transcribe Streaming.")

        # Create transcript handler
        handler = TranscriptHandler(stream.output_stream, self._event_queue)

        # Set up microphone with sounddevice callback
        audio_queue = self._audio_queue

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning("Microphone status: %s", status)
            audio = bytes(indata)
            loop.call_soon_threadsafe(audio_queue.put_nowait, audio)

        loop = asyncio.get_event_loop()

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                dtype="int16",
                channels=self.channels,
                callback=audio_callback,
            ):
                logger.info("Microphone opened (rate=%d, channels=%d)", self.sample_rate, self.channels)

                # Run audio send and transcript receive concurrently
                send_task = asyncio.create_task(self._send_audio(stream))
                recv_task = asyncio.create_task(handler.start())

                done, pending = await asyncio.wait(
                    [send_task, recv_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                for task in done:
                    if task.exception():
                        raise task.exception()

        finally:
            self._connected = False
            try:
                await stream.input_stream.end_stream()
            except Exception:
                pass
            self._stream_obj = None

    async def _send_audio(self, stream):
        """Send audio chunks from microphone to Amazon Transcribe."""
        while self._running:
            try:
                audio = await asyncio.wait_for(self._audio_queue.get(), timeout=1.0)
                await stream.input_stream.send_audio_event(audio_chunk=audio)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning("Failed to send audio: %s", e)
                break

    async def health_check(self) -> bool:
        """Check if connected to Amazon Transcribe."""
        return self._connected
