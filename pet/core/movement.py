"""
pet/core/movement.py — Screen wandering for the desktop pet.

Many Codex atlases ship dedicated movement rows (``running-left`` and
``running-right``).  The :class:`MovementController` makes the pet use
them: while idle it periodically walks a short distance along the bottom
of the screen (above the taskbar), animating the matching run row, then
returns to its idle animation.

It stops immediately when the pet leaves the idle state, gets dragged,
or the window is hidden.
"""

from __future__ import annotations

import logging
import random

from PySide6.QtCore import QPoint, QObject, QRect, QTimer
from PySide6.QtGui import QGuiApplication

from .animation_engine import AnimationEngine
from .state_machine import PetState

logger = logging.getLogger(__name__)


class MovementController(QObject):
    """
    Periodically walks the pet window along the bottom of the screen.

    Args:
        engine: The animation engine (its run rows are used while walking).
        window: The :class:`~pet.ui.pet_window.PetWindow` to move.
        interval_ms: Milliseconds between movement steps.
        step_px: Pixels moved per step.
        min_pause / max_pause: Seconds of idle before the next walk
            (random within the range; tests can pin them equal).
        min_distance / max_distance: Random walk length in pixels.
        rng: Optional ``random.Random`` instance (for deterministic tests).
    """

    def __init__(
        self,
        engine: AnimationEngine,
        window,
        *,
        interval_ms: int = 40,
        step_px: int = 2,
        min_pause: float = 20.0,
        max_pause: float = 60.0,
        min_distance: int = 150,
        max_distance: int = 500,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(engine)
        self._engine = engine
        self._window = window
        self._step_px = max(1, int(step_px))
        self._min_pause = max(0.0, float(min_pause))
        self._max_pause = max(self._min_pause, float(max_pause))
        self._min_distance = max(1, int(min_distance))
        self._max_distance = max(self._min_distance, int(max_distance))
        self._rng = rng or random.Random()

        self._enabled = True
        self._moving = False
        self._direction = 1  # +1 = right, -1 = left
        self._remaining = 0  # pixels left to walk
        self._pause_ticks = 1  # seconds until the next walk may start
        self._state = PetState.IDLE

        self._timer = QTimer(self)
        self._timer.setInterval(max(10, int(interval_ms)))
        self._timer.timeout.connect(self._step)

    # ─── Public control ────────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable wandering entirely."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self.stop()

    @property
    def is_moving(self) -> bool:
        """True while the pet is currently walking."""
        return self._moving

    def tick_second(self) -> None:
        """Called once per second: count down to the next walk (if idle)."""
        if not self._enabled or self._moving or self._state is not PetState.IDLE:
            return
        self._pause_ticks -= 1
        if self._pause_ticks <= 0:
            self._start_walk()

    def on_state_changed(self, state: PetState) -> None:
        """React to pet state changes: only wander while idle."""
        self._state = state
        if state is not PetState.IDLE:
            self.stop()

    def stop(self) -> None:
        """Abort any walk and restore the state animation."""
        if not self._moving:
            return
        self._moving = False
        self._timer.stop()
        self._engine.restore_state_animation()

    # ─── Internals ─────────────────────────────────────────────────────

    def _start_walk(self) -> None:
        if not self._enabled or self._moving or not self._window.isVisible():
            self._reschedule()
            return
        if not self._can_walk():
            self._reschedule()
            return

        geometry, floor_y = self._floor()
        x, w = self._window.pos().x(), self._window.width()
        left = geometry.left() + 4
        right = geometry.right() - w - 4

        # Prefer the direction that keeps us away from the screen edge.
        if x <= left + 8:
            direction = 1
        elif x >= right - 8:
            direction = -1
        else:
            direction = -1 if self._rng.random() < 0.5 else 1

        self._direction = direction
        self._remaining = self._rng.randint(self._min_distance, self._max_distance)
        self._floor_y = floor_y
        self._moving = True

        self._engine.play_animation("running-left" if direction < 0 else "running-right")
        self._timer.start()
        self._step()  # move immediately onto the floor
        self._reschedule()

    def _can_walk(self) -> bool:
        """True when the pack has run rows and the window is on screen."""
        frames = getattr(self._engine, "_frames", {})
        return "running-left" in frames and "running-right" in frames

    def _step(self) -> None:
        if not self._moving:
            return
        if not self._window.isVisible() or self._window.drag.is_dragging:
            self.stop()
            return

        geometry, floor_y = self._floor()
        x, y = self._window.pos().x(), self._window.pos().y()
        new_x = x + self._direction * self._step_px
        w = self._window.width()
        right_edge = geometry.right() - w
        if new_x < geometry.left() or new_x > right_edge:
            self.stop()
            return

        self._window.move_pet(QPoint(new_x, floor_y))
        self._remaining -= self._step_px
        if self._remaining <= 0:
            self.stop()

    def _floor(self) -> tuple[QRect, int]:
        """Available desktop geometry + the y of the bottom edge (floor)."""
        screen = QGuiApplication.screenAt(self._window.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
        return geometry, geometry.bottom() - self._window.height() + 1

    def _reschedule(self) -> None:
        self._pause_ticks = self._rng.randint(
            round(self._min_pause), round(self._max_pause)
        )


__all__ = ["MovementController"]
