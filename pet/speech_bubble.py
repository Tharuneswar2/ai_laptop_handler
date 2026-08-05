"""
pet/speech_bubble.py — Floating speech bubble widget.

Features:
- Rounded corners and subtle drop shadow
- Auto-sizing with maximum width constraint & text wrapping
- Typewriter animation effect (character-by-character reveal)
- Fade-in & fade-out opacity transitions
- Auto-dismiss after configurable duration
- Rich text and emoji support
"""

import logging
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPen, QBrush, QFontMetrics, QFont
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsDropShadowEffect, QGraphicsOpacityEffect

from pet.config import PetConfig

logger = logging.getLogger(__name__)


class SpeechBubble(QWidget):
    """
    Floating speech bubble window positioned relative to the pet widget.
    """

    def __init__(self, config: PetConfig, parent_pet_window: QWidget):
        super().__init__()
        self.config = config
        self.pet_window = parent_pet_window

        self._full_text = ""
        self._current_char_idx = 0

        self._setup_ui()
        self._setup_timers_and_animations()

    def _setup_ui(self) -> None:
        """Initialize frameless transparent widget with shadow & label layout."""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # Label for displaying text
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        self.label.setFont(QFont(self.config.bubble_font_family, self.config.bubble_font_size))
        self.label.setStyleSheet("color: #1e1b4b; background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.config.bubble_padding,
            self.config.bubble_padding,
            self.config.bubble_padding,
            self.config.bubble_padding + 6  # room for tail
        )
        layout.addWidget(self.label)

        # Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        # Opacity effect for fade in / fade out
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

    def _setup_timers_and_animations(self) -> None:
        """Setup typing timer and fade animations."""
        # Typewriter timer
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self._on_typing_step)

        # Auto-dismiss timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.hide_bubble)

        # Fade animations
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(self.config.bubble_fade_duration_ms)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)

    # ─── Public API ──────────────────────────────────────────────────────

    def show_text(self, text: str, duration_ms: int = None) -> None:
        """
        Display text in speech bubble with typing animation.

        Args:
            text: Message to display
            duration_ms: Auto-dismiss delay in ms (None uses config default)
        """
        if not text:
            return

        self._full_text = text
        self._current_char_idx = 0
        self.label.setText("")

        # Calculate bubble size based on text length
        font_metrics = QFontMetrics(self.label.font())
        rect = font_metrics.boundingRect(
            0, 0, self.config.bubble_max_width - 2 * self.config.bubble_padding, 1000,
            Qt.TextWordWrap, text
        )
        w = min(self.config.bubble_max_width, rect.width() + 2 * self.config.bubble_padding + 10)
        h = rect.height() + 2 * self.config.bubble_padding + 14
        self.setFixedSize(max(80, w), max(50, h))

        self._reposition_above_pet()
        self.show()

        # Fade In
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

        # Start Typewriter
        self.typing_timer.start(self.config.bubble_typing_speed_ms)

        # Setup Auto-Dismiss
        dismiss_delay = duration_ms if duration_ms is not None else self.config.bubble_duration_ms
        self.dismiss_timer.stop()
        self.dismiss_timer.start(dismiss_delay + len(text) * self.config.bubble_typing_speed_ms)

    def hide_bubble(self) -> None:
        """Fade out and hide the bubble."""
        self.typing_timer.stop()
        self.dismiss_timer.stop()

        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self._on_fade_out_finished)
        self.fade_anim.start()

    def _on_fade_out_finished(self) -> None:
        try:
            self.fade_anim.finished.disconnect(self._on_fade_out_finished)
        except Exception:
            pass
        self.hide()

    def _on_typing_step(self) -> None:
        """Reveal one character at a time."""
        if self._current_char_idx <= len(self._full_text):
            self.label.setText(self._full_text[:self._current_char_idx])
            self._current_char_idx += 1
        else:
            self.typing_timer.stop()

    def _reposition_above_pet(self) -> None:
        """Align bubble nicely above the pet window."""
        pet_geo = self.pet_window.geometry()
        bx = pet_geo.center().x() - self.width() // 2
        by = pet_geo.top() - self.height() + 10

        # Clamp to screen bounds
        screen = self.pet_window.screen()
        if screen:
            s_geo = screen.availableGeometry()
            bx = max(s_geo.left() + 10, min(bx, s_geo.right() - self.width() - 10))
            by = max(s_geo.top() + 10, by)

        self.move(QPoint(bx, by))

    # ─── QPainter Speech Bubble Drawing ──────────────────────────────────

    def paintEvent(self, event) -> None:
        """Draw bubble background with rounded rectangle and speech tail."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        r = self.config.bubble_corner_radius
        w = float(self.width())
        h = float(self.height() - 8)  # Leave room for tail at bottom

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)

        # Add tail pointing down towards pet
        tail_x = w / 2.0
        path.moveTo(tail_x - 8, h)
        path.lineTo(tail_x, h + 8)
        path.lineTo(tail_x + 8, h)

        # Draw Background (White / Soft Light Cream)
        painter.setPen(QPen(QColor(226, 232, 240, 200), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, 245)))
        painter.drawPath(path)
