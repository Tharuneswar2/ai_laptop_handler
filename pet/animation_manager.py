"""
pet/animation_manager.py — State-based animation engine.

Supports two rendering pathways:
1. QPainter programmatic drawing (default) — cute character drawn with math/shapes,
   supporting blinking, breathing, ear wiggles, loading dots, Zzz floating, etc.
2. QMovie GIF / sprite loader (optional override if files exist in assets/<state>/).
"""

import math
import logging
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QMovie

from pet.config import PetConfig
from pet.event_handler import PetState
from pet.emotion_manager import EmotionManager, EmotionModifiers

logger = logging.getLogger(__name__)


class AnimationManager(QObject):
    """
    Manages animation frame timing, state parameters, and rendering properties.
    Emits frame_updated signal to trigger widget redraws.
    """

    frame_updated = Signal()

    def __init__(self, config: PetConfig, emotion_manager: EmotionManager):
        super().__init__()
        self.config = config
        self.emotion_manager = emotion_manager

        self.current_state = PetState.IDLE
        self.tick = 0
        self.blink_state = False
        self.blink_counter = 0

        # Optional QMovie GIF loader state
        self.current_movie: QMovie | None = None
        self._movie_cache: dict[str, QMovie] = {}

        # Frame timer (30 FPS default)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(1000 // self.config.fps)

        self._check_assets_for_state(self.current_state)

    def set_state(self, state: str) -> None:
        """Switch animation state cleanly."""
        try:
            new_state = PetState(state)
        except ValueError:
            logger.warning("Unknown pet state '%s', defaulting to idle", state)
            new_state = PetState.IDLE

        if new_state == self.current_state:
            return

        logger.info("Pet animation state: %s → %s", self.current_state.value, new_state.value)
        self.current_state = new_state
        self.tick = 0

        self._check_assets_for_state(new_state)

    def _check_assets_for_state(self, state: PetState) -> None:
        """Check if custom GIF asset exists for the state."""
        state_dir = Path(self.config.assets_path) / state.value
        gif_files = list(state_dir.glob("*.gif")) if state_dir.exists() else []

        if self.current_movie:
            self.current_movie.stop()
            self.current_movie = None

        if gif_files:
            gif_path = str(gif_files[0])
            if gif_path not in self._movie_cache:
                movie = QMovie(gif_path)
                movie.setSpeed(int(100 * self.emotion_manager.modifiers.animation_speed))
                movie.frameChanged.connect(lambda: self.frame_updated.emit())
                self._movie_cache[gif_path] = movie

            self.current_movie = self._movie_cache[gif_path]
            self.current_movie.start()
            logger.debug("Using GIF animation for state '%s': %s", state.value, gif_path)

    def _on_tick(self) -> None:
        """Timer callback for frame calculations."""
        self.tick += 1

        # Handle blinking logic for idle/listening states
        if self.current_state in (PetState.IDLE, PetState.LISTENING, PetState.HAPPY, PetState.WORKING):
            if not self.blink_state:
                if self.tick % (self.config.blink_interval_ms // (1000 // self.config.fps)) == 0:
                    self.blink_state = True
                    self.blink_counter = 0
            else:
                self.blink_counter += 1
                if self.blink_counter >= 3:  # Blink lasts 3 frames
                    self.blink_state = False

        if not self.current_movie:
            self.frame_updated.emit()

    def get_render_params(self) -> dict:
        """
        Compute parametric properties for QPainter rendering based on state, tick, and emotions.
        """
        mods: EmotionModifiers = self.emotion_manager.modifiers
        t = self.tick * self.config.breathe_speed * mods.animation_speed

        # Breathing effect
        breathe_y = math.sin(t) * 3.0
        breathe_scale = 1.0 + math.sin(t) * 0.02

        # State specific calculations
        bounce_y = 0.0
        rotation = mods.head_tilt
        eye_open = 0.0 if self.blink_state else 1.0
        mouth_open = mods.mouth_open
        mouth_curve = mods.mouth_curve
        glow = False
        loading_angle = 0.0
        zzz_offset = 0.0
        typing_offset = 0.0

        if self.current_state == PetState.IDLE:
            eye_open = 0.0 if self.blink_state else 1.0

        elif self.current_state == PetState.LISTENING:
            glow = True
            bounce_y = math.sin(t * 2) * 2.0
            eye_open = 1.2 * mods.eye_scale

        elif self.current_state == PetState.THINKING:
            loading_angle = (self.tick * 8) % 360
            rotation = math.sin(t) * 5.0
            eye_open = 0.8

        elif self.current_state == PetState.WORKING:
            typing_offset = math.sin(self.tick * 0.4) * 4.0
            bounce_y = abs(math.sin(self.tick * 0.3)) * 3.0

        elif self.current_state == PetState.SPEAKING:
            mouth_open = 0.2 + abs(math.sin(self.tick * 0.4)) * 0.6
            bounce_y = math.sin(t * 1.5) * 2.0

        elif self.current_state == PetState.HAPPY:
            bounce_y = abs(math.sin(self.tick * 0.3)) * 12.0
            mouth_curve = 0.8
            eye_open = 1.0

        elif self.current_state == PetState.EXCITED:
            bounce_y = abs(math.sin(self.tick * 0.5)) * 16.0
            mouth_curve = 1.0
            rotation = math.sin(self.tick * 0.4) * 12.0

        elif self.current_state == PetState.SAD:
            breathe_y = math.sin(t * 0.5) * 1.5
            mouth_curve = -0.6
            eye_open = 0.5

        elif self.current_state == PetState.ERROR:
            rotation = math.sin(self.tick * 0.8) * 8.0
            mouth_curve = -0.4

        elif self.current_state == PetState.SLEEPING:
            eye_open = 0.0
            zzz_offset = (self.tick * 1.5) % 40.0
            breathe_y = math.sin(t * 0.4) * 2.0

        return {
            "state": self.current_state,
            "breathe_y": breathe_y + bounce_y - mods.body_bounce,
            "breathe_scale": breathe_scale,
            "rotation": rotation,
            "eye_open": eye_open * mods.eye_scale,
            "pupil_offset_y": mods.pupil_offset_y,
            "mouth_open": mouth_open,
            "mouth_curve": mouth_curve,
            "glow": glow,
            "loading_angle": loading_angle,
            "zzz_offset": zzz_offset,
            "typing_offset": typing_offset,
            "blush_opacity": mods.blush_opacity,
            "sparkle": mods.sparkle,
        }
