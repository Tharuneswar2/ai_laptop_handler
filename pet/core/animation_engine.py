"""
pet/core/animation_engine.py — Sprite-sheet animation playback.

The engine takes a :class:`~pet.core.asset_loader.PetPack`, converts its
sliced frames to cached QPixmaps, and plays the animation that matches the
current pet state.  It supports per-state fps, one-shot animations and
smooth (cross-faded) state switches, and it keeps CPU usage near zero when
idle or hidden by stopping its timer.
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap

from .asset_loader import PetPack
from .emotion_manager import EmotionManager
from .state_machine import ONE_SHOT_STATES, PetState

logger = logging.getLogger(__name__)


class AnimationEngine(QObject):
    """
    Plays one animation at a time (the one for the current pet state).

    Signals:
        frame_changed: emitted whenever a new frame is ready (drives repaints).
        state_animation_started(str): emitted when the active animation
            changes, so the renderer can cross-fade.
        animation_finished: emitted after a one-shot animation completes.
    """

    frame_changed = Signal()
    state_animation_started = Signal(str)
    animation_finished = Signal()

    def __init__(
        self,
        emotion_manager: EmotionManager,
        *,
        default_fps: float = 12.0,
        scale: float = 1.0,
        device_pixel_ratio: float = 1.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._emotions = emotion_manager
        self._default_fps = default_fps
        self._scale = scale
        self._dpr = device_pixel_ratio

        self._pack: PetPack | None = None
        self._frames: dict[str, tuple[QPixmap, ...]] = {}
        self._fps: dict[str, float] = {}

        self._animation: str | None = None
        self._state: PetState = PetState.IDLE
        self._index = 0
        self._one_shot = False
        self._paused = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    # ─── Pack loading ──────────────────────────────────────────────────

    def set_pack(self, pack: PetPack, *, scale: float | None = None) -> None:
        """
        Load a new pet pack.

        Converts the pack's PIL frames into cached, DPI-aware QPixmaps.
        Existing animations are dropped; playback restarts from the start.
        """
        if scale is not None:
            self._scale = scale
        self._pack = pack
        self._frames.clear()
        self._fps.clear()

        for name, pil_frames in pack.frames.items():
            pixmaps = tuple(self._to_pixmap(frame) for frame in pil_frames)
            self._frames[name] = pixmaps
        self._fps.update(pack.metadata.get("animation_fps", {}))
        self._apply_state(self._state, restart=True)

    def _to_pixmap(self, image) -> QPixmap:
        """Convert a PIL RGBA frame to a pre-scaled QPixmap (high-DPI aware)."""
        image = image.convert("RGBA")
        data = image.tobytes("raw", "RGBA")
        qimage = QImage(data, image.width, image.height, QImage.Format.Format_RGBA8888)
        qimage = qimage.copy()  # detach from the byte buffer

        dpr = max(self._dpr, 1.0)  # guard: a 0 dpr would collapse the sprite
        target_w = max(1, round(image.width * self._scale * dpr))
        target_h = max(1, round(image.height * self._scale * dpr))
        if (target_w, target_h) != (image.width, image.height):
            qimage = qimage.scaled(
                target_w, target_h,
                mode=Qt.TransformationMode.SmoothTransformation,
            )
        pixmap = QPixmap.fromImage(qimage)
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    # ─── Playback control ──────────────────────────────────────────────

    def set_state(self, state: PetState) -> None:
        """Switch the active animation to the one for ``state``."""
        if state is not self._state:
            self._apply_state(state, restart=False)

    def restart(self) -> None:
        """Restart the current animation from its first frame."""
        self._index = 0
        self._start_timer()

    def pause(self) -> None:
        """Pause frame advance (used while dragging)."""
        self._paused = True
        self._timer.stop()

    def resume(self) -> None:
        """Resume frame advance after :meth:`pause`."""
        self._paused = False
        self._start_timer()

    def stop(self) -> None:
        """Stop playback entirely (window hidden)."""
        self._timer.stop()

    def update_scale(self, scale: float) -> None:
        """Re-render pixmaps at a new scale (keeps cached frames fresh)."""
        if self._pack is not None and scale != self._scale:
            self.set_pack(self._pack, scale=scale)

    # ─── Accessors ─────────────────────────────────────────────────────

    @property
    def pack(self) -> PetPack | None:
        """The currently loaded pet pack."""
        return self._pack

    @property
    def animation(self) -> str | None:
        """Name of the active animation row."""
        return self._animation

    def current_frame(self) -> QPixmap | None:
        """The QPixmap for the current frame, or None when nothing loaded."""
        if self._animation is None:
            return None
        frames = self._frames.get(self._animation)
        if not frames:
            return None
        return frames[min(self._index, len(frames) - 1)]

    def frame_count(self) -> int:
        """Number of frames in the active animation (0 when none)."""
        if self._animation is None:
            return 0
        return len(self._frames.get(self._animation, ()))

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ─── Internals ─────────────────────────────────────────────────────

    def _apply_state(self, state: PetState, *, restart: bool) -> None:
        if self._pack is None:
            return
        animation = self._pack.animation_for(state)
        if animation is None or animation not in self._frames:
            logger.debug("No animation for state %s in pack %s", state.value, self._pack.id)
            return

        self._state = state
        self._animation = animation
        self._index = 0
        self._one_shot = state in ONE_SHOT_STATES
        self.state_animation_started.emit(animation)
        self._start_timer()
        self.frame_changed.emit()

    def _start_timer(self) -> None:
        if self._paused:
            return
        fps = self._fps.get(self._animation or "", self._default_fps)
        fps *= self._emotions.preset.speed_multiplier
        interval = max(1, round(1000.0 / max(fps, 1.0)))
        self._timer.start(interval)

    def _advance(self) -> None:
        if self._animation is None or self._paused:
            return
        count = self.frame_count()
        if count <= 1:
            return
        self._index += 1
        if self._index >= count:
            if self._one_shot:
                self._index = count - 1
                self._timer.stop()
                logger.debug("One-shot animation %s finished", self._animation)
                self.animation_finished.emit()
                return
            self._index = 0
        self.frame_changed.emit()

    def _on_emotion_changed(self) -> None:
        """Emotion changes may alter playback speed — restart the timer."""
        self._start_timer()


# Re-export for the renderer's convenience.
FrameTick = Callable[[], None]

__all__ = ["AnimationEngine"]
