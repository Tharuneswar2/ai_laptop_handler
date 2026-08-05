"""
examples/demo_controller.py — Automated demo driving the pet through its API.

Run::

    venv/bin/python pet/examples/demo_controller.py [--pet cat] [--scale 1.0]

This demonstrates every public API method.  The assistant backend would
call the exact same methods.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtCore import QTimer

from pet import PetConfig, PetController


def run_demo(pet: PetController) -> None:
    """Cycle the pet through states, emotions, bubbles and notifications."""

    def step(index: int) -> None:
        if index == 0:
            pet.change_pet(pet.config.default_pet)
            pet.say("Hello! I'm your desktop companion.")
            pet.notify("Nova online")
        elif index == 1:
            pet.set_state("listening")
            pet.set_emotion("curious")
            pet.say("I'm listening...")
        elif index == 2:
            pet.set_state("thinking")
            pet.set_emotion("neutral")
            pet.say("Let me think about that...")
        elif index == 3:
            pet.set_state("working")
            pet.say("Opening VS Code")
            pet.notify("Working...")
        elif index == 4:
            pet.set_state("speaking")
            pet.set_emotion("happy")
            pet.say("Done! Anything else?")
        elif index == 5:
            pet.set_state("happy")
            pet.set_emotion("excited")
            pet.say("Yay!")
        elif index == 6:
            pet.set_state("error")
            pet.set_emotion("surprised")
            pet.say("Oops, something went wrong.")
            pet.notify("Error: command failed")
        elif index == 7:
            pet.wake()
            pet.sleep()
            pet.say("Going to sleep...")
        elif index == 8:
            pet.wake()
            pet.set_scale(pet.config.scale * 1.3)
            pet.notify("Zoomed in!")
        elif index == 9:
            pet.set_scale(pet.config.scale)
            pet.move_to(100, 100)
            pet.notify("Moved to (100, 100)")
        elif index == 10:
            pet.set_state("idle")
            pet.say("That's the whole API. Drag me around!")
            return
        QTimer.singleShot(3200, lambda i=index + 1: step(i))

    QTimer.singleShot(1000, lambda: step(0))


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop Pet demo")
    parser.add_argument("--pet", default=None, help="pet pack id")
    parser.add_argument("--scale", type=float, default=None)
    args = parser.parse_args()

    config = PetConfig()
    if args.pet:
        config = config.with_defaults(default_pet=args.pet)
    if args.scale:
        config = config.with_defaults(scale=args.scale)

    pet = PetController(config)
    run_demo(pet)
    return pet.run()


if __name__ == "__main__":
    raise SystemExit(main())
