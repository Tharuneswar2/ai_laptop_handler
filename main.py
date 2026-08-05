#!/usr/bin/env python3
"""
main.py — AI Laptop Voice Handler entry point.

Coordinates the full pipeline:
  listen → transcribe → understand → route → execute → speak

Modes:
  python main.py              # Full voice mode (mic + speaker)
  python main.py --text       # Text-only mode (keyboard input)
  python main.py --no-wake    # Voice mode, skip wake word
  python main.py --api        # Start API server instead
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is in the Python path
sys.path.insert(0, str(Path(__file__).parent))

import config
from brain.intent_parser import parse_intent, requires_confirmation
from brain.memory import Memory
from router.tool_router import route
from ui.terminal_ui import (
    console, print_banner, print_status, print_heard,
    print_intent, print_result, print_error, print_divider,
    print_help, display_interaction, prompt_text_input,
)

import signal
import sys

def shutdown(sig, frame):
    print("\nStopping...")
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
# ─── Logging Setup ───────────────────────────────────────────────────

def setup_logging() -> None:
    """Configure logging to both file and console."""
    log_file = config.LOG_DIR / "nova.log"

    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Suppress noisy libraries
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ─── Core Pipeline ───────────────────────────────────────────────────

def process_command(text: str, memory: Memory, speak_response: bool = True) -> None:
    """
    Process a single user command through the full pipeline.

    Args:
        text: The user's command text.
        memory: Memory instance for logging.
        speak_response: Whether to speak the response aloud.
    """
    start = time.time()

    # 1. Parse intent
    intent = parse_intent(text)
    print_intent(intent.tool, intent.action)

    # 2. Check for confirmation-required actions
    if requires_confirmation(intent):
        console.print("  [bold yellow]⚠ This action requires confirmation.[/]")

    # 3. Route to tool and execute
    result = route(intent)
    duration_ms = int((time.time() - start) * 1000)

    # 4. Display result
    print_result(result.message, result.success)

    # 5. Speak response
    if speak_response:
        try:
            from voice.speaker import speak
            speak(result.message[:200])  # limit length for TTS
        except Exception as e:
            logger.warning("TTS failed: %s", e)

    # 6. Log to memory
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
                print_status("Goodbye! 👋", "bold magenta")
                break
            if text.lower() == "help":
                print_help()
                continue
            if text.lower() == "history":
                recent = memory.get_recent(10)
                for entry in recent:
                    console.print(f"  [dim]{entry['timestamp']}[/] {entry['user_text']} → {entry['result']}")
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
            print_status("Interrupted. Goodbye! 👋", "bold magenta")
            break


# ─── Voice Mode Loop ─────────────────────────────────────────────────

def run_voice_mode(memory: Memory, use_wake_word: bool = True) -> None:
    """Run the assistant in full voice mode (mic + speaker)."""
    print_banner()
    print_help()

    if use_wake_word:
        print_status(f"Listening for wake word: {config.WAKE_WORDS}", "bold green")
    else:
        print_status("Listening (wake word disabled)...", "bold green")

    print_divider()

    from voice.listener import listen_smart
    from voice.wakeword import detect_wake_word, check_text_for_wake_word
    from voice.speaker import speak

    while True:
        try:
            if use_wake_word:
                # Wait for wake word
                print_status("Waiting for wake word...", "bold cyan")
                if not detect_wake_word(timeout=None):
                    continue
                speak("Yes?")
                print_status("Wake word detected! Listening...", "bold green")

            # Listen for command
            print_status("Listening...", "bold green")
            text = listen_smart()

            if not text:
                print_status("Didn't catch that. Try again.", "dim yellow")
                continue

            # Strip wake word if it's in the transcription
            _, clean_text = check_text_for_wake_word(text)
            if clean_text:
                text = clean_text

            print_heard(text)
            process_command(text, memory, speak_response=True)

        except KeyboardInterrupt:
            console.print("\n")
            print_status("Interrupted. Goodbye! 👋", "bold magenta")
            speak("Goodbye!")
            break
        except Exception as e:
            print_error(str(e))
            logger.error("Voice loop error: %s", e, exc_info=True)
            time.sleep(1)


# ─── Entry Point ─────────────────────────────────────────────────────

def main():
    """Parse arguments and start the assistant."""
    parser = argparse.ArgumentParser(
        description="AI Laptop Voice Handler (Nova) — voice-controlled laptop assistant",
    )
    parser.add_argument("--text", action="store_true", help="Run in text-only mode (no microphone)")
    parser.add_argument("--no-wake", action="store_true", help="Skip wake word detection")
    parser.add_argument("--api", action="store_true", help="Start API server instead")
    args = parser.parse_args()

    setup_logging()
    logger.info("Starting AI Laptop Handler (Nova)...")

    if args.api:
        from api.server import start_server
        start_server()
        return

    memory = Memory()

    if args.text:
        run_text_mode(memory)
    else:
        run_voice_mode(memory, use_wake_word=not args.no_wake)


if __name__ == "__main__":
    main()
