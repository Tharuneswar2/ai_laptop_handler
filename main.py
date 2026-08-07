#!/usr/bin/env python3
"""
main.py — AI Laptop Handler entry point.

Coordinates the full pipeline:
  listen → transcribe → understand → route → execute → speak

Modes:
  python main.py              # Web UI mode (default, browser STT via WebSocket)
  python main.py --text       # Text-only mode (keyboard input)
  python main.py --api        # Start API server only (REST endpoints)
  python main.py --aws        # Amazon Transcribe Streaming (server-side STT)
  python main.py --aws --debug  # AWS mode with debug logging
"""

import argparse
import asyncio
import logging
import sys
import time
import signal
from pathlib import Path

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


def shutdown(sig, frame):
    print("\nStopping...")
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)


# ─── Logging Setup ───────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure logging — full detail to file, minimal output to console."""
    log_file = config.LOG_DIR / "nova.log"

    # Root logger captures everything at INFO level
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL))

    # This function may be reached more than once by embedded/API entry points.
    # Avoid duplicate lines while keeping every handler explicitly UTF-8.
    root.handlers.clear()

    formatter = logging.Formatter(
        fmt=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT,
    )

    # File handler: all INFO and above (for debugging)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Console handler: only WARNING and above (keep terminal clean)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Suppress noisy libraries entirely
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)


