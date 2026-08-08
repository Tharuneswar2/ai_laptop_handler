import asyncio
import sounddevice as sd

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent


SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1024


class MyEventHandler(TranscriptResultStreamHandler):

    async def handle_transcript_event(
        self,
        transcript_event: TranscriptEvent
    ):
        results = transcript_event.transcript.results

        for result in results:
            if not result.alternatives:
                continue

            text = result.alternatives[0].transcript.strip()

            if not text:
                continue

            if result.is_partial:
                print(f"\rPartial: {text}", end="", flush=True)
            else:
                print(f"\rFinal:   {text}")


async def microphone_stream(stream):

    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def callback(indata, frames, time, status):
        if status:
            print(f"\nMicrophone: {status}")

        audio = bytes(indata)

        loop.call_soon_threadsafe(
            queue.put_nowait,
            audio
        )

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_SIZE,
        dtype="int16",
        channels=CHANNELS,
        callback=callback,
    ):
        print("Microphone ready")
        print("Listening...\n")

        while True:
            audio = await queue.get()

            await stream.input_stream.send_audio_event(
                audio_chunk=audio
            )


async def main():

    client = TranscribeStreamingClient(
        region="ap-south-1"
    )

    print("Connecting to Amazon Transcribe...")

    stream = await client.start_stream_transcription(
        language_code="en-US",
        media_sample_rate_hz=SAMPLE_RATE,
        media_encoding="pcm",
    )

    print("Amazon Transcribe connected")
    print("Listening...\n")

    handler = MyEventHandler(
        stream.output_stream
    )

    try:

        await asyncio.gather(
            microphone_stream(stream),
            handler.handle_events(),
        )

    except KeyboardInterrupt:
        pass

    finally:
        try:
            await stream.input_stream.end_stream()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())