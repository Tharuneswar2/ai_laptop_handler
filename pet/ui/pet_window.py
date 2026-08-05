"""
pet/ui/pet_window.py — The transparent desktop window hosting the pet.

Window characteristics:
  * frameless, translucent background
  * always on top (configurable)
  * hidden from the taskbar (Qt.Tool, configurable)
  * drag support via :class:`~pet.input.drag_manager.DragManager`
  * remembers its position and clamps to the visible desktop
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from ..config import PetConfig
from ..core.animation_engine import AnimationEngine
from ..core.renderer import PetRenderer
from ..input.drag_manager import DragManager

logger = logging.getLogger(__name__)


class PetWindow(QWidget):
    """The always-on-top desktop widget that displays the pet."""

    moved_by_drag = Signal(QPoint)

    def __init__(
        self,
        renderer: PetRenderer,
        engine: AnimationEngine,
        config: PetConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.renderer = renderer
        self.engine = engine

        # Frameless, translucent, desktop-overlay flags.
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if config.always_on_top is False:
            flags = Qt.WindowType.FramelessWindowHint
        if not config.show_in_taskbar:
            flags |= Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        if config.opacity < 1.0:
            self.setWindowOpacity(config.opacity)

        # Layout: the renderer fills the window.
        renderer.setParent(self)
        self.resize(renderer.size())
        renderer.show()

        # Dragging.
        self.drag = DragManager(
            self,
            position_path=config.position_path,
            default_position=config.default_position,
            pause_animation=True,
        )
        self.drag.set_callbacks(
            on_pause=engine.pause,
            on_resume=engine.resume,
        )
        self.drag.drag_finished.connect(self.moved_by_drag)

        self._restore_position()

    # ─── Mouse forwarding ──────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.drag.mouse_press(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.drag.mouse_move(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.drag.mouse_release(event)

    # ─── Visibility ────────────────────────────────────────────────────

    def show_pet(self) -> None:
        """Show the window, clamped to a visible monitor."""
        self.drag.clamp_to_screen()
        self.show()

    def hide_pet(self) -> None:
        """Hide the window and pause playback (low CPU)."""
        self.hide()
        self.engine.stop()

    def move_pet(self, position: QPoint) -> None:
        """Move the window and keep it on screen."""
        self.move(self.drag._clamp_to_screen(position))

    # ─── Position persistence ──────────────────────────────────────────

    def _restore_position(self) -> None:
        saved = self.drag.restore_position()
        if saved is not None:
            self.move(saved)
        elif self.config.default_position is not None:
            self.move(QPoint(*self.config.default_position))
        else:
            self.move(self.drag.default_anchor())
        self.drag.clamp_to_screen()


__all__ = ["PetWindow"]
