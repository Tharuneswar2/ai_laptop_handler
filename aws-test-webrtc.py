import asyncio
import signal

from aiortc.contrib.media import MediaPlayer
from av.audio.resampler import AudioResampler

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent


# ============================================================
# CONFIGURATION
# ============================================================

AWS_REGION = "ap-south-1"

MICROPHONE = "Microphone Array (AMD Audio Device)"

TARGET_SAMPLE_RATE = 16000


# ============================================================
# TRANSCRIPT HANDLER
# ============================================================

class TranscriptHandler(TranscriptResultStreamHandler):

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
                print(
                    f"\rPARTIAL: {text:<100}",
                    end="",
                    flush=True
                )

            else:
                print(
                    f"\nFINAL:   {text}",
                    flush=True
                )


# ============================================================
# MAIN
# ============================================================

async def main():

    print()
    print("=" * 65)
    print(" WEBRTC → AMAZON TRANSCRIBE LIVE TEST")
    print("=" * 65)
    print()

    print(f"Microphone : {MICROPHONE}")
    print(f"AWS Region : {AWS_REGION}")
    print(f"Target     : {TARGET_SAMPLE_RATE} Hz / Mono / PCM")
    print()

    # ========================================================
    # MICROPHONE
    # ========================================================

    print("Opening microphone...")

    player = MediaPlayer(
        f"audio={MICROPHONE}",
        format="dshow",
    )

    if player.audio is None:
        raise RuntimeError(
            "Could not open microphone."
        )

    print("Microphone: READY")

    # ========================================================
    # AWS
    # ========================================================

    print("Connecting to Amazon Transcribe...")

    client = TranscribeStreamingClient(
        region=AWS_REGION
    )

    stream = await client.start_stream_transcription(
        language_code="en-US",
        media_sample_rate_hz=TARGET_SAMPLE_RATE,
        media_encoding="pcm",
    )

    print("Amazon Transcribe: CONNECTED")

    print()
    print("-" * 65)
    print(" SPEAK NOW")
    print()
    print(" Example:")
    print("   open chrome")
    print("   open downloads")
    print("   open visual studio code")
    print()
    print(" Press Ctrl+C to stop")
    print("-" * 65)
    print()

    # ========================================================
    # AUDIO RESAMPLER
    # ========================================================

    resampler = AudioResampler(
        format="s16",
        layout="mono",
        rate=TARGET_SAMPLE_RATE,
    )

    # ========================================================
    # SEND MICROPHONE → AWS
    # ========================================================

    async def send_audio():

        frame_count = 0

        try:

            while True:

                frame = await player.audio.recv()

                frame_count += 1

                # ------------------------------------------------
                # Print information about first frame
                # ------------------------------------------------

                if frame_count == 1:

                    print()
                    print("[AUDIO DEBUG]")
                    print(
                        f"  Input format : {frame.format.name}"
                    )
                    print(
                        f"  Input rate   : {frame.sample_rate} Hz"
                    )
                    print(
                        f"  Input layout : {frame.layout.name}"
                    )
                    print(
                        f"  Channels     : {len(frame.layout.channels)}"
                    )
                    print()

                # ------------------------------------------------
                # Resample:
                #
                # Whatever microphone gives us
                #              ↓
                #       16 kHz mono
                #       signed 16-bit
                #              ↓
                #         Amazon AWS
                # ------------------------------------------------

                resampled_frames = resampler.resample(frame)

                if not isinstance(
                    resampled_frames,
                    list
                ):
                    resampled_frames = [
                        resampled_frames
                    ]

                for resampled in resampled_frames:

                    if resampled is None:
                        continue

                    pcm_bytes = resampled.to_ndarray().tobytes()

                    if pcm_bytes:

                        await stream.input_stream.send_audio_event(
                            audio_chunk=pcm_bytes
                        )

                # ------------------------------------------------
                # Debug every 100 frames
                # ------------------------------------------------

                if frame_count % 100 == 0:

                    print(
                        f"\rAudio frames sent: {frame_count}",
                        end="",
                        flush=True
                    )

        except asyncio.CancelledError:

            print("\nAudio task cancelled.")

            raise

        except Exception as e:

            print()
            print()
            print("AUDIO ERROR:")
            print(repr(e))

            raise

    # ========================================================
    # RECEIVE AWS TRANSCRIPTS
    # ========================================================

    handler = TranscriptHandler(
        stream.output_stream
    )

    # ========================================================
    # CREATE TASKS
    # ========================================================

    audio_task = asyncio.create_task(
        send_audio()
    )

    transcript_task = asyncio.create_task(
        handler.handle_events()
    )

    # ========================================================
    # WAIT
    # ========================================================

    try:

        await asyncio.gather(
            audio_task,
            transcript_task,
        )

    except asyncio.CancelledError:

        pass

    finally:

        print()
        print()
        print("Stopping...")

        # ----------------------------------------------------
        # Stop audio
        # ----------------------------------------------------

        if not audio_task.done():
            audio_task.cancel()

        # ----------------------------------------------------
        # End AWS input stream
        # ----------------------------------------------------

        try:
            await stream.input_stream.end_stream()
        except Exception:
            pass

        # ----------------------------------------------------
        # Stop transcript task
        # ----------------------------------------------------

        if not transcript_task.done():
            transcript_task.cancel()

        # ----------------------------------------------------
        # Stop microphone
        # ----------------------------------------------------

        try:
            player.audio.stop()
        except Exception:
            pass

        print("Microphone stopped.")
        print("Amazon Transcribe stopped.")
        print("Done.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print()
        print("Stopped by user.")