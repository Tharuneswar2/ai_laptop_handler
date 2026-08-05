"""
pet/event_handler.py — Event system for backend ↔ pet communication.

The backend emits events via PetEventBus signals.
The pet controller connects to those signals.
Clean decoupling — the backend never imports pet rendering code.
"""

import logging
from enum import Enum

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class PetState(str, Enum):
    """All possible pet animation states."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    WORKING = "working"
    SPEAKING = "speaking"
    HAPPY = "happy"
    SAD = "sad"
    SLEEPING = "sleeping"
    EXCITED = "excited"
    ERROR = "error"


class PetEmotion(str, Enum):
    """Emotion modifiers (independent of state)."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    CURIOUS = "curious"
    CONFUSED = "confused"
    SLEEPY = "sleepy"
    SURPRISED = "surprised"
    EXCITED = "excited"


class PetEventBus(QObject):
    """
    Qt signal-based event bus for pet communication.

    Usage from backend:
        bus = PetEventBus()
        bus.state_changed.emit("listening")
        bus.say_text.emit("Opening Chrome...")
    """

    # Core signals
    state_changed = Signal(str)       # PetState value
    say_text = Signal(str)            # text for speech bubble
    notification = Signal(str)        # floating notification text
    emotion_changed = Signal(str)     # PetEmotion value

    # Control signals
    hide_pet = Signal()
    show_pet = Signal()
    sleep_pet = Signal()
    wake_pet = Signal()
    move_pet = Signal(int, int)       # x, y coordinates

    def __init__(self, parent=None):
        super().__init__(parent)
        logger.info("PetEventBus initialized.")

    def emit_state(self, state: str) -> None:
        """Convenience method to emit a state change."""
        self.state_changed.emit(state)

    def emit_say(self, text: str) -> None:
        """Convenience method to show a speech bubble."""
        self.say_text.emit(text)

    def emit_notification(self, text: str) -> None:
        """Convenience method to show a notification."""
        self.notification.emit(text)
