"""
pet/core/pet_controller.py — Public API of the Desktop Pet Engine.

This is the only class the assistant backend needs to know about::

    pet = PetController()
    pet.start()

    pet.set_state("listening")
    pet.say("Opening VS Code")
    pet.notify("Download finished")
    pet.change_pet("cat")
    pet.sleep(); pet.wake()
    pet.hide(); pet.show()
    pet.move_to(100, 200)
    pet.set_scale(1.5)

Every method is safe to call from any thread — calls from backend threads
are marshalled onto the Qt GUI thread before touching widgets.  State
changes are also published on the shared event bus
(:class:`~pet.core.event_bus.EventBus`), so the backend can stay fully
decoupled.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from ..config import PetConfig, ensure_data_dir
from .asset_loader import AssetLoader, PetPack, PetPackError
from .emotion_manager import EmotionManager, PetEmotion
from .event_bus import EventBus, PetEvent, set_thread_hook
from .fallback_pet import build_fallback_pack
from .movement import MovementController
from .state_machine import PetState, PetStateMachine, StateMachineOptions
from ..ui.notification_widget import NotificationWidget
from ..ui.pet_window import PetWindow
from ..ui.speech_bubble import SpeechBubble
from .animation_engine import AnimationEngine
from .renderer import PetRenderer

logger = logging.getLogger(__name__)


class _Invoker(QObject):
    """Marshals callables onto the thread owning this object.

    PySide6 queued signals with an ``object`` payload deliver Python
    callables reliably across threads (unlike ``Q_ARG``-based invokeMethod).
    """

    invoke_requested = Signal(object)

    @Slot(object)
    def _run(self, fn: Any) -> None:  # fn: Callable[[], None]
        fn()


class PetController(QObject):
    """
    Front controller for the pet engine.

    Wires together the event bus, state machine, emotion manager, animation
    engine, renderer, window, speech bubble, notifications and dragging.
    """

    def __init__(self, config: PetConfig | None = None) -> None:
        super().__init__()
        self.config = config or PetConfig()
        ensure_data_dir(self.config)

        self.app: QApplication = QApplication.instance() or QApplication(sys.argv)
        self._gui_thread = self.app.thread()

        # Event bus + thread marshalling hook.
        self.event_bus = EventBus()
        self._invoker = _Invoker()
        self._invoker.moveToThread(self._gui_thread)
        self._invoker.invoke_requested.connect(
            self._invoker._run, Qt.ConnectionType.QueuedConnection
        )
        set_thread_hook(self._marshal)

        # Engine pieces.
        self.loader = AssetLoader(self.config.asset_root, self.config.pets_dir)
        self.emotions = EmotionManager()
        self.state_machine = PetStateMachine(
            StateMachineOptions(state_timeout=self.config.state_timeout)
        )
        self.anim_engine = AnimationEngine(
            self.emotions,
            default_fps=self.config.fps,
            scale=self.config.scale,
        )

        self._pack: PetPack | None = None
        self._window: PetWindow | None = None
        self._renderer: PetRenderer | None = None
        self._bubble: SpeechBubble | None = None
        self._notifications: NotificationWidget | None = None
        self.movement: MovementController | None = None

        # Timers.
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)
        self._auto_sleep_timer = QTimer(self)
        self._auto_sleep_timer.setSingleShot(True)
        self._auto_sleep_timer.timeout.connect(self.sleep)

        # Wire FSM -> animation + event bus.
        self.state_machine.add_listener(self._on_state_changed)
        self.anim_engine.animation_finished.connect(self._on_animation_finished)
        self.emotions.add_listener(lambda _prev, cur: self.event_bus.publish(PetEvent.PET_EMOTION, cur.value))

    # ─── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Build the window (if needed), load the default pet and show it.
        Non-blocking; returns immediately so it can be embedded in an
        existing Qt application.
        """
        # The window must exist first: it supplies the device pixel ratio
        # that the animation engine uses to build its pixmaps.
        self._ensure_window()
        self._load_pack(self.config.default_pet)
        self._window.show_pet()
        self._tick_timer.start()
        self._reset_auto_sleep()
        logger.info("Pet started (%s)", self._pack.id if self._pack else "none")

    def run(self) -> int:
        """Start the pet and block in the Qt event loop (standalone mode)."""
        self.start()
        return self.app.exec()

    def stop(self) -> None:
        """Hide the window and stop timers (leaves the app running)."""
        if self.movement is not None:
            self.movement.stop()
        if self._window is not None:
            self._window.hide_pet()
        self._tick_timer.stop()
        self._auto_sleep_timer.stop()

    def quit(self) -> None:
        """Full shutdown: stop and quit the Qt application."""
        self.stop()
        self.app.quit()

    # ─── Pet selection ─────────────────────────────────────────────────

    def list_pets(self) -> list[dict[str, str]]:
        """Installed pet packs (id + path), for UI pickers."""
        return self.loader.list_pets()

    def load_pet(self, pet: str) -> bool:
        """Alias of :meth:`change_pet` (kept for API symmetry)."""
        return self.change_pet(pet)

    def change_pet(self, pet: str) -> bool:
        """
        Switch to another pet pack (by id, folder name or path).

        Falls back to the built-in pet when the pack is missing.
        Returns True when a pack is loaded (incl. the fallback).
        """
        if QThread.currentThread() is self.app.thread():
            return self._load_pack(pet)

        done = threading.Event()
        result: list[bool] = []

        def _load() -> None:
            try:
                result.append(self._load_pack(pet))
            finally:
                done.set()

        self._marshal(_load)
        done.wait()
        return bool(result and result[0])

    @property
    def pet_id(self) -> str | None:
        """Id of the currently loaded pet pack."""
        return self._pack.id if self._pack else None

    # ─── State / emotion ───────────────────────────────────────────────

    def set_state(self, state: str | PetState, *, force: bool = False) -> bool:
        """
        Request a pet state: "idle" | "listening" | "thinking" | "working"
        | "speaking" | "happy" | "sleeping" | "error".
        """
        target = self._parse_state(state)
        return self._marshal_or_run(lambda: self.state_machine.transition(target, force=force))

    def set_emotion(self, emotion: str | PetEmotion) -> None:
        """Set an emotion: neutral | happy | curious | confused | sleepy | surprised | excited."""
        parsed = self.emotions.parse(emotion)
        self._marshal_or_run(lambda: self.emotions.set(parsed))

    # ─── Speech / notifications ────────────────────────────────────────

    def say(self, text: str, *, duration: float | None = None) -> None:
        """Show a speech bubble with ``text`` (typewriter effect)."""
        duration = duration if duration is not None else self.config.speech_bubble_duration
        self._marshal_or_run(
            lambda: self._with_bubble(lambda b: b.show_message(text, duration=duration, typing_ms=self.config.speech_bubble_typing_ms))
        )
        self.event_bus.publish(PetEvent.PET_SAY, {"text": text})

    def notify(self, text: str, *, duration: float | None = None) -> None:
        """Show a toast notification."""
        duration = duration if duration is not None else self.config.notification_duration
        self._marshal_or_run(
            lambda: self._with_notifications(lambda n: n.notify(text, duration=duration))
        )
        self.event_bus.publish(PetEvent.PET_NOTIFY, {"text": text})

    # ─── Visibility / sleep ────────────────────────────────────────────

    def show(self) -> None:
        """Show the pet window."""
        self._marshal_or_run(self._show_impl)
        self.event_bus.publish(PetEvent.PET_SHOW)

    def hide(self) -> None:
        """Hide the pet window (playback stops -> low CPU)."""
        self._marshal_or_run(self._hide_impl)
        self.event_bus.publish(PetEvent.PET_HIDE)

    def sleep(self) -> None:
        """Put the pet to sleep (slow, sleepy animation)."""
        def _do() -> None:
            self.state_machine.transition(PetState.SLEEPING, force=True)
            self.emotions.set(PetEmotion.SLEEPY)
            self._auto_sleep_timer.stop()
        self._marshal_or_run(_do)
        self.event_bus.publish(PetEvent.PET_SLEEP)

    def wake(self) -> None:
        """Wake the pet up (back to idle)."""
        def _do() -> None:
            self.state_machine.transition(PetState.IDLE, force=True)
            self.emotions.reset()
            self._reset_auto_sleep()
        self._marshal_or_run(_do)
        self.event_bus.publish(PetEvent.PET_WAKE)

    # ─── Geometry ──────────────────────────────────────────────────────

    def move_to(self, x: int, y: int) -> None:
        """Move the pet window to (x, y), clamped to the desktop."""
        self._marshal_or_run(lambda: self._window.move_pet(QPoint(x, y)) if self._window else None)

    def set_scale(self, scale: float) -> None:
        """Change the sprite scale (e.g. 1.5 = 50% bigger)."""
        scale = max(0.1, float(scale))
        self._marshal_or_run(
            lambda: (self._renderer.set_scale(scale), self._window.resize(self._renderer.size()))
            if self._renderer and self._window
            else None
        )

    # ─── Internal wiring ───────────────────────────────────────────────

    def _ensure_window(self) -> None:
        if self._window is not None:
            return
        dpr = self.app.primaryScreen().devicePixelRatio() if self.app.primaryScreen() else 1.0
        self.anim_engine._dpr = dpr
        self._renderer = PetRenderer(
            self.anim_engine,
            self.emotions,
            frame_size=self.config.pet_size,
            scale=self.config.scale,
        )
        self._renderer.set_transition_ms(self.config.transition_ms)

        self._window = PetWindow(self._renderer, self.anim_engine, self.config)
        self._window.moved_by_drag.connect(self._on_drag_end)

        self.movement = MovementController(
            self.anim_engine,
            self._window,
            interval_ms=self.config.walk_interval_ms,
            step_px=self.config.walk_step_px,
            min_pause=self.config.min_walk_pause,
            max_pause=self.config.max_walk_pause,
            min_distance=self.config.min_walk_distance,
            max_distance=self.config.max_walk_distance,
        )
        self.movement.set_enabled(self.config.movement_enabled)

        self._bubble = SpeechBubble(theme=self.config.theme)
        self._bubble.attach_to(self._window)
        self._notifications = NotificationWidget(theme=self.config.theme)
        self._notifications.attach_to(self._window)

    def _load_pack(self, pet: str) -> bool:
        try:
            pack = self.loader.load_pack(pet)
        except PetPackError as exc:
            logger.warning("Falling back to built-in pet (%s)", exc)
            pack = build_fallback_pack()
        if pack.id == (self._pack.id if self._pack else None):
            return True
        self._pack = pack
        self.anim_engine.set_pack(pack, scale=self.config.scale)
        self.state_machine.reset()
        self.emotions.reset()
        if self.movement is not None:
            self.movement.on_state_changed(self.state_machine.state)
        if self._window is not None:
            self._window.resize(self._renderer.size())
            self._window.show_pet()
        logger.info("Loaded pet pack: %s (%s)", pack.display_name, pack.id)
        self.event_bus.publish(PetEvent.PET_CHANGE_PET, {"id": pack.id, "name": pack.display_name})
        return True

    def _on_state_changed(self, previous: PetState, current: PetState) -> None:
        self.anim_engine.set_state(current)
        if self.movement is not None:
            self.movement.on_state_changed(current)
        self._reset_auto_sleep()
        self.event_bus.publish(_STATE_EVENT.get(current, PetEvent.PET_IDLE), {"state": current.value})

    def _on_animation_finished(self) -> None:
        self.state_machine.on_animation_finished()

    def _on_drag_end(self, position: QPoint) -> None:
        self.event_bus.publish(PetEvent.PET_DRAG_END, {"x": position.x(), "y": position.y()})

    def _on_tick(self) -> None:
        self.state_machine.tick(1.0)
        if self.movement is not None:
            self.movement.tick_second()

    def _reset_auto_sleep(self) -> None:
        if self.state_machine.state is PetState.IDLE:
            self._auto_sleep_timer.start(int(self.config.autosleep_timeout * 1000))
        else:
            self._auto_sleep_timer.stop()

    def _show_impl(self) -> None:
        if self._window is not None:
            self._window.show_pet()
            self.anim_engine.resume()

    def _hide_impl(self) -> None:
        if self.movement is not None:
            self.movement.stop()
        if self._window is not None:
            self._window.hide_pet()

    def _with_bubble(self, fn) -> None:
        if self._bubble is not None:
            fn(self._bubble)

    def _with_notifications(self, fn) -> None:
        if self._notifications is not None:
            fn(self._notifications)

    def _parse_state(self, state: str | PetState) -> PetState:
        if isinstance(state, PetState):
            return state
        try:
            return PetState(str(state).lower())
        except ValueError:
            logger.warning("Unknown state %r, using idle", state)
            return PetState.IDLE

    def _marshal_or_run(self, fn) -> Any:
        """Run ``fn`` now when on the GUI thread, else queue it."""
        if QThread.currentThread() is self.app.thread():
            return fn()
        self._marshal(fn)
        return None

    def _marshal(self, fn) -> None:
        """Queue ``fn`` onto the Qt GUI thread (thread-safe)."""
        self._invoker.invoke_requested.emit(fn)


_STATE_EVENT: dict[PetState, PetEvent] = {
    PetState.IDLE: PetEvent.PET_IDLE,
    PetState.LISTENING: PetEvent.PET_LISTENING,
    PetState.THINKING: PetEvent.PET_THINKING,
    PetState.WORKING: PetEvent.PET_WORKING,
    PetState.SPEAKING: PetEvent.PET_SPEAKING,
    PetState.HAPPY: PetEvent.PET_HAPPY,
    PetState.SLEEPING: PetEvent.PET_SLEEP,
    PetState.ERROR: PetEvent.PET_ERROR,
}

__all__ = ["PetController"]
