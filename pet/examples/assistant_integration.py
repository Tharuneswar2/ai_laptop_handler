"""
examples/assistant_integration.py — How the AI backend controls the pet.

Two coupling levels are supported:

1. Direct API calls (simplest)
   ``pet.set_state("working"); pet.say("Opening VS Code")``

2. Event bus (loose coupling)
   The backend publishes semantic events; the engine reacts and also
   republishes state changes, so other components can observe the pet.

This example simulates a backend thread (e.g. a FastAPI request handler or
the voice loop) calling the pet API from a non-GUI thread — everything is
thread-safe and marshalled onto the Qt main thread automatically.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pet import PetController, PetEvent


def backend_worker(pet: PetController) -> None:
    """
    Runs on a backend thread (like the assistant's processing pipeline).

    In the real app this lives inside your intent router, e.g.:

        result = route(intent)        # tools/...
        pet.set_state("speaking")
        pet.say(result.message)
    """
    # Wake word detected
    pet.set_state("listening")
    pet.say("I'm listening...")
    time.sleep(1.2)

    # Command received -> think -> work -> speak
    pet.set_state("thinking")
    time.sleep(0.8)
    pet.set_state("working")
    pet.say("Opening VS Code")
    time.sleep(1.5)

    pet.set_state("speaking")
    pet.set_emotion("happy")
    pet.say("VS Code is now open!")
    time.sleep(2.0)

    # Error handling
    pet.set_state("error")
    pet.set_emotion("surprised")
    pet.say("That folder doesn't exist.")
    pet.notify("Error: folder not found")
    time.sleep(2.5)

    # Back to idle
    pet.set_state("idle")
    pet.set_emotion("neutral")

    # Try switching pets (a pack installed later, e.g. via codexpet.top)
    pets = [entry["id"] for entry in pet.list_pets()]
    if len(pets) > 1:
        pet.change_pet(pets[1])
        pet.notify(f"Pet changed to {pets[1]}")
        time.sleep(2.0)
        pet.change_pet(pet.config.default_pet)

    pet.say("Back to normal!")
    time.sleep(1.0)

    # Finish the demo.
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, pet.quit)


def main() -> int:
    pet = PetController()

    # Optional: observe pet events from anywhere.
    def on_event(event: PetEvent, payload: object) -> None:
        if event in (PetEvent.PET_SAY, PetEvent.PET_NOTIFY):
            print(f"[event bus] {event.value}: {payload}")

    pet.event_bus.subscribe(PetEvent.PET_SAY, on_event)
    pet.event_bus.subscribe(PetEvent.PET_NOTIFY, on_event)

    pet.start()

    # The backend would start this thread; the pet engine runs in the Qt loop.
    threading.Thread(target=backend_worker, args=(pet,), daemon=True).start()

    return pet.app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
