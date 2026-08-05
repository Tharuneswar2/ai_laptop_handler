"""
pet/input/drag_manager.py — Dragging, clamping and position persistence.

The pet can be dragged across all monitors.  Animation pauses while
dragging (optional), the position is clamped to the visible desktop and
saved to a JSON file on release so it can be restored on startup.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, QRect, QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class DragManager(QObject):
    """
    Handles mouse drags for the pet window.

    Usage::

        drag = DragManager(window, config)
        drag.set_callbacks(on_start=..., on_end=...)
        # window: forward mousePressEvent/mouseMoveEvent/mouseReleaseEvent
    """

    drag_started = Signal()
    drag_finished = Signal(QPoint)  # final top-left position

    def __init__(
        self,
        widget: QWidget,
        *,
        position_path: Path,
        default_position: tuple[int, int] | None = None,
        pause_animation: bool = True,
    ) -> None:
        super().__init__(widget)
        self.widget = widget
        self._position_path = Path(position_path)
        self._default_position = default_position
        self._pause_animation = pause_animation

        self._dragging = False
        self._press_global: QPoint | None = None
        self._press_window: QPoint | None = None
        self._on_pause: Callable[[], None] | None = None
        self._on_resume: Callable[[], None] | None = None
        self._on_drag_end: Callable[[QPoint], None] | None = None

    # ─── Wiring ────────────────────────────────────────────────────────

    def set_callbacks(
        self,
        *,
        on_pause: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
        on_drag_end: Callable[[QPoint], None] | None = None,
    ) -> None:
        """Hook animation pause/resume and a drag-end callback."""
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_drag_end = on_drag_end

    # ─── Mouse events (forwarded by the window) ────────────────────────

    def mouse_press(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self._press_global = event.globalPosition().toPoint()
        self._press_window = self.widget.frameGeometry().topLeft()
        if self._pause_animation and self._on_pause:
            self._on_pause()
        self.drag_started.emit()
        event.accept()

    def mouse_move(self, event: QMouseEvent) -> None:
        if not self._dragging or self._press_global is None or self._press_window is None:
            return
        delta = event.globalPosition().toPoint() - self._press_global
        target = self._press_window + delta
        self.widget.move(self._clamp_to_screen(target))
        event.accept()

    def mouse_release(self, event: QMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._press_global = None
        self._press_window = None
        if self._pause_animation and self._on_resume:
            self._on_resume()
        position = self.widget.frameGeometry().topLeft()
        self.save_position(position)
        self.drag_finished.emit(position)
        if self._on_drag_end:
            self._on_drag_end(position)
        event.accept()

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    # ─── Position persistence ──────────────────────────────────────────

    def restore_position(self) -> QPoint | None:
        """Load the saved position (None when unavailable)."""
        if not self._position_path.exists():
            return None
        try:
            data = json.loads(self._position_path.read_text(encoding="utf-8"))
            return QPoint(int(data["x"]), int(data["y"]))
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Could not restore pet position: %s", exc)
            return None

    def save_position(self, position: QPoint) -> None:
        """Persist the pet position to disk."""
        try:
            self._position_path.parent.mkdir(parents=True, exist_ok=True)
            self._position_path.write_text(
                json.dumps({"x": position.x(), "y": position.y()}), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Could not save pet position: %s", exc)

    def default_anchor(self) -> QPoint:
        """Fallback position: bottom-right of the primary screen."""
        screen = QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        size = self.widget.size()
        return QPoint(geometry.right() - size.width() + 1, geometry.bottom() - size.height() + 1)

    # ─── Screen clamping ───────────────────────────────────────────────

    def clamp_to_screen(self) -> None:
        """Ensure the window is visible on some monitor (call on startup)."""
        self.widget.move(self._clamp_to_screen(self.widget.pos()))

    def _clamp_to_screen(self, position: QPoint) -> QPoint:
        size = self.widget.size()
        screen = QGuiApplication.screenAt(position)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        x = min(max(position.x(), geometry.left()), geometry.right() - size.width() + 1)
        y = min(max(position.y(), geometry.top()), geometry.bottom() - size.height() + 1)
        return QPoint(x, y)


__all__ = ["DragManager"]
