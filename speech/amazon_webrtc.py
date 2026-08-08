"""
speech/amazon_webrtc.py — Amazon Transcribe with WebRTC microphone.

Uses aiortc MediaPlayer for microphone capture with built-in
audio processing (noise reduction, echo cancellation, AGC).
Based on the working aws-test-webrtc.py pattern.
"""

import asyncio
import logging
import time
from typing import AsyncIterator, Optional

from speech.provider import SpeechProvider, TranscriptEvent, TranscriptKind
from speech.wakeword import WakeWordDetector

logger = logging.getLogger(__name__)

# Lazy imports
_aiortc = None
_av = None
_amazon_transcribe = None


def _ensure_imports():
    """Lazy-import aiortc, av, and amazon_transcribe."""
    global _aiortc, _av, _amazon_transcribe

    if _aiortc is None:
        try:
            from aiortc.contrib.media import MediaPlayer
            _aiortc = {"MediaPlayer": MediaPlayer}
        except ImportError:
            raise ImportError(
                "aiortc is required for WebRTC mode. "
                "Install with: pip install aiortc av"
            )

    if _av is None:
        try:
            from av.audio.resampler import AudioResampler
            _av = {"AudioResampler": AudioResampler}
        except ImportError:
            raise ImportError(
                "av (PyAV) is required for WebRTC mode. "
                "Install with: pip install av"
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


def list_audio_devices() -> list:
    """List available audio input devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        inputs = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                inputs.append((i, d["name"]))
        return inputs
    except Exception:
        return []


def _find_default_microphone() -> str:
    """Find the default input microphone name for DirectShow."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        default_idx = sd.default.device[0]

        # First pass: find a non-truncated real input device
        for i, d in enumerate(devices):
            name = d.get("name", "")
            max_channels = d.get("max_input_channels", 0)
            if max_channels > 0 and name:
                lower_name = name.lower()
                if "sound mapper" in lower_name:
                    continue
                if "primary sound capture" in lower_name:
                    continue
                # Skip truncated names (DirectShow bug)
                if not name.endswith(")"):
                    continue
                if i == default_idx:
                    logger.info("Selected default microphone: %s", name)
                    return name

        # Second pass: if default was truncated/mapper, find first complete name
        for i, d in enumerate(devices):
            name = d.get("name", "")
            max_channels = d.get("max_input_channels", 0)
            if max_channels > 0 and name:
                lower_name = name.lower()
                if "sound mapper" in lower_name or "primary sound capture" in lower_name:
                    continue
                if name.endswith(")"):
                    logger.info("Selected microphone: %s", name)
                    return name

        # Third pass: accept truncated names as last resort
        for i, d in enumerate(devices):
            name = d.get("name", "")
            max_channels = d.get("max_input_channels", 0)
            if max_channels > 0 and name:
                lower_name = name.lower()
                if "sound mapper" not in lower_name and "primary sound capture" not in lower_name:
                    logger.info("Using fallback microphone (may be truncated): %s", name)
                    return name

    except Exception as e:
        logger.warning("Failed to detect microphone: %s", e)

    return "Microphone Array (AMD Audio Device)"


class WebRTCTranscriptHandler:
    """
    Handles transcript events from Amazon Transcribe for WebRTC mode.
    """

    def __init__(self, output_stream, event_queue: asyncio.Queue):
        self.output_stream = output_stream
        self.event_queue = event_queue

    def _create_handler_class(self):
        """Create a dynamic handler class."""
        queue = self.event_queue
        base_handler = _amazon_transcribe["handler"]

        class Handler(base_handler):
            async def handle_transcript_event(self, transcript_event):
                results = transcript_event.transcript.results
                for result in results:
                    if not result.alternatives:
                        continue
                    text = result.alternatives[0].transcript.strip()
                    if not text:
                        continue
                    kind = TranscriptKind.PARTIAL if result.is_partial else TranscriptKind.FINAL
                    event = TranscriptEvent(kind=kind, text=text)
                    await queue.put(event)

        return Handler

    async def start(self):
        """Start handling transcript events."""
        handler_class = self._create_handler_class()
        handler = handler_class(self.output_stream)
        await handler.handle_events()


class WebRTCAmazonProvider(SpeechProvider):
    """
    Amazon Transcribe Streaming provider with WebRTC microphone.

    Uses aiortc MediaPlayer for microphone capture with built-in
    audio processing (noise reduction, echo cancellation, AGC).
    """

    def __init__(
        self,
        region: str = "ap-south-1",
        language_code: str = "en-US",
        sample_rate: int = 16000,
        microphone_name: str = None,
        enable_wake_word: bool = True,
        wake_words: list = None,
        max_reconnect_attempts: int = 10,
        debug: bool = False,
    ):
        self.region = region
        self.language_code = language_code
        self.sample_rate = sample_rate
        self.microphone_name = microphone_name
        self.enable_wake_word = enable_wake_word
        self.max_reconnect_attempts = max_reconnect_attempts
        self.debug = debug

        self._wake_word: Optional[WakeWordDetector] = None
        self._running = False
        self._connected = False
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._reconnect_count = 0
        self._start_time = 0.0
        self._player = None
        self._stream_obj = None

        if enable_wake_word:
            self._wake_word = WakeWordDetector(wake_words=wake_words)

    @property
    def name(self) -> str:
        return "Amazon Transcribe (WebRTC)"

    async def start(self) -> None:
        """Initialize — no persistent connection yet."""
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        logger.info("WebRTC Amazon provider started (region=%s)", self.region)

    async def stop(self) -> None:
        """Stop streaming and release resources."""
        self._running = False
        self._connected = False

        if self._wake_word:
            self._wake_word.reset()

        if self._player:
            try:
                self._player.audio.stop()
            except Exception:
                pass
            self._player = None

        if self._stream_obj:
            try:
                await self._stream_obj.input_stream.end_stream()
            except Exception:
                pass
            self._stream_obj = None

        duration = time.time() - self._start_time
        logger.info("WebRTC Amazon provider stopped (duration: %.1fs)", duration)

    async def stream(self) -> AsyncIterator[TranscriptEvent]:
        """
        Stream audio to Amazon Transcribe and yield transcript events.
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
        """Run a single streaming session with WebRTC microphone."""
        _ensure_imports()
        MediaPlayer = _aiortc["MediaPlayer"]
        AudioResampler = _av["AudioResampler"]
        TranscribeStreamingClient = _amazon_transcribe["client"]

        # Determine audio device
        if self.microphone_name:
            device_spec = f"audio={self.microphone_name}"
        else:
            device_name = _find_default_microphone()
            device_spec = f"audio={device_name}"

        # Open microphone with WebRTC (MediaPlayer)
        player = MediaPlayer(device_spec, format="dshow")

        if player.audio is None:
            raise RuntimeError("Could not open microphone. Check your audio device.")

        self._player = player

        # Create resampler: any format → 16kHz mono s16
        resampler = AudioResampler(
            format="s16",
            layout="mono",
            rate=self.sample_rate,
        )

        # Connect to Amazon Transcribe
        client = TranscribeStreamingClient(region=self.region)
        stream = await client.start_stream_transcription(
            language_code=self.language_code,
            media_sample_rate_hz=self.sample_rate,
            media_encoding="pcm",
        )

        self._stream_obj = stream
        self._connected = True
        self._reconnect_count = 0
        logger.info("Connected to Amazon Transcribe (WebRTC mode).")

        # Create transcript handler
        handler = WebRTCTranscriptHandler(stream.output_stream, self._event_queue)

        # Run audio send and transcript receive concurrently
        send_task = asyncio.create_task(self._send_audio_webrtc(player, resampler, stream))
        recv_task = asyncio.create_task(handler.start())

        try:
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

    async def _send_audio_webrtc(self, player, resampler, stream):
        """Send audio from WebRTC microphone to Amazon Transcribe."""
        frame_count = 0

        try:
            while self._running:
                frame = await player.audio.recv()
                frame_count += 1

                # Log first frame info
                if frame_count == 1 and self.debug:
                    logger.debug(
                        "Audio input: format=%s, rate=%d Hz, layout=%s",
                        frame.format.name if frame.format else "unknown",
                        frame.sample_rate,
                        frame.layout.name if frame.layout else "unknown",
                    )

                # Resample to 16kHz mono s16
                resampled_frames = resampler.resample(frame)
                if not isinstance(resampled_frames, list):
                    resampled_frames = [resampled_frames]

                for resampled in resampled_frames:
                    if resampled is None:
                        continue
                    pcm_bytes = resampled.to_ndarray().tobytes()
                    if pcm_bytes:
                        await stream.input_stream.send_audio_event(audio_chunk=pcm_bytes)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("WebRTC audio error: %s", e)
            raise

    async def health_check(self) -> bool:
        """Check if connected to Amazon Transcribe."""
        return self._connected
