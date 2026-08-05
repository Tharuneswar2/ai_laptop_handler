"""
pet/pet_controller.py — Main Public API Controller for the Desktop Pet Engine.

Coordinates the QApplication, window, animation manager, emotion manager,
drag manager, event bus, and speech bubble.

Provides a clean, fully-typed API that the AI backend can call directly:
    pet = PetController()
    pet.start()
    pet.set_state("listening")
    pet.say("Opening Chrome...")
"""

import sys
import logging
from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtWidgets import QApplication

from pet.config import PetConfig
from pet.event_handler import PetEventBus, PetState, PetEmotion
from pet.emotion_manager import EmotionManager
from pet.animation_manager import AnimationManager
from pet.drag_manager import DragManager
from pet.pet_window import PetWindow
from pet.speech_bubble import SpeechBubble

logger = logging.getLogger(__name__)


class PetController(QObject):
    """
    Public Controller API for Desktop Pet.
    Can run inside an existing PySide6 QApplication or initialize its own event loop.
    """

    def __init__(self, config: PetConfig = None):
        super().__init__()
        self.config = config or PetConfig()

        # Ensure QApplication instance exists
        self.app = QApplication.instance()
        if not self.app:
            self.app = QApplication(sys.argv)
            logger.info("Initialized new QApplication for Desktop Pet.")

        # Core Managers
        self.event_bus = PetEventBus()
        self.emotion_mgr = EmotionManager()
        self.anim_mgr = AnimationManager(self.config, self.emotion_mgr)

        # Window & Dragging
        self.drag_mgr = DragManager(None, self.config)
        self.window = PetWindow(self.config, self.anim_mgr, self.drag_mgr)
        self.drag_mgr._widget = self.window

        # Drag Callbacks
        self.drag_mgr.set_callbacks(
            on_start=self._on_drag_start,
            on_end=self._on_drag_end
        )

        # Speech Bubble
        self.bubble = SpeechBubble(self.config, self.window)

        # Auto-sleep timer
        self.auto_sleep_timer = QTimer(self)
        self.auto_sleep_timer.setSingleShot(True)
        self.auto_sleep_timer.timeout.connect(self.sleep)

        # Connect Event Bus Signals
        self._wire_signals()

        self._previous_state_before_drag = PetState.IDLE

    def _wire_signals(self) -> None:
        """Wire event bus signals to internal handlers."""
        self.event_bus.state_changed.connect(self._on_bus_state_changed)
        self.event_bus.say_text.connect(self._on_bus_say)
        self.event_bus.notification.connect(self._on_bus_notification)
        self.event_bus.emotion_changed.connect(self._on_bus_emotion_changed)
        self.event_bus.hide_pet.connect(self.hide)
        self.event_bus.show_pet.connect(self.show)
        self.event_bus.sleep_pet.connect(self.sleep)
        self.event_bus.wake_pet.connect(self.wake)
        self.event_bus.move_pet.connect(self.move_to)

    # ─── Public API ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Show pet window and start rendering."""
        self.window.show()
        self._reset_auto_sleep_timer()
        logger.info("Desktop Pet Engine started.")

    def set_state(self, state: str) -> None:
        """
        Set animation state.
        Supported: idle, listening, thinking, working, speaking, happy, sad, sleeping, excited, error
        """
        self._reset_auto_sleep_timer()
        self.anim_mgr.set_state(state)

    def set_emotion(self, emotion: str) -> None:
        """
        Set emotion modifier.
        Supported: neutral, happy, curious, confused, sleepy, surprised, excited
        """
        self.emotion_mgr.set_emotion(emotion)

    def say(self, text: str, duration_sec: float = None) -> None:
        """
        Show speech bubble text.
        Automatically switches state to 'speaking' unless already working/happy.
        """
        self._reset_auto_sleep_timer()
        duration_ms = int(duration_sec * 1000) if duration_sec else None

        if self.anim_mgr.current_state not in (PetState.WORKING, PetState.HAPPY, PetState.ERROR):
            self.set_state(PetState.SPEAKING)

        self.bubble.show_text(text, duration_ms)

    def show_notification(self, text: str) -> None:
        """Show floating notification banner above pet."""
        self.say(f"🔔 {text}", duration_sec=3.0)

    def move_to(self, x: int, y: int) -> None:
        """Move pet window to coordinates."""
        self.window.move(x, y)
        self.config.save_position(x, y)

    def hide(self) -> None:
        """Hide pet window & speech bubble."""
        self.bubble.hide_bubble()
        self.window.hide()

    def show(self) -> None:
        """Show pet window."""
        self.window.show()

    def sleep(self) -> None:
        """Put pet to sleep state."""
        self.bubble.hide_bubble()
        self.anim_mgr.set_state(PetState.SLEEPING)
        self.emotion_mgr.set_emotion(PetEmotion.SLEEPY)
        logger.info("Pet is sleeping Zzz...")

    def wake(self) -> None:
        """Wake pet from sleep."""
        self.emotion_mgr.reset()
        self.anim_mgr.set_state(PetState.IDLE)
        self.say("Good day!", duration_sec=2.0)
        self._reset_auto_sleep_timer()

    def process_events(self) -> None:
        """Process pending Qt events (useful when embedding in async/other loops)."""
        if self.app:
            self.app.processEvents()

    # ─── Internal Event Bus Slots ────────────────────────────────────────

    @Slot(str)
    def _on_bus_state_changed(self, state: str) -> None:
        self.set_state(state)

    @Slot(str)
    def _on_bus_say(self, text: str) -> None:
        self.say(text)

    @Slot(str)
    def _on_bus_notification(self, text: str) -> None:
        self.show_notification(text)

    @Slot(str)
    def _on_bus_emotion_changed(self, emotion: str) -> None:
        self.set_emotion(emotion)

    def _on_drag_start(self) -> None:
        self._previous_state_before_drag = self.anim_mgr.current_state
        self.bubble.hide_bubble()
        self.anim_mgr.set_state(PetState.EXCITED)

    def _on_drag_end(self) -> None:
        self.anim_mgr.set_state(self._previous_state_before_drag.value)
        self._reset_auto_sleep_timer()

    def _reset_auto_sleep_timer(self) -> None:
        if self.config.sleep_after_idle_ms > 0:
            self.auto_sleep_timer.start(self.config.sleep_after_idle_ms)
