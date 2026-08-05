"""
pet/core/fallback_pet.py — Built-in procedural pet used as a safety net.

When no pet pack is installed (or a requested pack is missing), the engine
builds a small sprite-sheet atlas in memory with Pillow and feeds it through
the exact same animation pipeline as a Codex pack.  No art files are
required, and nothing is hardcoded into the renderer — the fallback pet is
just another spritesheet with the standard v1 row layout.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .asset_loader import CELL_HEIGHT, CELL_WIDTH, COLUMNS, V1_ROWS, ROW_BY_INDEX

# Draw on a small logical grid, then upscale with NEAREST for a crisp
# pixel look at the full 192x208 Codex cell size.
GRID_W, GRID_H = 24, 26
SCALE = CELL_WIDTH // GRID_W  # 8


@dataclass(frozen=True)
class Palette:
    """Colour scheme of the fallback blob."""

    body: tuple[int, int, int]
    belly: tuple[int, int, int]
    outline: tuple[int, int, int]
    eye: tuple[int, int, int]
    accent: tuple[int, int, int]


DEFAULT_PALETTE = Palette(
    body=(255, 196, 120),
    belly=(255, 236, 200),
    outline=(140, 90, 40),
    eye=(60, 40, 30),
    accent=(255, 120, 140),
)


def _base(center_x: float, center_y: float, width: float, height: float) -> tuple[float, ...]:
    """Bounds for the creature's body ellipse at a given centre."""
    return (
        center_x - width / 2,
        center_y - height / 2,
        center_x + width / 2,
        center_y + height / 2,
    )


def draw_blob(
    img: Image.Image,
    frame: int,
    *,
    palette: Palette = DEFAULT_PALETTE,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    tilt: float = 0.0,
    blink: bool = False,
    sad: bool = False,
    sweat: bool = False,
    zzz: bool = False,
    arm_up: float = 0.0,
    sparkle: bool = False,
) -> None:
    """Draw one frame of the fallback blob onto a transparent GRID-sized image."""
    d = ImageDraw.Draw(img)
    cx = GRID_W / 2 + x_offset
    cy = GRID_H / 2 + y_offset

    # ── shadow ──────────────────────────────────────────────────────────
    d.ellipse((cx - 6, GRID_H - 3, cx + 6, GRID_H), fill=(0, 0, 0, 40))

    # ── body ────────────────────────────────────────────────────────────
    body_h = 14 + 3 * math.sin(frame * 0.9)
    body_w = 13
    d.ellipse(_base(cx, cy + 3, body_w, body_h), fill=palette.body, outline=palette.outline, width=1)

    # ── ears (two little triangles) ─────────────────────────────────────
    for sign in (-1, 1):
        ex = cx + sign * 3.5
        ey = cy - 5
        if tilt:
            ex -= sign * tilt
        d.polygon(
            [(ex - 2, ey), (ex + 2, ey), (ex + sign * 1, ey - 4)],
            fill=palette.accent if not sad else palette.outline,
        )

    # ── eyes ────────────────────────────────────────────────────────────
    eye_y = cy - 1
    if sad:
        for sign in (-1, 1):
            d.line(
                (cx + sign * 3.5 - 1.5, eye_y - 1.5, cx + sign * 3.5 + 1.5, eye_y + 1.5),
                fill=palette.eye, width=1,
            )
            d.line(
                (cx + sign * 3.5 + 1.5, eye_y - 1.5, cx + sign * 3.5 - 1.5, eye_y + 1.5),
                fill=palette.eye, width=1,
            )
    elif blink:
        for sign in (-1, 1):
            d.line(
                (cx + sign * 3.5 - 2, eye_y, cx + sign * 3.5 + 2, eye_y),
                fill=palette.eye, width=1,
            )
    else:
        for sign in (-1, 1):
            d.ellipse((cx + sign * 3.5 - 1.5, eye_y - 1.5, cx + sign * 3.5 + 1.5, eye_y + 1.5), fill=palette.eye)

    # ── mouth ───────────────────────────────────────────────────────────
    mouth_y = cy + 3
    if sad:
        d.arc((cx - 2, mouth_y, cx + 2, mouth_y + 2), 0, 180, fill=palette.outline, width=1)
    else:
        d.arc((cx - 2, mouth_y - 1, cx + 2, mouth_y + 1), 20, 160, fill=palette.outline, width=1)

    # ── belly patch ─────────────────────────────────────────────────────
    d.ellipse((cx - 3, cy + 5, cx + 3, cy + 9), fill=palette.belly)

    # ── arm waving ──────────────────────────────────────────────────────
    if arm_up:
        wx = cx + 7
        wy = cy + 2 - arm_up * 4
        d.line((cx + 6, cy + 3, wx, wy), fill=palette.outline, width=1)
        d.ellipse((wx - 1.5, wy - 1.5, wx + 1.5, wy + 1.5), fill=palette.body)

    # ── effects ─────────────────────────────────────────────────────────
    if sweat:
        d.ellipse((cx + 5, cy - 6, cx + 6, cy - 5), fill=(120, 180, 255))
    if zzz:
        zx, zy = cx + 5 + frame, cy - 8 - frame % 4
        d.text((zx, zy), "z", fill=palette.outline)
    if sparkle:
        s = frame % 3
        d.ellipse((cx - 8, cy - 8 - s, cx - 7, cy - 7 - s), fill=(255, 230, 120))


