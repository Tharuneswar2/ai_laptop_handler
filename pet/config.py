"""
pet/config.py — Configuration for the Desktop Pet Engine.

All tunable settings are collected in the :class:`PetConfig` dataclass so the
engine can be re-configured without touching engine code.  ``load_config`` can
read overrides from an optional JSON file (see the ``PET_CONFIG_FILE`` env var).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

_PET_ROOT = Path(__file__).resolve().parent
DEFAULT_ASSET_ROOT = _PET_ROOT / "assets"


@dataclass
class PetConfig:
    """Runtime settings for the desktop pet engine."""

    # ─── Pet pack discovery ────────────────────────────────────────────
    default_pet: str = "robot--nova"
    """Slug (or pack directory name) of the pet loaded at startup."""

    asset_root: Path = DEFAULT_ASSET_ROOT
    """Directory that contains the ``pets/`` folder with pet packs."""

    pets_dir: str = "pets"
    """Name of the pet packs folder inside ``asset_root``."""

    # ─── Rendering ─────────────────────────────────────────────────────
    pet_size: tuple[int, int] = (192, 208)
    """Base frame size of the pet in logical pixels (Codex v1 frame)."""

    scale: float = 1.0
    """Global display scale applied to the sprite."""

    fps: int = 12
    """Default animation speed in frames per second."""

    always_on_top: bool = True
    """Keep the pet window above all other windows."""

    opacity: float = 1.0
    """Window opacity in the range 0.0 (invisible) to 1.0 (opaque)."""

    theme: str = "light"
    """UI theme used for speech bubbles and notifications."""

    show_in_taskbar: bool = False
    """Show the pet window in the OS taskbar (normally hidden)."""

    dpi_scale: bool = True
    """Scale the sprite by the screen's device pixel ratio."""

    # ─── Timers ────────────────────────────────────────────────────────
    speech_bubble_duration: float = 6.0
    """Seconds a speech bubble stays visible before fading out."""

    speech_bubble_typing_ms: int = 18
    """Milliseconds between characters of the typing effect."""

    notification_duration: float = 4.0
    """Seconds a notification stays visible before fading out."""

    autosleep_timeout: float = 300.0
    """Seconds of inactivity (IDLE) before the pet falls asleep."""

    state_timeout: float = 90.0
    """Seconds a non-IDLE state may persist before it is force-released."""

    # ─── Movement (wandering) ──────────────────────────────────────────
    movement_enabled: bool = True
    """Let the pet wander along the bottom of the screen when idle."""

    walk_interval_ms: int = 40
    """Milliseconds between movement steps (higher = slower walk)."""

    walk_step_px: int = 2
    """Pixels moved per step while walking."""

    min_walk_pause: float = 20.0
    """Minimum seconds of idle before the pet may start walking."""

    max_walk_pause: float = 60.0
    """Maximum seconds of idle before the pet starts walking."""

    min_walk_distance: int = 150
    """Minimum walk length in pixels."""

    max_walk_distance: int = 500
    """Maximum walk length in pixels."""

    # ─── Position persistence ──────────────────────────────────────────
    default_position: tuple[int, int] | None = None
    """Starting window position; ``None`` = bottom-right of the primary screen."""

    position_path: Path = _PET_ROOT / "data" / "pet_position.json"
    """JSON file used to remember the pet position between runs."""

    # ─── Cross-fade ────────────────────────────────────────────────────
    transition_ms: int = 140
    """Duration of the sprite cross-fade when switching states."""

    # ─── Convenience helpers ───────────────────────────────────────────

    @property
    def pets_root(self) -> Path:
        """Absolute path to the folder containing pet packs."""
        return self.asset_root / self.pets_dir

    def with_defaults(self, **overrides: Any) -> "PetConfig":
        """Return a copy of this config with ``overrides`` applied."""
        return replace(self, **overrides)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the config to a plain dict (for save/debug)."""
        data: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Path):
                data[key] = str(value)
            elif isinstance(value, tuple):
                data[key] = list(value)
            else:
                data[key] = value
        return data


def load_config(path: str | os.PathLike | None = None) -> PetConfig:
    """
    Build a :class:`PetConfig` from JSON overrides.

    Args:
        path: Optional path to a JSON config file.  If omitted, the file
            pointed to by the ``PET_CONFIG_FILE`` environment variable is
            used (when set).

    Returns:
        A fully-populated :class:`PetConfig` instance.
    """
    config = PetConfig()

    file = Path(path) if path else None
    if file is None:
        env = os.environ.get("PET_CONFIG_FILE", "")
        if env:
            file = Path(env)

    if file is None or not file.exists():
        return config

    with file.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    overrides: dict[str, Any] = {}
    for key, value in raw.items():
        if not hasattr(config, key):
            continue
        if key in ("asset_root", "position_path"):
            value = Path(str(value))
        elif key in ("pet_size", "default_position") and isinstance(value, list):
            value = tuple(value)
        overrides[key] = value

    return replace(config, **overrides) if overrides else config


def ensure_data_dir(config: PetConfig) -> None:
    """Create the data directory used for position persistence."""
    Path(config.position_path).parent.mkdir(parents=True, exist_ok=True)


__all__ = ["PetConfig", "load_config", "DEFAULT_ASSET_ROOT", "ensure_data_dir"]
