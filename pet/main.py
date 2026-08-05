"""
pet/main.py — Standalone entry point and demo runner.

Usage::

    python -m pet                       # start the default pet
    python -m pet --pet cat             # start a specific pet pack
    python -m pet --list                # show installed pet packs
    python -m pet --demo                # run the automated state demo
    python -m pet --scale 1.5           # bigger pet
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pet.config import PetConfig, load_config  # noqa: E402
from pet.core.pet_controller import PetController  # noqa: E402

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pet",
        description="Nova Desktop Pet Engine (Codex pet-pack compatible)",
    )
    parser.add_argument("--pet", default=None, help="pet pack id to load")
    parser.add_argument("--list", action="store_true", help="list installed pet packs")
    parser.add_argument("--demo", action="store_true", help="run the automated demo sequence")
    parser.add_argument("--no-demo", action="store_true", help="do NOT run the demo sequence")
    parser.add_argument("--scale", type=float, default=None, help="sprite scale (0.5 - 3.0)")
    parser.add_argument("--config", default=None, help="path to a JSON config file")
    return parser


def run_demo(pet: PetController) -> None:
    """Drive the pet through every state so its behaviour is visible."""
    from PySide6.QtCore import QTimer

    steps: list[tuple[str, str, str]] = [
        ("listening", "neutral", "I'm listening... say something!"),
        ("thinking", "curious", "Hmm, let me think about that..."),
        ("working", "neutral", "Opening VS Code"),
        ("speaking", "happy", "Done! Anything else? 😊"),
        ("happy", "excited", "Yay! Task completed!"),
        ("sleeping", "sleepy", "zzz..."),
        ("working", "confused", "Hmm, that didn't work. Retrying..."),
        ("error", "surprised", "Oops! Something went wrong."),
        ("idle", "neutral", ""),
    ]

    def play(index: int) -> None:
        if index >= len(steps):
            pet.wake()
            pet.set_state("idle")
            pet.notify("Demo finished — grab me and drag me around!")
            return
        state, emotion, message = steps[index]
        pet.set_emotion(emotion)
        if state == "sleeping":
            pet.sleep()
        else:
            pet.wake()
            pet.set_state(state)
        if message:
            pet.say(message, duration=4.0)
        pet.notify(f"State: {state}")
        QTimer.singleShot(3800, lambda i=index: play(i + 1))

    QTimer.singleShot(1200, lambda: play(0))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")

    config = load_config(args.config)
    if args.pet:
        config = config.with_defaults(default_pet=args.pet)
    if args.scale is not None:
        config = config.with_defaults(scale=args.scale)

    pet = PetController(config)

    if args.list:
        for entry in pet.list_pets():
            print(f"  {entry['id']:<40} {entry['dir']}")
        return 0

    demo = args.demo or not args.no_demo
    if demo:
        run_demo(pet)
    else:
        pet.notify("Nova pet online")

    return pet.run()


if __name__ == "__main__":
    raise SystemExit(main())
