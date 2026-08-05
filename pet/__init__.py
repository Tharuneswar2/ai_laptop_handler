"""
pet — Desktop Pet Engine for the AI Voice Assistant.

A cute, animated desktop companion that visualizes
the assistant's current state (listening, thinking, speaking, etc.).
Contains zero AI logic — it only renders visual feedback.

Usage:
    from pet.pet_controller import PetController

    pet = PetController()
    pet.start()
    pet.set_state("listening")
    pet.say("Opening Chrome...")
"""

from pet.pet_controller import PetController
from pet.event_handler import PetEventBus, PetState

__all__ = ["PetController", "PetEventBus", "PetState"]