def build_fallback_atlas() -> Image.Image:
    """Build the full v1 atlas (1536x1872) for the fallback blob."""
    atlas = Image.new("RGBA", (COLUMNS * CELL_WIDTH, V1_ROWS * CELL_HEIGHT), (0, 0, 0, 0))

    for row, _name, count in ROW_BY_INDEX:
        for column in range(count):
            small = Image.new("RGBA", (GRID_W, GRID_H), (0, 0, 0, 0))
            phase = column / max(count - 1, 1)
            blob_kwargs: dict = {}
            if row == 0:  # idle — gentle bob + blink
                blob_kwargs = dict(y_offset=-1.2 * math.sin(phase * math.pi * 2), blink=(column == 3))
            elif row == 1:  # running-right — steps right
                blob_kwargs = dict(x_offset=2.5 * math.sin(phase * math.pi * 2), tilt=-1, y_offset=-1.5 * abs(math.sin(phase * math.pi)))
            elif row == 2:  # running-left
                blob_kwargs = dict(x_offset=-2.5 * math.sin(phase * math.pi * 2), tilt=1, y_offset=-1.5 * abs(math.sin(phase * math.pi)))
            elif row == 3:  # waving
                blob_kwargs = dict(arm_up=1.0 - abs(phase - 0.5) * 1.6, y_offset=-0.8 * math.sin(phase * math.pi * 2))
            elif row == 4:  # jumping — arc up and down
                blob_kwargs = dict(y_offset=-7 * math.sin(phase * math.pi), arm_up=0.6)
            elif row == 5:  # failed
                blob_kwargs = dict(sad=True, sweat=True, y_offset=0.8 * math.sin(phase * math.pi * 2))
            elif row == 6:  # waiting — sway, blink
                blob_kwargs = dict(x_offset=1.5 * math.sin(phase * math.pi * 2), blink=(column == 4))
            elif row == 7:  # running — fast bounce
                blob_kwargs = dict(y_offset=-2.5 * abs(math.sin(phase * math.pi * 2)), tilt=-1.2 * math.sin(phase * math.pi * 2))
            else:  # review — look side to side
                blob_kwargs = dict(x_offset=1.8 * math.sin(phase * math.pi * 3), sparkle=(column % 2 == 0))
            draw_blob(small, frame=column, **blob_kwargs)

            scaled = small.resize((CELL_WIDTH, CELL_HEIGHT), Image.Resampling.NEAREST)
            atlas.paste(scaled, (column * CELL_WIDTH, row * CELL_HEIGHT))

    return atlas


def build_fallback_pack(pack_id: str = "fallback--builtin") -> "PetPack":
    """
    Build a :class:`~pet.core.asset_loader.PetPack` from procedural art.

    The fallback flows through the exact same pipeline as a real Codex
    pack — it is only an in-memory atlas instead of a folder on disk.
    """
    from .asset_loader import PetPack, DEFAULT_STATE_TO_ANIMATION

    atlas = build_fallback_atlas()
    frames: dict[str, tuple] = {}
    for row, name, count in ROW_BY_INDEX:
        cells: list = []
        for column in range(count):
            cells.append(
                atlas.crop(
                    (
                        column * CELL_WIDTH,
                        row * CELL_HEIGHT,
                        (column + 1) * CELL_WIDTH,
                        (row + 1) * CELL_HEIGHT,
                    )
                )
            )
        frames[name] = tuple(cells)

    states = {
        state: anim for state, anim in DEFAULT_STATE_TO_ANIMATION.items() if anim in frames
    }
    return PetPack(
        id=pack_id,
        display_name="Fallback Blob",
        description="Built-in procedural pet used when no pet pack is installed.",
        pack_dir=Path("(built-in)"),
        sprite_version=1,
        frames=frames,
        states=states,
        metadata={},
    )


__all__ = ["build_fallback_atlas", "build_fallback_pack", "Palette", "DEFAULT_PALETTE"]
