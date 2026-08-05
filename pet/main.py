"""
pet/main.py — Standalone entry point & demo launcher for Desktop Pet Engine.

Usage:
    python -m pet.main           # Run pet in normal idle state
    python -m pet.main --demo    # Run automated demo sequence cycling through states
    python -m pet.main --state listening # Start directly in specific state
"""

import sys
import time
import signal
import logging
import argparse
from pathlib import Path

# Ensure root project directory is in python path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pet.config import PetConfig
from pet.pet_controller import PetController
from pet.event_handler import PetState, PetEmotion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pet.main")


def run_demo(pet: PetController) -> None:
    """Run an automated demo sequence demonstrating all pet features."""
    logger.info("Starting Desktop Pet Demo Sequence...")

    demo_steps = [
        (0, lambda: pet.say("Hello! I am Nova, your desktop pet! 😸", duration_sec=3)),
        (3500, lambda: (pet.set_state("listening"), pet.say("Listening for your command... 🎤"))),
        (7000, lambda: (pet.set_state("thinking"), pet.say("Thinking & parsing intent... ⚡"))),
        (10500, lambda: (pet.set_state("working"), pet.say("Opening Google Chrome... 💻"))),
        (14000, lambda: (pet.set_state("happy"), pet.set_emotion("excited"), pet.say("Chrome opened successfully! 🎉"))),
        (17500, lambda: pet.show_notification("Battery status: 85% remaining 🔋")),
        (21000, lambda: (pet.set_state("error"), pet.set_emotion("confused"), pet.say("Oops! Command failed ❌"))),
        (24500, lambda: (pet.sleep(), pet.say("Time for a quick nap... Zzz 😴"))),
        (28500, lambda: pet.wake()),
        (31500, lambda: (pet.set_state("idle"), pet.say("Ready for work! Direct me anytime! ✨"))),
    ]

    for delay_ms, action in demo_steps:
        QTimer.singleShot(delay_ms, action)


def main():
    parser = argparse.ArgumentParser(description="Desktop Pet Engine for AI Assistant")
    parser.add_argument("--demo", action="store_true", help="Run automated demo sequence")
    parser.add_argument("--state", type=str, default="idle", help="Initial state (idle, listening, thinking, etc.)")
    args = parser.parse_args()

    config = PetConfig()
    pet = PetController(config)
    pet.start()

    if args.state != "idle":
        pet.set_state(args.state)

    if args.demo:
        run_demo(pet)
    else:
        pet.say("Nova Desktop Pet is ready! Drag me anywhere.", duration_sec=4)

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)  # Let Python interpreter run to catch SIGINT

    logger.info("Pet loop running. Press Ctrl+C to stop.")
    sys.exit(pet.app.exec())


if __name__ == "__main__":
    main()
