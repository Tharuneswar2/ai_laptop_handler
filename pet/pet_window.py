"""
pet/pet_window.py — Main transparent desktop window for the pet.

Features:
- Transparent background (Qt.WA_TranslucentBackground)
- Frameless, stays on top, hidden from taskbar (Qt.Tool)
- High-DPI support
- Rendered via QPainter (procedural cute character with glowing effects, eyes, mouth, Zzz, etc.)
- Multi-monitor placement and saved position loading
"""

import math
import logging
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QRadialGradient, QLinearGradient,
    QPainterPath, QPen, QBrush, QMouseEvent
)
from PySide6.QtWidgets import QWidget, QApplication

from pet.config import PetConfig
from pet.animation_manager import AnimationManager
from pet.drag_manager import DragManager
from pet.event_handler import PetState

logger = logging.getLogger(__name__)


class PetWindow(QWidget):
    """
    Transparent desktop overlay widget hosting the pet character.
    """

    def __init__(self, config: PetConfig, anim_mgr: AnimationManager, drag_mgr: DragManager):
        super().__init__()
        self.config = config
        self.anim_mgr = anim_mgr
        self.drag_mgr = drag_mgr

        self._setup_window_flags()
        self._init_position()

        # Connect animation updates to widget repaint
        self.anim_mgr.frame_updated.connect(self.update)

    def _setup_window_flags(self) -> None:
        """Configure Qt window attributes for transparent desktop overlay."""
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        self.setWindowFlags(flags)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setWindowOpacity(self.config.opacity)

        # Set fixed size large enough for pet + padding for Zzz/sparkles/glow
        size = self.config.pet_size + 60
        self.setFixedSize(size, size)

    def _init_position(self) -> None:
        """Position window on desktop based on config or saved state."""
        saved_pos = self.config.load_position()
        if saved_pos and saved_pos[0] is not None and saved_pos[1] is not None:
            self.move(saved_pos[0], saved_pos[1])
            logger.info("Restored pet position: (%d, %d)", saved_pos[0], saved_pos[1])
            return

        # Default: Bottom-right corner of primary screen
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            geo = primary_screen.availableGeometry()
            x = geo.right() - self.width() - self.config.window_margin - 40
            y = geo.bottom() - self.height() - self.config.window_margin - 40
            self.move(x, y)
            logger.info("Set default pet position: (%d, %d)", x, y)

    # ─── Event Handlers ──────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.drag_mgr.handle_mouse_press(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.drag_mgr.handle_mouse_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.drag_mgr.handle_mouse_release(event)
        super().mouseReleaseEvent(event)

    # ─── QPainter Rendering ──────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        """Render pet character with QPainter."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # If custom GIF is loaded, draw it directly
        if self.anim_mgr.current_movie and self.anim_mgr.current_movie.currentPixmap():
            pix = self.anim_mgr.current_movie.currentPixmap()
            scaled_pix = pix.scaled(
                self.config.pet_size, self.config.pet_size,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (self.width() - scaled_pix.width()) // 2
            y = (self.height() - scaled_pix.height()) // 2
            painter.drawPixmap(x, y, scaled_pix)
            return

        # Draw procedural QPainter character
        params = self.anim_mgr.get_render_params()
        self._draw_procedural_pet(painter, params)

    def _draw_procedural_pet(self, painter: QPainter, p: dict) -> None:
        """Draw the procedural pet character using shapes & gradients."""
        cx = self.width() / 2.0
        cy = self.height() / 2.0 + 10.0 + p["breathe_y"]
        r = self.config.pet_size / 2.0

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(p["rotation"])
        painter.scale(p["breathe_scale"], p["breathe_scale"])

        # 1. Glow Effect (Listening / Thinking state)
        if p["glow"]:
            glow_grad = QRadialGradient(0, 0, r + 20)
            glow_color = QColor(139, 92, 246, 120) if p["state"] != PetState.ERROR else QColor(239, 68, 68, 120)
            glow_grad.setColorAt(0, glow_color)
            glow_grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow_grad))
            painter.drawEllipse(QPointF(0, 0), r + 20, r + 20)

        # 2. Main Body (Radial Gradient)
        body_grad = QRadialGradient(-r * 0.3, -r * 0.3, r * 1.4)
        c1 = QColor(self.config.body_color_1)
        c2 = QColor(self.config.body_color_2)
        if p["state"] == PetState.ERROR:
            c1, c2 = QColor("#ef4444"), QColor("#991b1b")
        elif p["state"] == PetState.HAPPY:
            c1, c2 = QColor("#ec4899"), QColor("#8b5cf6")

        body_grad.setColorAt(0, c1)
        body_grad.setColorAt(1, c2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(body_grad))
        painter.drawEllipse(QPointF(0, 0), r, r)

        # 3. Blush / Cheeks
        if p["blush_opacity"] > 0:
            blush_color = QColor(self.config.cheek_color)
            blush_color.setAlphaF(p["blush_opacity"])
            painter.setBrush(QBrush(blush_color))
            painter.drawEllipse(QPointF(-r * 0.55, r * 0.15), r * 0.22, r * 0.15)
            painter.drawEllipse(QPointF(r * 0.55, r * 0.15), r * 0.22, r * 0.15)

        # 4. Eyes
        eye_y = -r * 0.15
        eye_spacing = r * 0.42
        eye_r_x = r * 0.16
        eye_r_y = r * 0.22 * p["eye_open"]

        eye_color = QColor(self.config.eye_color)
        painter.setBrush(QBrush(Qt.white))
        painter.setPen(Qt.NoPen)

        if p["eye_open"] > 0.05:
            # Left & Right Sclera (White)
            painter.drawEllipse(QPointF(-eye_spacing, eye_y), eye_r_x, max(1.0, eye_r_y))
            painter.drawEllipse(QPointF(eye_spacing, eye_y), eye_r_x, max(1.0, eye_r_y))

            # Pupils (Dark)
            pupil_y = eye_y + p["pupil_offset_y"]
            painter.setBrush(QBrush(eye_color))
            pupil_r = eye_r_x * 0.65
            painter.drawEllipse(QPointF(-eye_spacing, pupil_y), pupil_r, min(pupil_r, max(1.0, eye_r_y * 0.8)))
            painter.drawEllipse(QPointF(eye_spacing, pupil_y), pupil_r, min(pupil_r, max(1.0, eye_r_y * 0.8)))

            # Catchlight (White sparkle in pupil)
            painter.setBrush(QBrush(Qt.white))
            painter.drawEllipse(QPointF(-eye_spacing - pupil_r * 0.3, pupil_y - pupil_r * 0.3), pupil_r * 0.35, pupil_r * 0.35)
            painter.drawEllipse(QPointF(eye_spacing - pupil_r * 0.3, pupil_y - pupil_r * 0.3), pupil_r * 0.35, pupil_r * 0.35)
        else:
            # Closed eyes (Happy curves or sleeping lines)
            pen = QPen(eye_color, 3, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(-eye_spacing - eye_r_x, eye_y)
            path.quadTo(-eye_spacing, eye_y - 6, -eye_spacing + eye_r_x, eye_y)
            painter.drawPath(path)

            path2 = QPainterPath()
            path2.moveTo(eye_spacing - eye_r_x, eye_y)
            path2.quadTo(eye_spacing, eye_y - 6, eye_spacing + eye_r_x, eye_y)
            painter.drawPath(path2)

        # 5. Mouth
        mouth_y = r * 0.25
        pen_mouth = QPen(QColor(self.config.mouth_color), 3, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_mouth)
        painter.setBrush(Qt.NoBrush)

        mouth_path = QPainterPath()
        if p["mouth_open"] > 0.1:
            painter.setBrush(QBrush(QColor(self.config.mouth_color)))
            mouth_rect = QRectF(-r * 0.2, mouth_y, r * 0.4, r * 0.3 * p["mouth_open"])
            painter.drawEllipse(mouth_rect)
        else:
            ctrl_y = mouth_y + (r * 0.3 * p["mouth_curve"])
            mouth_path.moveTo(-r * 0.18, mouth_y)
            mouth_path.quadTo(0, ctrl_y, r * 0.18, mouth_y)
            painter.drawPath(mouth_path)

        # 6. Accessories / State Extras
        # Loading Ring (Thinking)
        if p["state"] == PetState.THINKING:
            painter.setPen(QPen(QColor(255, 255, 255, 200), 4, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(QRectF(-r * 1.2, -r * 1.2, r * 2.4, r * 2.4), int(-p["loading_angle"] * 16), 100 * 16)

        # Zzz (Sleeping)
        if p["state"] == PetState.SLEEPING:
            painter.setPen(QPen(QColor(255, 255, 255, 220), 3))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(18)
            painter.setFont(font)
            zzz_y = -r * 0.8 - p["zzz_offset"]
            painter.drawText(int(r * 0.5), int(zzz_y), "Zzz...")

        # Working / Typing animation icon
        if p["state"] == PetState.WORKING:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
            off = p["typing_offset"]
            painter.drawRect(QRectF(-15 + off, r * 0.7, 8, 4))
            painter.drawRect(QRectF(0 - off, r * 0.7, 8, 4))
            painter.drawRect(QRectF(15 + off, r * 0.7, 8, 4))

        # Question mark (Error)
        if p["state"] == PetState.ERROR:
            painter.setPen(QPen(QColor("#f59e0b"), 4))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(28)
            painter.setFont(font)
            painter.drawText(int(-10), int(-r * 1.1), "?")

        painter.restore()
