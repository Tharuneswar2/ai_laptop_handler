"""
pet/ui/speech_bubble.py — Floating speech bubble for assistant messages.

Features: rounded corners, drop shadow, auto sizing with word wrapping,
a typewriter reveal effect, fade in/out, emoji support and a configurable
lifetime.  The bubble is its own top-level window so it can float above the
pet and follows the pet as it is dragged around.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

logger = logging.getLogger(__name__)

BUBBLE_PADDING_X = 16
BUBBLE_PADDING_Y = 10
MAX_BUBBLE_WIDTH = 320
MIN_BUBBLE_WIDTH = 60
BUBBLE_FONT_PIXEL = 13


class SpeechBubble(QWidget):
    """
    A transient speech bubble shown above the pet.

    Usage::

        bubble = SpeechBubble(config)
        bubble.attach_to(pet_window)
        bubble.show_message("Opening VS Code", duration=6.0)
    """

    def __init__(self, *, theme: str = "light", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._colors = self._theme_colors(theme)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._label.font()
        font.setPixelSize(BUBBLE_FONT_PIXEL)
        self._label.setFont(font)
        self._label.setStyleSheet(
            f"color: {self._colors['text']}; background: transparent; padding: {BUBBLE_PADDING_Y}px {BUBBLE_PADDING_X}px;"
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 90))
        self._label.setGraphicsEffect(shadow)

        # Typing effect.
        self._full_text = ""
        self._visible_chars = 0
        self._type_timer = QTimer(self)
        self._type_timer.timeout.connect(self._type_tick)

        # Lifetime + fade-out.
        self._life_timer = QTimer(self)
        self._life_timer.setSingleShot(True)
        self._life_timer.timeout.connect(self.fade_out)

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(30)
        self._fade_timer.timeout.connect(self._fade_tick)
        self._fade_opacity = 1.0
        self._fade_direction = 0

        self._pet_window: QWidget | None = None
        self.hide()

    # ─── Attachment ────────────────────────────────────────────────────

    def attach_to(self, window: QWidget) -> None:
        """Make the bubble follow ``window`` (the pet window)."""
        self._pet_window = window
        window.moved_by_drag.connect(lambda _pos: self._reposition())

    # ─── Public API ────────────────────────────────────────────────────

    def show_message(
        self,
        text: str,
        *,
        duration: float = 6.0,
        typing_ms: int = 18,
    ) -> None:
        """Display ``text`` with a typewriter effect, then fade out."""
        self._full_text = text
        self._visible_chars = 0
        self._layout_bubble(text)

        self._fade_opacity = 0.0
        self._fade_direction = 1
        self.show()
        self.raise_()
        self._fade_timer.start()

        self._type_timer.start(max(typing_ms, 1))
        self._life_timer.start(int(duration * 1000))

    def clear(self) -> None:
        """Instantly remove the bubble."""
        self._type_timer.stop()
        self._life_timer.stop()
        self._fade_timer.stop()
        self.hide()

    def fade_out(self) -> None:
        """Fade the bubble out over ~300 ms."""
        self._type_timer.stop()
        self._fade_direction = -1
        self._fade_timer.start()

    # ─── Painting ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(6, 6, -6, -8)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)

        # Tail pointing down toward the pet.
        tail_w, tail_h = 14, 8
        tail_x = self.width() / 2 - tail_w / 2
        path.moveTo(tail_x, rect.bottom() + 1)
        path.lineTo(tail_x + tail_w / 2, rect.bottom() + tail_h)
        path.lineTo(tail_x + tail_w, rect.bottom() + 1)
        path.closeSubpath()

        painter.setPen(QPen(QColor(self._colors["border"]), 1.5))
        painter.setBrush(QColor(self._colors["background"]))
        painter.drawPath(path)
        painter.end()

    # ─── Internals ─────────────────────────────────────────────────────

    def _type_tick(self) -> None:
        self._visible_chars += 2
        self._label.setText(self._full_text[: self._visible_chars])
        if self._visible_chars >= len(self._full_text):
            self._type_timer.stop()
            self._label.setText(self._full_text)

    def _fade_tick(self) -> None:
        self._fade_opacity += 0.12 * self._fade_direction
        if self._fade_opacity <= 0.0:
            self._fade_opacity = 0.0
            self.hide()
            self._fade_timer.stop()
            return
        if self._fade_opacity >= 1.0:
            self._fade_opacity = 1.0
            self._fade_timer.stop()
            return
        self.setWindowOpacity(self._fade_opacity)

    def _layout_bubble(self, text: str) -> None:
        metrics = QFontMetrics(self._label.font())
        # Measure the widest line after wrapping to auto-size the bubble.
        words = text.split() or [""]
        lines: list[str] = []
        current = ""
        for word in words:
            probe = f"{current} {word}".strip()
            if metrics.horizontalAdvance(probe) <= MAX_BUBBLE_WIDTH - BUBBLE_PADDING_X * 2:
                current = probe
            else:
                lines.append(current)
                current = word
        lines.append(current)

        width = max(
            MIN_BUBBLE_WIDTH,
            min(MAX_BUBBLE_WIDTH, max(metrics.horizontalAdvance(line) for line in lines) + BUBBLE_PADDING_X * 2),
        )
        height = len(lines) * metrics.height() + BUBBLE_PADDING_Y * 2
        self.setFixedSize(width, height + 8)  # +8 for the tail
        self._label.setGeometry(0, 0, width, height)

        self._reposition()

    def _reposition(self) -> None:
        if self._pet_window is None or not self.isVisible():
            return
        pet_geometry = self._pet_window.frameGeometry()
        x = pet_geometry.center().x() - self.width() // 2
        y = pet_geometry.top() - self.height() - 4
        self.move(QPoint(x, y))

    def _theme_colors(self, theme: str) -> dict[str, str]:
        if theme == "dark":
            return {
                "background": "rgba(38, 42, 56, 235)",
                "border": "rgba(120, 140, 200, 120)",
                "text": "#F2F4FF",
            }
        return {
            "background": "rgba(255, 255, 255, 240)",
            "border": "rgba(150, 160, 200, 140)",
            "text": "#2A2E3F",
        }


__all__ = ["SpeechBubble"]
