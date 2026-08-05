"""
pet — Nova Desktop Pet Engine.

A modular, asset-driven desktop companion for the AI Laptop Voice Handler.
The pet engine is deliberately free of AI logic: it only renders sprite-sheet
animations and reacts to external events published by the assistant backend.

Pet packs follow the Codex pet-pack convention:

    pets/<pet-slug>--<author-slug>/
    ├── submission.json
    ├── pet.json
    └── spritesheet.webp

The engine discovers packs under ``pet/assets/pets/`` (see ``PetConfig.asset_root``)
and falls back to a procedurally drawn pet when no pack is available.

Public API:

    from pet import PetController

    pet = PetController()
    pet.start()
    pet.set_state("listening")
    pet.say("Opening VS Code")
    pet.notify("Download finished")
"""

from .config import PetConfig, load_config
from .core.event_bus import EventBus, PetEvent
from .core.state_machine import PetState
from .core.emotion_manager import PetEmotion
from .core.pet_controller import PetController
from .core.asset_loader import PetPack, PetPackError

__version__ = "2.0.0"
__all__ = [
    "PetConfig",
    "load_config",
    "PetController",
    "EventBus",
    "PetEvent",
    "PetState",
    "PetEmotion",
    "PetPack",
    "PetPackError",
    "__version__",
]
