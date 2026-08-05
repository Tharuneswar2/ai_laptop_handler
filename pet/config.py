"""
pet/config.py — Configuration for the Desktop Pet Engine.

Uses dataclasses for clean, type-safe settings.
All visual parameters are tunable from here.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

PET_DIR = Path(__file__).parent
ASSETS_DIR = PET_DIR / "assets"
POSITION_FILE = PET_DIR / ".pet_position.json"


@dataclass
class PetConfig:
    """All configurable settings for the desktop pet."""

    # ─── Size & Position ──────────────────────────────────────────────
    pet_size: int = 120                  # pet body diameter in pixels
    default_x: int = -1                  # -1 = bottom-right of screen
    default_y: int = -1
    window_margin: int = 20              # margin from screen edges

    # ─── Animation ────────────────────────────────────────────────────
    fps: int = 30                        # target frames per second
    blink_interval_ms: int = 3000        # time between blinks
    breathe_speed: float = 0.02          # breathing oscillation speed
    transition_duration_ms: int = 300    # state change crossfade

    # ─── Speech Bubble ────────────────────────────────────────────────
    bubble_font_family: str = "Segoe UI"
    bubble_font_size: int = 12
    bubble_max_width: int = 250
    bubble_padding: int = 12
    bubble_corner_radius: int = 14
    bubble_duration_ms: int = 3500       # auto-dismiss time
    bubble_typing_speed_ms: int = 30     # per-character reveal
    bubble_fade_duration_ms: int = 400

    # ─── Notification ─────────────────────────────────────────────────
    notification_duration_ms: int = 3000
    notification_offset_y: int = -80     # above the pet

    # ─── Appearance ───────────────────────────────────────────────────
    body_color_1: str = "#7c3aed"        # gradient start (purple)
    body_color_2: str = "#3b82f6"        # gradient end (blue)
    eye_color: str = "#1e1b4b"           # pupil color
    cheek_color: str = "#f472b6"         # blush color
    mouth_color: str = "#312e81"         # mouth color

    # ─── Behavior ─────────────────────────────────────────────────────
    always_on_top: bool = True
    opacity: float = 1.0                 # 0.0 – 1.0
    sleep_after_idle_ms: int = 120_000   # auto-sleep after 2 min idle
    draggable: bool = True

    # ─── Paths ────────────────────────────────────────────────────────
    assets_path: str = str(ASSETS_DIR)
    position_file: str = str(POSITION_FILE)

    def save_position(self, x: int, y: int) -> None:
        """Persist the pet's position to disk."""
        try:
            data = {"x": x, "y": y}
            Path(self.position_file).write_text(json.dumps(data))
        except Exception as e:
            logger.warning("Failed to save position: %s", e)

    def load_position(self) -> tuple[int, int] | None:
        """Load the pet's last saved position."""
        try:
            path = Path(self.position_file)
            if path.exists():
                data = json.loads(path.read_text())
                return data.get("x"), data.get("y")
        except Exception as e:
            logger.warning("Failed to load position: %s", e)
        return None

    def to_dict(self) -> dict:
        """Export config as a dictionary."""
        return asdict(self)
