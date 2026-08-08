#!/usr/bin/env python3
"""
main.py — AI Laptop Handler entry point.

Coordinates the full pipeline:
  listen → transcribe → understand → route → execute → speak

Modes:
  python main.py              # Web UI mode (default, browser STT via WebSocket)
  python main.py --text       # Text-only mode (keyboard input)
  python main.py --api        # Start API server only (REST endpoints)
  python main.py --aws        # Amazon Transcribe Streaming (headless voice mode)
  python main.py --aws --debug  # AWS mode with debug logging
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure project root is in the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config
from brain.intent_parser import parse_intent, requires_confirmation
from brain.memory import Memory
from router.tool_router import route
from ui.terminal_ui import (
    console, print_banner, print_status, print_heard,
    print_intent, print_result, print_error, print_divider,
    print_help, display_interaction, prompt_text_input,
)


logger = logging.getLogger(__name__)


# ─── Logging Setup ───────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure logging — full detail to file, minimal output to console."""
    log_file = config.LOG_DIR / "nova.log"

    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL))
    root.handlers.clear()

    formatter = logging.Formatter(
        fmt=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT,
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)


def setup_debug_logging() -> None:
    """Enable debug-level console logging for troubleshooting."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT,
    )
    debug_handler = logging.StreamHandler(sys.stdout)
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(formatter)
    root.addHandler(debug_handler)

    for name in ("speech", "speech.amazon_transcribe", "speech.microphone", "speech.vad"):
        logging.getLogger(name).setLevel(logging.DEBUG)


# ─── Core Pipeline ───────────────────────────────────────────────────

def process_command(text: str, memory: Memory, speak_response: bool = True) -> None:
    """
    Process a single user command or multi-step goal through the full pipeline.
    """
    start = time.time()

    parsed = parse_intent(text)

    from planner.task import ExecutionPlan
    if isinstance(parsed, ExecutionPlan):
        console.print(f"  [bold cyan]Execution Plan generated for goal:[/] [white]{parsed.goal}[/]")
        for i, t in enumerate(parsed.tasks):
            console.print(f"    [dim]{i+1}. [{t.tool}.{t.action}][/] {t.params}")

        from planner.executor import execute_plan
        result = execute_plan(parsed)
        duration_ms = int((time.time() - start) * 1000)

        print_result(result.message, result.success)

        if speak_response:
            try:
                from voice.speaker import speak
                speak(f"Completed goal: {parsed.goal}")
            except Exception as e:
                logger.warning("TTS failed: %s", e)

        memory.add(
            user_text=text,
            intent="planner.execute_plan",
            result=result.message,
            status="ok" if result.success else "error",
            duration_ms=duration_ms,
        )
        print_divider()
        return

    intent = parsed
    print_intent(intent.tool, intent.action)

    if requires_confirmation(intent):
        console.print("  [bold yellow]This action requires confirmation.[/]")

    result = route(intent)
    duration_ms = int((time.time() - start) * 1000)

    print_result(result.message, result.success)

    if speak_response:
        try:
            from voice.speaker import speak
            speak(result.message[:200])
        except Exception as e:
            logger.warning("TTS failed: %s", e)

    memory.add(
        user_text=text,
        intent=f"{intent.tool}.{intent.action}",
        result=result.message,
        status="ok" if result.success else "error",
        duration_ms=duration_ms,
    )

    print_divider()


# ─── Text Mode Loop ──────────────────────────────────────────────────

def run_text_mode(memory: Memory) -> None:
    """Run the assistant in text-only mode (keyboard input, no mic)."""
    print_banner()
    print_help()
    print_status("Text Mode — type commands below", "bold yellow")
    console.print("  [dim]Type 'quit' or 'exit' to stop. Type 'help' for examples.[/]")
    print_divider()

    while True:
        try:
            text = prompt_text_input()
            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                print_status("Goodbye!", "bold magenta")
                break
            if text.lower() == "help":
                print_help()
                continue
            if text.lower() == "history":
                recent = memory.get_recent(10)
                for entry in recent:
                    console.print(f"  [dim]{entry['timestamp']}[/] {entry['user_text']} -> {entry['result']}")
                print_divider()
                continue

            from voice.wakeword import check_text_for_wake_word
            _, clean_text = check_text_for_wake_word(text)
            if clean_text:
                text = clean_text

            print_heard(text)
            process_command(text, memory, speak_response=False)

        except KeyboardInterrupt:
            console.print("\n")
            print_status("Interrupted. Goodbye!", "bold magenta")
            break


# ─── Web Mode ────────────────────────────────────────────────────────

def run_web_mode() -> None:
    """
    Start the web UI with browser-based STT.
    """
    print_banner()
    console.print("  [bold green]Speech Provider:[/]")
    console.print("  [bold cyan]Default Local Provider (Browser STT)[/]")
    console.print()
    console.print(f"  [bold white]Open your browser:[/] [cyan]http://{config.API_HOST}:{config.API_PORT}[/]")
    console.print(f"  [bold white]API docs:[/]          [cyan]http://{config.API_HOST}:{config.API_PORT}/docs[/]")
    console.print()
    console.print("  [dim]Use Chrome or Edge for best Speech Recognition support.[/]")
    console.print("  [dim]Keep the browser tab open for continuous listening.[/]")
    console.print("  [dim]Press Ctrl+C to stop the server.[/]")
    print_divider()

    from api.server import start_server
    start_server()


# ─── AWS Voice Mode ─────────────────────────────────────────────────

# How long to wait (in seconds) after the last FINAL transcript before
# dispatching the accumulated utterance. This gives the user time to
# finish multi-segment sentences without the half-sentence being sent
# to the LLM prematurely.
UTTERANCE_SILENCE_TIMEOUT = 1.5  # seconds


async def run_aws_voice_mode(use_webrtc: bool = False, debug: bool = False) -> None:
    """
    Headless AWS voice assistant mode.

    Uses Amazon Transcribe Streaming for live STT.
    No browser, no web server, no GUI.
    Only microphone interaction.

    Args:
        use_webrtc: If True, use WebRTC microphone (better audio processing).
        debug: Enable debug logging.
    """
    from speech.factory import create_provider
    from speech.provider import TranscriptEvent, TranscriptKind
    from speech.wakeword import WakeWordDetector

    memory = Memory()
    wake_detector = WakeWordDetector(wake_words=config.WAKE_WORDS)

    # Create provider
    provider = create_provider(
        use_aws=not use_webrtc,
        use_aws_live=use_webrtc,
        aws_region=config.AWS_REGION,
        aws_language=config.AWS_LANGUAGE_CODE,
        aws_sample_rate=config.AWS_SAMPLE_RATE,
        wake_words=config.WAKE_WORDS,
        debug=debug,
    )

    # Print banner
    console.print()
    console.print("  [bold cyan]NOVA AI LAPTOP HANDLER[/]")
    if use_webrtc:
        console.print("  [bold cyan]AWS VOICE MODE (WebRTC)[/]")
    else:
        console.print("  [bold cyan]AWS VOICE MODE[/]")
    console.print()
    console.print("  [bold green]STT Provider:[/]   Amazon Transcribe" + (" (WebRTC)" if use_webrtc else ""))
    console.print("  [bold green]Mode:[/]           Headless Voice")
    console.print("  [bold green]Microphone:[/]     Initializing...")
    console.print("  [bold green]Status:[/]         Connecting...")
    console.print()
    print_divider()

    # Track startup message
    startup_spoken = False
    stop_event = asyncio.Event()

    # Handle CTRL+C cleanly
    loop = asyncio.get_event_loop()

    def _signal_handler():
        console.print("\n")
        console.print("  [dim]Stopping...[/]")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # ── Utterance accumulation state ──────────────────────────────────
    # Instead of processing each FINAL segment immediately, we buffer
    # them and only dispatch after the user stops speaking (no new
    # FINAL events for UTTERANCE_SILENCE_TIMEOUT seconds).
    accumulated_segments: list[str] = []  # buffered FINAL text segments
    flush_task: Optional[asyncio.Task] = None  # pending flush timer
    user_is_speaking = False  # True while PARTIAL events are arriving

    async def _flush_accumulated() -> None:
        """
        Wait for silence timeout, then dispatch the accumulated utterance.

        Called as an asyncio task each time a FINAL segment arrives.
        If a new FINAL arrives before this fires, this task is cancelled
        and a fresh one is started (debounce pattern).
        """
        nonlocal accumulated_segments, flush_task

        await asyncio.sleep(UTTERANCE_SILENCE_TIMEOUT)

        # Combine all accumulated segments into a single utterance
        full_text = " ".join(accumulated_segments).strip()
        accumulated_segments.clear()
        flush_task = None

        if not full_text:
            return

        # Show the full assembled utterance
        console.print(f"\r  [bold green]You (complete):[/] [white]{full_text}[/]" + " " * 20)

        # Check wake word on the full text
        has_wake, remaining = wake_detector.check(full_text)

        if has_wake:
            wake_detector.consume_wake()
            if remaining:
                # Command after wake word — process it
                console.print(f"  [bold cyan]Command:[/] {remaining}")
                console.print("  [dim]Sending command to AI...[/]")
                _process_in_thread(remaining, memory)
            else:
                # Wake word only — acknowledge and wait
                console.print("  [bold yellow]Listening for command...[/]")
                try:
                    from voice.speaker import speak
                    speak("Yes, Sir?")
                except Exception:
                    pass
        elif wake_detector.is_wake_active:
            # Command after wake (split utterance across flushes)
            wake_detector.consume_wake()
            console.print(f"  [bold cyan]Command:[/] {full_text}")
            console.print("  [dim]Sending command to AI...[/]")
            _process_in_thread(full_text, memory)
        else:
            # No wake word — ignore
            if debug:
                logger.debug("Ignoring (no wake word): %s", full_text[:60])

    try:
        await provider.start()

        # Update status
        console.print("  [bold green]Microphone:[/]     Ready")
        console.print("  [bold green]Status:[/]         Listening")
        console.print()
        print_divider()

        # Stream events
        async for event in provider.stream():
            if stop_event.is_set():
                break

            if event.kind == TranscriptKind.ERROR:
                # Reconnection or error messages
                if "Reconnecting" in (event.error or ""):
                    console.print(f"  [yellow]{event.error}[/]")
                else:
                    console.print(f"  [red]STT Error: {event.error}[/]")
                continue

            if event.kind == TranscriptKind.PARTIAL:
                # Live partial transcript — user is still speaking
                user_is_speaking = True
                console.print(f"\r  [dim]You:[/] [white]{event.text}[/]", end="")

                # If we have a pending flush and a new partial arrives,
                # cancel it — the user is still talking
                if flush_task and not flush_task.done():
                    flush_task.cancel()
                    flush_task = None
                continue

            if event.kind == TranscriptKind.FINAL:
                text = event.text.strip()
                if not text:
                    continue

                user_is_speaking = False

                # Show the segment as it arrives (informational)
                console.print(f"\r  [dim]Segment:[/] [white]{text}[/]" + " " * 20)

                # Accumulate this segment
                accumulated_segments.append(text)

                # Cancel any pending flush timer and start a new one
                # (debounce — resets the silence countdown)
                if flush_task and not flush_task.done():
                    flush_task.cancel()
                flush_task = asyncio.create_task(_flush_accumulated())

            # Speak startup message once after first successful connection
            if not startup_spoken and event.kind in (TranscriptKind.PARTIAL, TranscriptKind.FINAL):
                startup_spoken = True
                try:
                    from voice.speaker import speak
                    speak("Nova is alive.")
                except Exception:
                    pass

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("AWS voice mode error: %s", e, exc_info=True)
        console.print(f"  [red]Fatal error: {e}[/]")
    finally:
        # Cancel any pending flush
        if flush_task and not flush_task.done():
            flush_task.cancel()
        console.print("  [dim]Stopping microphone...[/]")
        await provider.stop()
        console.print("  [dim]Stopping Amazon Transcribe...[/]")
        console.print("  [dim]AWS voice mode stopped.[/]")
        console.print("  [dim]Goodbye.[/]")


def _process_in_thread(text: str, memory: Memory) -> None:
    """Process a command in a background thread to avoid blocking the event loop."""
    import threading

    def _run():
        try:
            process_command(text, memory, speak_response=True)
        except Exception as e:
            logger.error("Command processing failed: %s", e)

    thread = threading.Thread(target=_run, daemon=True, name="cmd-processor")
    thread.start()


# ─── Entry Point ─────────────────────────────────────────────────────

def main():
    """Parse arguments and start the assistant."""
    parser = argparse.ArgumentParser(
        description="AI Laptop Handler (Nova) — voice-controlled laptop assistant",
    )
    parser.add_argument("--text", action="store_true", help="Run in text-only mode (keyboard input)")
    parser.add_argument("--web", action="store_true", help="Run web UI with browser-based STT (default)")
    parser.add_argument("--api", action="store_true", help="Start API server only (REST endpoints)")
    parser.add_argument("--aws", action="store_true", help="Use Amazon Transcribe Streaming (headless voice mode)")
    parser.add_argument("--aws-live", action="store_true", help="Use Amazon Transcribe with WebRTC (best audio quality)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging()
    if args.debug:
        setup_debug_logging()

    logger.info("Starting AI Laptop Handler (Nova)...")
    stt_mode = "aws-live" if args.aws_live else ("aws" if args.aws else config.STT_PROVIDER)
    logger.info("STT Provider: %s", stt_mode)

    if args.api:
        from api.server import start_server
        start_server()
        return

    if args.text:
        memory = Memory()
        run_text_mode(memory)
        return

    if args.aws or args.aws_live:
        # Headless AWS voice mode — no browser, no web server
        try:
            asyncio.run(run_aws_voice_mode(
                use_webrtc=args.aws_live,
                debug=args.debug,
            ))
        except KeyboardInterrupt:
            console.print("\n  [dim]Goodbye.[/]")
        return

    # Default: Web mode
    run_web_mode()


if __name__ == "__main__":
    main()
