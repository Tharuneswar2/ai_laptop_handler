"""
pet/ui/notification_widget.py — Transient toast notifications.

Shows brief system messages (download finished, pet changed, errors ...)
in a small stack anchored to the top-right of the pet window.  Each toast
fades in, stays for a configurable duration and fades out automatically.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QPropertyAnimation, QRectF, Qt, QTimer, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

logger = logging.getLogger(__name__)

TOAST_WIDTH = 230
TOAST_HEIGHT = 44
MAX_TOASTS = 3
GAP = 6


class _Toast(QWidget):
    """A single rounded notification chip."""

    def __init__(self, text: str, *, theme: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._text = text
        self._theme = theme
        self._colors = {
            "dark": {
                "background": "rgba(48, 52, 68, 240)",
                "border": "rgba(140, 160, 220, 110)",
                "text": "#F2F4FF",
            },
            "light": {
                "background": "rgba(255, 255, 255, 242)",
                "border": "rgba(150, 160, 200, 130)",
                "text": "#2A2E3F",
            },
        }[theme]

        self.setFixedSize(TOAST_WIDTH, TOAST_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        label = QLabel(text, self)
        label.setGeometry(14, 0, TOAST_WIDTH - 28, TOAST_HEIGHT)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        font = label.font()
        font.setPixelSize(12)
        label.setFont(font)
        label.setStyleSheet(f"color: {self._colors['text']}; background: transparent;")
        self._label = label

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

    def fade_to(self, opacity: float, ms: int = 250) -> QPropertyAnimation:
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setStartValue(self._effect.opacity())
        anim.setEndValue(opacity)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        return anim

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.setPen(QPen(QColor(self._colors["border"]), 1.0))
        painter.setBrush(QColor(self._colors["background"]))
        painter.drawPath(path)
        painter.end()


class NotificationWidget(QWidget):
    """
    Stack of toast notifications anchored near the pet window.

    Usage::

        notifications = NotificationWidget()
        notifications.attach_to(pet_window)
        notifications.notify("Download finished", duration=4.0)
    """

    def __init__(self, *, theme: str = "light", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._pet_window: QWidget | None = None
        self._toasts: list[_Toast] = []

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def attach_to(self, window: QWidget) -> None:
        """Anchor the notification stack to ``window`` (the pet window)."""
        self._pet_window = window
        window.moved_by_drag.connect(lambda _pos: self._reposition())

    def notify(self, text: str, *, duration: float = 4.0) -> None:
        """Show a toast notification that disappears automatically."""
        if self._pet_window is None:
            self.hide()
            return

        if len(self._toasts) >= MAX_TOASTS:
            oldest = self._toasts.pop(0)
            oldest.deleteLater()

        toast = _Toast(text, theme=self._theme, parent=self)
        toast.show()
        self._toasts.append(toast)
        self._relayout()

        fade_in = toast.fade_to(1.0)
        fade_in.start()

        QTimer.singleShot(int(duration * 1000), lambda t=toast: self._dismiss(t))

    # ─── Internals ─────────────────────────────────────────────────────

    def _dismiss(self, toast: _Toast) -> None:
        if toast not in self._toasts:
            return
        anim = toast.fade_to(0.0)
        anim.finished.connect(lambda t=toast: self._remove(t))
        anim.start()

    def _remove(self, toast: _Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.deleteLater()
        self._relayout()

    def _relayout(self) -> None:
        y = 0
        for toast in reversed(self._toasts):
            toast.move(0, y)
            y += toast.height() + GAP
        total_height = y - GAP if self._toasts else 0
        self.setFixedSize(TOAST_WIDTH, max(total_height, 1))
        self._reposition()

    def _reposition(self) -> None:
        if self._pet_window is None:
            return
        if not self.isVisible() and self._toasts:
            self.show()
            self.raise_()
        pet_geometry = self._pet_window.frameGeometry()
        x = pet_geometry.right() - self.width() + 1
        y = pet_geometry.top()
        self.move(QPoint(x, y))


__all__ = ["NotificationWidget"]
