"""
pet/drag_manager.py — Drag support with position persistence.

Handles mouse press/move/release for dragging the pet window.
Pauses idle animation during drag, saves position on drop,
and clamps to screen bounds.
"""

import logging

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from pet.config import PetConfig

logger = logging.getLogger(__name__)


class DragManager:
    """Manages dragging behavior for the pet window."""

    def __init__(self, widget: QWidget, config: PetConfig):
        self._widget = widget
        self._config = config
        self._dragging = False
        self._drag_offset = QPoint()
        self._on_drag_start = None
        self._on_drag_end = None

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def set_callbacks(self, on_start=None, on_end=None) -> None:
        """Set optional callbacks for drag start/end."""
        self._on_drag_start = on_start
        self._on_drag_end = on_end

    def handle_mouse_press(self, event: QMouseEvent) -> None:
        """Call from the widget's mousePressEvent."""
        if not self._config.draggable:
            return
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self._widget.frameGeometry().topLeft()
            if self._on_drag_start:
                self._on_drag_start()

    def handle_mouse_move(self, event: QMouseEvent) -> None:
        """Call from the widget's mouseMoveEvent."""
        if not self._dragging:
            return
        new_pos = event.globalPosition().toPoint() - self._drag_offset
        # Clamp to screen bounds
        screen = self._widget.screen()
        if screen:
            geo = screen.availableGeometry()
            x = max(geo.left(), min(new_pos.x(), geo.right() - self._widget.width()))
            y = max(geo.top(), min(new_pos.y(), geo.bottom() - self._widget.height()))
            new_pos = QPoint(x, y)
        self._widget.move(new_pos)

    def handle_mouse_release(self, event: QMouseEvent) -> None:
        """Call from the widget's mouseReleaseEvent."""
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            # Save position
            pos = self._widget.pos()
            self._config.save_position(pos.x(), pos.y())
            logger.debug("Pet position saved: (%d, %d)", pos.x(), pos.y())
            if self._on_drag_end:
                self._on_drag_end()