def setup_debug_logging() -> None:
    """Enable debug-level console logging for troubleshooting."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Add debug console handler
    formatter = logging.Formatter(
        fmt=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT,
    )
    debug_handler = logging.StreamHandler(sys.stdout)
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(formatter)
    root.addHandler(debug_handler)

    # Enable debug for speech modules
    for name in ("speech", "speech.amazon_transcribe", "speech.microphone", "speech.vad"):
        logging.getLogger(name).setLevel(logging.DEBUG)


logger = logging.getLogger(__name__)


# ─── Core Pipeline ───────────────────────────────────────────────────

def process_command(text: str, memory: Memory, speak_response: bool = True) -> None:
    """
    Process a single user command or multi-step goal through the full pipeline.

    Args:
        text: The user's command or goal text.
        memory: Memory instance for logging.
        speak_response: Whether to speak the response aloud.
    """
    start = time.time()

    # 1. Parse intent or execution plan
    parsed = parse_intent(text)

    # 2. Handle ExecutionPlan (multi-step goal)
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

    # 3. Handle single Intent
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

            # Strip wake word if present
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

def run_web_mode(aws_mode: bool = False, debug: bool = False) -> None:
    """
    Start the web UI with browser-based STT.

    Optionally starts Amazon Transcribe provider if --aws flag is used.
    """
    from speech.factory import create_provider
    from speech.provider import get_provider

    # Create speech provider
    provider = create_provider(
        use_aws=aws_mode,
        aws_region=config.AWS_REGION,
        aws_language=config.AWS_LANGUAGE_CODE,
        aws_sample_rate=config.AWS_SAMPLE_RATE,
        wake_words=config.WAKE_WORDS,
        enable_vad=config.AWS_VAD_ENABLED,
        debug=debug,
    )

    print_banner()

    if aws_mode:
        console.print("  [bold green]Speech Provider:[/]")
        console.print("  [bold cyan]Amazon Transcribe Streaming[/]")
    else:
        console.print("  [bold green]Speech Provider:[/]")
        console.print("  [bold cyan]Default Local Provider (Browser STT)[/]")
    console.print()

    if not aws_mode:
        console.print(f"  [bold white]Open your browser:[/] [cyan]http://{config.API_HOST}:{config.API_PORT}[/]")
        console.print(f"  [bold white]API docs:[/]          [cyan]http://{config.API_HOST}:{config.API_PORT}/docs[/]")
        console.print()
        console.print("  [dim]Use Chrome or Edge for best Speech Recognition support.[/]")
        console.print("  [dim]Keep the browser tab open for continuous listening.[/]")
    else:
        console.print("  [dim]Speak into your microphone. Say 'Hey Nova' to activate.[/]")
        console.print("  [dim]Partial transcripts will appear in real-time.[/]")

    console.print("  [dim]Press Ctrl+C to stop the server.[/]")
    print_divider()

    from api.server import start_server

    # If AWS mode, register provider and run background listener
    if aws_mode:
        _run_aws_mode(provider, debug)
    else:
        start_server()


def _run_aws_mode(provider, debug: bool = False) -> None:
    """Run the application with Amazon Transcribe as the speech provider."""
    import threading
    from api.server import start_server
    from speech.provider import TranscriptEvent, TranscriptKind
    from speech.wakeword import WakeWordDetector
    from voice.speaker import speak

    memory = Memory()
    wake_detector = WakeWordDetector(wake_words=config.WAKE_WORDS)
    loop = asyncio.new_event_loop()

    def aws_listener():
        """Background thread running the AWS Transcribe stream."""
        asyncio.set_event_loop(loop)

        async def _run():
            from speech.microphone import get_microphone_stream

            await provider.start()

            try:
                async for event in provider.stream():
                    if event.kind == TranscriptKind.ERROR:
                        console.print(f"  [yellow]STT: {event.error}[/]")
                        continue

                    if event.kind == TranscriptKind.PARTIAL:
                        # Show live partial transcript (overwrite line)
                        console.print(f"\r  [dim]You:[/] [white]{event.text}[/]", end="")
                        continue

                    if event.kind == TranscriptKind.FINAL:
                        text = event.text.strip()
                        if not text:
                            continue

                        # Clear partial line and show final
                        console.print(f"\r  [bold green]You:[/] [white]{text}[/]" + " " * 20)

                        # Check wake word
                        has_wake, remaining = wake_detector.check(text)

                        if has_wake:
                            wake_detector.consume_wake()
                            if remaining:
                                # Command after wake word
                                console.print(f"  [bold cyan]Command:[/] {remaining}")
                                _process_in_main_thread(remaining, memory)
                            else:
                                console.print("  [bold yellow]Listening for command...[/]")
                                speak("Yes, Sir?")
                        elif wake_detector.is_wake_active:
                            # Command after wake
                            wake_detector.consume_wake()
                            console.print(f"  [bold cyan]Command:[/] {text}")
                            _process_in_main_thread(text, memory)
                        else:
                            logger.debug("Ignoring (no wake word): %s", text[:40])

            except Exception as e:
                logger.error("AWS listener error: %s", e)
                console.print(f"  [red]AWS Transcribe error: {e}[/]")
            finally:
                await provider.stop()

        loop.run_until_complete(_run())

    def _process_in_main_thread(text: str, memory: Memory):
        """Process a command in the main thread."""
        try:
            process_command(text, memory, speak_response=True)
        except Exception as e:
            logger.error("Command processing failed: %s", e)

    # Start AWS listener in background
    listener_thread = threading.Thread(target=aws_listener, daemon=True, name="aws-stt")
    listener_thread.start()

    # Start API server (for REST endpoints and potential web UI)
    try:
        start_server()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        provider.stop()


# ─── Entry Point ─────────────────────────────────────────────────────

def main():
    """Parse arguments and start the assistant."""
    parser = argparse.ArgumentParser(
        description="AI Laptop Handler (Nova) — voice-controlled laptop assistant",
    )
    parser.add_argument("--text", action="store_true", help="Run in text-only mode (keyboard input)")
    parser.add_argument("--web", action="store_true", help="Run web UI with browser-based STT (default)")
    parser.add_argument("--api", action="store_true", help="Start API server only (REST endpoints)")
    parser.add_argument("--aws", action="store_true", help="Use Amazon Transcribe Streaming (server-side STT)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging()
    if args.debug:
        setup_debug_logging()

    logger.info("Starting AI Laptop Handler (Nova)...")
    logger.info("STT Provider: %s", "aws" if args.aws else config.STT_PROVIDER)

    if args.api:
        from api.server import start_server
        start_server()
        return

    if args.text:
        memory = Memory()
        run_text_mode(memory)
        return

    # Default mode is Web Mode (with optional AWS)
    run_web_mode(aws_mode=args.aws, debug=args.debug)


if __name__ == "__main__":
    main()
