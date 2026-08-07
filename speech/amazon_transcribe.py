"""
speech/amazon_transcribe.py — Amazon Transcribe Streaming provider.

Uses the Amazon Transcribe Streaming SDK for real-time speech-to-text
with HTTP/2 streaming, partial transcripts, and automatic reconnect.
"""

import asyncio
import io
import json
import logging
import struct
import time
from typing import AsyncIterator, Optional

from speech.provider import SpeechProvider, TranscriptEvent, TranscriptKind
from speech.microphone import MicrophoneStream, get_microphone_stream
from speech.vad import EnergyVAD, VADConfig, create_vad
from speech.wakeword import WakeWordDetector

logger = logging.getLogger(__name__)

# Lazy imports
_aiobotocore_session = None


def _ensure_aiobotocore():
    """Lazy-import aiobotocore for Amazon Transcribe Streaming."""
    global _aiobotocore_session
    if _aiobotocore_session is None:
        try:
            import aiobotocore.session
            _aiobotocore_session = aiobotocore.session.get_session()
        except ImportError:
            raise ImportError(
                "aiobotocore is required for Amazon Transcribe. "
                "Install with: pip install aiobotocore[awscli]"
            )
    return _aiobotocore_session


class AmazonTranscribeProvider(SpeechProvider):
    """
    Amazon Transcribe Streaming speech provider.

    Streams audio from the microphone to Amazon Transcribe via HTTP/2.
    Receives partial and final transcripts in real-time.
    """

    def __init__(
        self,
        region: str = "ap-south-1",
        language_code: str = "en-US",
        sample_rate: int = 16000,
        enable_vad: bool = True,
        enable_wake_word: bool = True,
        wake_words: list = None,
        max_reconnect_attempts: int = 10,
        debug: bool = False,
    ):
        self.region = region
        self.language_code = language_code
        self.sample_rate = sample_rate
        self.enable_vad = enable_vad
        self.enable_wake_word = enable_wake_word
        self.max_reconnect_attempts = max_reconnect_attempts
        self.debug = debug

        self._microphone: Optional[MicrophoneStream] = None
        self._vad: Optional[EnergyVAD] = None
        self._wake_word: Optional[WakeWordDetector] = None
        self._running = False
        self._connected = False
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._reconnect_count = 0
        self._start_time = 0.0

        # Wake word and VAD setup
        if enable_wake_word:
            self._wake_word = WakeWordDetector(wake_words=wake_words)
        if enable_vad:
            self._vad = create_vad(config=VADConfig(sample_rate=sample_rate))

    @property
    def name(self) -> str:
        return "Amazon Transcribe Streaming"

    async def start(self) -> None:
        """Initialize microphone and begin streaming to Amazon Transcribe."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()

        # Start microphone
        self._microphone = get_microphone_stream(sample_rate=self.sample_rate)
        await self._microphone.start()

        logger.info(
            "Amazon Transcribe provider started (region=%s, language=%s, sample_rate=%d)",
            self.region, self.language_code, self.sample_rate,
        )

    async def stop(self) -> None:
        """Stop streaming and release resources."""
        self._running = False
        self._connected = False

        if self._microphone:
            await self._microphone.stop()
            self._microphone = None

        if self._wake_word:
            self._wake_word.reset()

        duration = time.time() - self._start_time
        logger.info("Amazon Transcribe provider stopped (duration: %.1fs)", duration)

    async def stream(self) -> AsyncIterator[TranscriptEvent]:
        """
        Stream audio to Amazon Transcribe and yield transcript events.

        Handles:
        - Partial transcripts
        - Final transcripts
        - Voice Activity Detection
        - Wake word detection
        - Automatic reconnect on connection loss
        """
        while self._running:
            try:
                async for event in self._stream_session():
                    yield event
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break

                self._reconnect_count += 1
                if self._reconnect_count > self.max_reconnect_attempts:
                    logger.error(
                        "Max reconnect attempts (%d) reached. Giving up.",
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

    async def _stream_session(self):
        """Single streaming session to Amazon Transcribe."""
        import struct

        session = _ensure_aiobotocore_session()
        client = session.create_client(
            "transcribestreaming",
            region_name=self.region,
        )

        try:
            async with client as transcribe:
                # Start streaming request
                request = transcribe.start_stream_transcription(
                    LanguageCode=self.language_code,
                    MediaSampleRateHertz=self.sample_rate,
                    MediaEncoding="pcm",
                    AudioChannelCount=1,
                    EnablePartialResultsStabilization=True,
                    PartialResultsStability="medium",
                )

                async with request as response:
                    self._connected = True
                    self._reconnect_count = 0
                    logger.info("Connected to Amazon Transcribe Streaming.")

                    # Send audio and receive transcripts concurrently
                    send_task = asyncio.create_task(self._send_audio(response))
                    recv_task = asyncio.create_task(self._receive_transcripts(response))

                    # Wait for either to complete (error or stop)
                    done, pending = await asyncio.wait(
                        [send_task, recv_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    # Check for errors
                    for task in done:
                        if task.exception():
                            raise task.exception()

        finally:
            self._connected = False

    async def _send_audio(self, response):
        """Send audio chunks from microphone to Amazon Transcribe."""
        if not self._microphone:
            return

        async for chunk in self._microphone.chunks():
            if not self._running:
                break

            # VAD: skip silence
            if self._vad and not self._vad.process(chunk):
                continue

            # Send audio event
            try:
                audio_event = {
                    "AudioEvent": {
                        "AudioChunk": chunk,
                    }
                }
                await response.input_stream.send(audio_event)
            except Exception as e:
                logger.warning("Failed to send audio: %s", e)
                break

        # Signal end of audio
        try:
            await response.input_stream.send_end_event()
        except Exception:
            pass

    async def _receive_transcripts(self, response):
        """Receive transcript events from Amazon Transcribe."""
        async for event in response.transcript_result_stream:
            if not self._running:
                break

            # Parse the event
            transcript_event = self._parse_transcript_event(event)
            if transcript_event:
                await self._event_queue.put(transcript_event)

    def _parse_transcript_event(self, event) -> Optional[TranscriptEvent]:
        """Parse an Amazon Transcribe event into a TranscriptEvent."""
        try:
            # Handle TranscriptEvent
            if hasattr(event, 'transcript'):
                transcript = event.transcript
                if transcript and transcript.get('results'):
                    for result in transcript['results']:
                        alternatives = result.get('alternatives', [])
                        if not alternatives:
                            continue

                        text = alternatives[0].get('transcript', '')
                        confidence = alternatives[0].get('confidence', 0.0)
                        is_partial = result.get('is_partial', True)

                        if text.strip():
                            kind = TranscriptKind.PARTIAL if is_partial else TranscriptKind.FINAL
                            return TranscriptEvent(
                                kind=kind,
                                text=text.strip(),
                                confidence=confidence,
                            )
            return None
        except Exception as e:
            logger.warning("Failed to parse transcript event: %s", e)
            return None

    async def health_check(self) -> bool:
        """Check if connected to Amazon Transcribe."""
        return self._connected
