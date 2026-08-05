"""
pet/core/renderer.py — The pet sprite widget.

Draws the current animation frame from the
:class:`~pet.core.animation_engine.AnimationEngine` onto a transparent
widget, applies emotion modifiers (bob, tint, overlays) and cross-fades
between states for flicker-free transitions.

The widget reserves a small headroom strip above the sprite so emotion
overlays (hearts, sparkles, "?", "!") are visible instead of clipped.
"""

from __future__ import annotations

import logging
import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .animation_engine import AnimationEngine
from .emotion_manager import EmotionManager

logger = logging.getLogger(__name__)

_TINT_ALPHA = 36
_OVERLAY_MARGIN_RATIO = 0.16  # headroom above the sprite, relative to frame height


class PetRenderer(QWidget):
    """
    Transparent widget that paints the current sprite frame.

    The widget size is ``(frame_w * scale, frame_h * scale * (1+margin))`` in
    logical pixels; the engine pixmaps already carry the device pixel ratio,
    so the sprite stays crisp on high-DPI screens.
    """

    def __init__(
        self,
        engine: AnimationEngine,
        emotions: EmotionManager,
        *,
        frame_size: tuple[int, int] = (192, 208),
        scale: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._emotions = emotions
        self._frame_size = frame_size
        self._scale = scale

        self._previous: QPixmap | None = None
        self._fade_started: float | None = None
        self._fade_ms = 140
        self._bob_phase = 0.0
        self._bob_timer = QTimer(self)
        self._bob_timer.setInterval(33)  # ~30 Hz
        self._bob_timer.timeout.connect(self._on_bob_tick)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(*self._logical_size())

        engine.frame_changed.connect(self.update)
        engine.state_animation_started.connect(self._on_animation_started)

    # ─── Layout ────────────────────────────────────────────────────────

    @property
    def margin(self) -> int:
        """Headroom above the sprite (logical pixels)."""
        return max(1, round(self._frame_size[1] * self._scale * _OVERLAY_MARGIN_RATIO))

    def sprite_rect(self) -> QRectF:
        """Rect occupied by the sprite itself (bottom-anchored)."""
        width = max(1, round(self._frame_size[0] * self._scale))
        height = max(1, round(self._frame_size[1] * self._scale))
        return QRectF(0, self.margin, width, height)

    def _logical_size(self) -> tuple[int, int]:
        width = max(1, round(self._frame_size[0] * self._scale))
        height = max(1, round(self._frame_size[1] * self._scale))
        return width, height + self.margin

    def set_scale(self, scale: float) -> None:
        """Change the display scale and refresh the engine pixmaps."""
        if scale == self._scale:
            return
        self._scale = scale
        self._engine.update_scale(scale)
        self.resize(*self._logical_size())
        self.update()

    def set_transition_ms(self, milliseconds: int) -> None:
        """Duration of the cross-fade between states."""
        self._fade_ms = max(0, milliseconds)

    # ─── Painting ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        sprite_rect = self.sprite_rect()
        pixmap = self._engine.current_frame()

        if pixmap is None:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
            painter.end()
            return

        # Emotion bob: vertical bounce applied on top of the sprite.
        bob = self._emotions.preset.bob_amplitude
        if bob:
            sprite_rect.translate(0, bob * math.sin(self._bob_phase))

        # Cross-fade: draw the previous state underneath at fading alpha.
        if self._previous is not None and self._fade_started is not None:
            progress = min(1.0, (time.monotonic() - self._fade_started) * 1000 / max(self._fade_ms, 1))
            painter.setOpacity(1.0 - progress)
            painter.drawPixmap(sprite_rect, self._previous, QRectF(self._previous.rect()))
            painter.setOpacity(progress)
        painter.drawPixmap(sprite_rect, pixmap, QRectF(pixmap.rect()))
        painter.setOpacity(1.0)

        # Emotion tint blended over the sprite.
        tint = self._emotions.preset.tint
        if tint:
            painter.fillRect(sprite_rect, QColor(*tint, _TINT_ALPHA))

        # Emotion overlay text in the headroom strip.
        overlay = self._emotions.preset.overlay
        if overlay:
            font = QFont()
            font.setPixelSize(max(10, round(self._frame_size[0] * self._scale * 0.14)))
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(
                QRectF(0, 0, self.width(), self.margin),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                overlay,
            )

        painter.end()

    # ─── Internals ─────────────────────────────────────────────────────

    def _on_animation_started(self, _animation: str) -> None:
        """Begin a cross-fade from the previous state's last frame."""
        current = self._engine.current_frame()
        if current is not None and self._fade_ms > 0:
            self._previous = current
            self._fade_started = time.monotonic()
        self._bob_timer.start()

    def _on_bob_tick(self) -> None:
        self._bob_phase += 0.25
        self.update()

    def stop(self) -> None:
        """Stop auxiliary timers (called when the window is hidden)."""
        self._bob_timer.stop()


__all__ = ["PetRenderer"]
