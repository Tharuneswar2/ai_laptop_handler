#!/usr/bin/env python3
"""
tools/generate_pet_sheets.py — Generate the bundled Nova pet packs.

Each pack follows the Codex convention:

    assets/pets/<pet-slug>--<author-slug>/
    ├── submission.json
    ├── pet.json
    └── spritesheet.webp      # 1536x1872 v1 atlas, 8 columns x 9 rows

The art is drawn procedurally with Pillow on a 24x26 grid and upscaled x8 to
the standard 192x208 frame size.  Row layout matches the awesome-codex-pet
validation tools:

    row 0 idle (6)   row 1 running-right (8)  row 2 running-left (8)
    row 3 waving (4) row 4 jumping (5)        row 5 failed (8)
    row 6 waiting (6) row 7 running (6)       row 8 review (6)

Run from the repo root:

    python -m pet.tools.generate_pet_sheets [--validate]
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "pets"

COLUMNS = 8
ROWS = 9
CELL_W, CELL_H = 192, 208
GRID_W, GRID_H = 24, 26
SCALE = CELL_W // GRID_W

ROW_LAYOUT: list[tuple[str, int]] = [
    ("idle", 6),
    ("running-right", 8),
    ("running-left", 8),
    ("waving", 4),
    ("jumping", 5),
    ("failed", 8),
    ("waiting", 6),
    ("running", 6),
    ("review", 6),
]

AUTHOR_SLUG = "nova"


@dataclass
class PetSpec:
    """Visual parameters of one pet."""

    slug: str
    display_name: str
    description: str
    body: tuple[int, int, int]
    belly: tuple[int, int, int]
    outline: tuple[int, int, int]
    eye: tuple[int, int, int]
    accent: tuple[int, int, int]
    ear_type: str = "point"  # point | round | antenna
    tail_type: str = "stub"  # stub | bushy | curved | antenna
    muzzle: str = "plain"    # plain | cat | panda
    ear_tips: tuple[int, int, int] | None = None


SPECS: list[PetSpec] = [
    PetSpec(
        slug="robot",
        display_name="Nova Bot",
        description="A tiny companion robot with a glowing antenna. Built-in default pet.",
        body=(170, 182, 200),
        belly=(212, 222, 238),
        outline=(84, 94, 116),
        eye=(90, 160, 255),
        accent=(255, 108, 120),
        ear_type="antenna",
        tail_type="antenna",
    ),
    PetSpec(
        slug="cat",
        display_name="Nova Cat",
        description="A sleepy orange kitten with a happy tail.",
        body=(255, 190, 96),
        belly=(255, 238, 205),
        outline=(150, 92, 40),
        eye=(70, 46, 26),
        accent=(255, 150, 170),
        ear_type="point",
        tail_type="curved",
        muzzle="cat",
    ),
    PetSpec(
        slug="fox",
        display_name="Nova Fox",
        description="A curious little fox with a big bushy tail.",
        body=(255, 130, 90),
        belly=(255, 236, 214),
        outline=(140, 62, 40),
        eye=(60, 38, 24),
        accent=(250, 240, 220),
        ear_type="point",
        tail_type="bushy",
        ear_tips=(255, 240, 220),
        muzzle="plain",
    ),
    PetSpec(
        slug="panda",
        display_name="Nova Panda",
        description="A chubby black-and-white panda who loves snacks.",
        body=(240, 240, 240),
        belly=(255, 255, 255),
        outline=(70, 74, 86),
        eye=(46, 50, 62),
        accent=(70, 74, 86),
        ear_type="round",
        tail_type="stub",
        muzzle="panda",
    ),
]


# ─── Frame parameterisation ────────────────────────────────────────────

def frame_params(row_name: str, column: int, count: int) -> dict:
    """Turn (row, column) into pose parameters for the generic drawer."""
    phase = column / max(count - 1, 1)
    two_pi = phase * math.tau
    p: dict = {}

    if row_name == "idle":
        p["bob"] = -1.2 * math.sin(two_pi)
        p["blink"] = column == 3
        p["sway"] = 0.4 * math.sin(two_pi * 2)
    elif row_name == "running-right":
        p["bob"] = -2.0 * abs(math.sin(math.pi * phase))
        p["x_shift"] = 2.2 * math.sin(two_pi)
        p["tilt"] = -1.0
        p["leg_cycle"] = math.sin(two_pi)
    elif row_name == "running-left":
        p["bob"] = -2.0 * abs(math.sin(math.pi * phase))
        p["x_shift"] = -2.2 * math.sin(two_pi)
        p["tilt"] = 1.0
        p["leg_cycle"] = math.sin(two_pi)
    elif row_name == "waving":
        p["bob"] = -0.9 * math.sin(two_pi)
        p["wave"] = math.sin(two_pi * 2)
        p["smile_big"] = True
    elif row_name == "jumping":
        p["bob"] = -7.0 * math.sin(math.pi * phase)
        p["arms_up"] = True
        p["legs_tucked"] = True
        p["smile_big"] = True
    elif row_name == "failed":
        p["bob"] = 0.6 * math.sin(two_pi)
        p["sad"] = True
        p["sweat"] = column % 3 == 0
        p["head_down"] = 0.6 * math.sin(two_pi)
    elif row_name == "waiting":
        p["sway"] = 1.4 * math.sin(two_pi)
        p["blink"] = column == 4
        p["ear_twitch"] = column % 2 == 1
    elif row_name == "running":
        p["bob"] = -2.6 * abs(math.sin(two_pi))
        p["tilt"] = -1.2 * math.sin(two_pi)
        p["motion_lines"] = True
        p["leg_cycle"] = math.sin(two_pi)
    else:  # review
        p["sway"] = 1.8 * math.sin(phase * math.tau * 1.5)
        p["eye_dart"] = math.sin(phase * math.tau * 3) * 1.2
        p["sparkle"] = column % 2 == 0

    return p


# ─── Drawing ───────────────────────────────────────────────────────────

def draw_frame(spec: PetSpec, row_name: str, column: int, count: int) -> Image.Image:
    img = Image.new("RGBA", (GRID_W, GRID_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = frame_params(row_name, column, count)

    cx = GRID_W / 2 + p.get("x_shift", 0.0)
    cy = GRID_H / 2 + p.get("bob", 0.0)
    sway = p.get("sway", 0.0)

    # Ground shadow.
    d.ellipse((cx - 6, GRID_H - 3, cx + 6, GRID_H), fill=(0, 0, 0, 50))

    # Tail (behind the body).
    tail_type = spec.tail_type
    if tail_type == "curved":
        d.arc((cx - 11, cy + 3, cx - 1, cy + 11), 60, 220, fill=spec.outline, width=2)
    elif tail_type == "bushy":
        d.ellipse((cx - 13, cy + 7, cx - 5, cy + 12), fill=spec.body, outline=spec.outline, width=1)
        d.polygon([(cx - 13, cy + 9), (cx - 17, cy + 8), (cx - 15, cy + 13), (cx - 12, cy + 12)], fill=spec.body)
    elif tail_type == "stub":
        d.ellipse((cx - 9, cy + 10, cx - 3, cy + 13), fill=spec.outline)
    elif tail_type == "antenna":
        d.line((cx + 6, cy - 9, cx + 8, cy - 13), fill=spec.outline, width=1)
        d.ellipse((cx + 6.5, cy - 14.5, cx + 9.5, cy - 12.5), fill=spec.accent)

    # Body.
    body_w, body_h = 12, 10
    body_top = cy + 1
    d.ellipse(
        (cx - body_w / 2, body_top, cx + body_w / 2, body_top + body_h),
        fill=spec.body, outline=spec.outline, width=1,
    )
    d.ellipse((cx - 2.5, body_top + 5, cx + 2.5, body_top + 8), fill=spec.belly)

    # Legs.
    if p.get("legs_tucked"):
        d.ellipse((cx - 5, cy + 9, cx - 1.5, cy + 12), fill=spec.body, outline=spec.outline, width=1)
        d.ellipse((cx + 1.5, cy + 9, cx + 5, cy + 12), fill=spec.body, outline=spec.outline, width=1)
    else:
        leg_cycle = p.get("leg_cycle", 0.0)
        lift = abs(leg_cycle)
        for sign in (-1, 1):
            lx = cx + sign * 3 + sign * leg_cycle
            ly = cy + 8 - lift * 0.8
            d.ellipse((lx - 1.5, ly, lx + 1.5, ly + 3.5), fill=spec.body, outline=spec.outline, width=1)

    # Head.
    head_down = p.get("head_down", 0.0)
    head_w, head_h = 11, 9
    hx = cx + sway * 0.6
    hy = cy - 3 + head_down
    d.ellipse(
        (hx - head_w / 2, hy - head_h / 2, hx + head_w / 2, hy + head_h / 2),
        fill=spec.body, outline=spec.outline, width=1,
    )

    # Ears.
    ear_type = spec.ear_type
    ear_tip = spec.ear_tips or spec.accent
    for sign in (-1, 1):
        ex = hx + sign * 3
        ey = hy - 3.4
        if p.get("ear_twitch") and sign == 1:
            ex += 0.8
            ey -= 0.8
        if ear_type == "point":
            d.polygon(
                [(ex - 1.8, ey + 1), (ex + 1.8, ey + 1), (ex + sign * 1.4, ey - 3)],
                fill=spec.body, outline=spec.outline, width=1,
            )
            if spec.ear_tips:
                d.polygon(
                    [(ex - 1.2, ey + 0.4), (ex + 1.2, ey + 0.4), (ex + sign * 1.0, ey - 2.2)],
                    fill=ear_tip,
                )
        elif ear_type == "round":
            d.ellipse((ex - 2.4, ey - 2.4, ex + 2.4, ey + 2.4), fill=spec.accent, outline=spec.outline, width=1)
        elif ear_type == "antenna":
            d.line((hx, hy - 4, hx, hy - 7), fill=spec.outline, width=1)
            d.ellipse((hx - 1.2, hy - 8.2, hx + 1.2, hy - 5.8), fill=spec.accent)

    # Face.
    eye_y = hy + 0.5
    if p.get("sad"):
        for sign in (-1, 1):
            exx = hx + sign * 3
            d.line((exx - 1.4, eye_y - 1.4, exx + 1.4, eye_y + 1.4), fill=spec.eye, width=1)
            d.line((exx + 1.4, eye_y - 1.4, exx - 1.4, eye_y + 1.4), fill=spec.eye, width=1)
    elif p.get("blink"):
        for sign in (-1, 1):
            d.line((hx + sign * 3 - 1.6, eye_y, hx + sign * 3 + 1.6, eye_y), fill=spec.eye, width=1)
    else:
        dart = p.get("eye_dart", 0.0)
        for sign in (-1, 1):
            exx = hx + sign * 3
            d.ellipse((exx - 1.5, eye_y - 1.5, exx + 1.5, eye_y + 1.5), fill=spec.eye)
            d.ellipse((exx - 0.5 + dart * 0.3, eye_y - 0.5, exx + 0.4 + dart * 0.3, eye_y + 0.4), fill=(255, 255, 255))

    # Panda eye patches.
    if spec.muzzle == "panda":
        for sign in (-1, 1):
            d.ellipse((hx + sign * 3 - 2.2, eye_y - 2.2, hx + sign * 3 + 2.2, eye_y + 2.2), fill=spec.accent)

    # Mouth / nose.
    mouth_y = hy + 3
    if p.get("sad"):
        d.arc((hx - 1.8, mouth_y, hx + 1.8, mouth_y + 2.2), 0, 180, fill=spec.outline, width=1)
    else:
        arc_lo = 190 if p.get("smile_big") else 210
        arc_hi = 350 if p.get("smile_big") else 330
        d.arc((hx - 1.8, mouth_y - 1, hx + 1.8, mouth_y + 1.2), arc_lo, arc_hi, fill=spec.outline, width=1)
        d.ellipse((hx - 0.5, mouth_y - 0.8, hx + 0.5, mouth_y + 0.2), fill=spec.outline)

    # Cat whiskers + cheeks.
    if spec.muzzle == "cat":
        for sign in (-1, 1):
            d.line((hx + sign * 3.4, mouth_y - 0.5, hx + sign * 5.6, mouth_y - 1.4), fill=spec.outline, width=1)
            d.line((hx + sign * 3.4, mouth_y + 0.6, hx + sign * 5.6, mouth_y + 0.6), fill=spec.outline, width=1)
            d.ellipse((hx + sign * 4.4 - 0.7, hy + 1.5, hx + sign * 4.4 + 0.7, hy + 2.9), fill=(255, 150, 170, 160))

    # Arms.
    if p.get("arms_up"):
        d.line((hx - 5, cy + 1, hx - 7, cy - 2), fill=spec.outline, width=1)
        d.line((hx + 5, cy + 1, hx + 7, cy - 2), fill=spec.outline, width=1)
    elif "wave" in p:
        wx = hx + 5.5
        wy = cy - 1 - max(0.0, p["wave"]) * 3.4
        d.line((hx + 4, cy + 1, wx, wy), fill=spec.outline, width=1)
        d.ellipse((wx - 1.2, wy - 1.2, wx + 1.2, wy + 1.2), fill=spec.body)

    # Effects.
    if p.get("sweat"):
        d.ellipse((hx + 5.5, hy - 5.5, hx + 6.6, hy - 4.4), fill=(130, 190, 255))
    if p.get("motion_lines"):
        for i in range(2):
            d.line((cx - 8.5 - i, cy - 2 + i * 2.4, cx - 5.5 - i, cy - 2 + i * 2.4), fill=(0, 0, 0, 90), width=1)
    if p.get("sparkle"):
        s = column % 3
        d.ellipse((hx - 7, hy - 6 - s, hx - 6, hy - 5 - s), fill=(255, 220, 110))

    return img.resize((CELL_W, CELL_H), Image.Resampling.NEAREST)


# ─── Pack assembly ─────────────────────────────────────────────────────

def build_atlas(spec: PetSpec) -> Image.Image:
    atlas = Image.new("RGBA", (COLUMNS * CELL_W, ROWS * CELL_H), (0, 0, 0, 0))
    for row, (name, count) in enumerate(ROW_LAYOUT):
        for column in range(count):
            frame = draw_frame(spec, name, column, count)
            atlas.paste(frame, (column * CELL_W, row * CELL_H))
    return atlas


def write_manifest(pack_dir: Path, spec: PetSpec) -> None:
    pet_id = f"{spec.slug}--{AUTHOR_SLUG}"
    pack_dir.mkdir(parents=True, exist_ok=True)

    pet_json = {
        "id": pet_id,
        "displayName": spec.display_name,
        "description": spec.description,
        "spritesheetPath": "spritesheet.webp",
        "spriteVersionNumber": 1,
    }
    (pack_dir / "pet.json").write_text(
        json.dumps(pet_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    submission = {
        "slug": pet_id,
        "pet_slug": spec.slug,
        "author_slug": AUTHOR_SLUG,
        "name": spec.display_name,
        "author": "Nova Lab",
        "primary_category": "Original",
        "tags": [spec.slug, "nova", "pixel"],
        "license": "CC BY-NC 4.0",
        "description": spec.description,
        "codex_install": {"pet_json": "pet.json", "spritesheet": "spritesheet.webp"},
    }
    (pack_dir / "submission.json").write_text(
        json.dumps(submission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def validate_atlas(path: Path, *, min_used_pixels: int = 50) -> list[str]:
    """Mirror of the awesome-codex-pet validator (kept dependency-free)."""
    errors: list[str] = []
    image = Image.open(path).convert("RGBA")
    if image.size != (COLUMNS * CELL_W, ROWS * CELL_H):
        errors.append(f"bad size {image.size}")
    for row, (name, count) in enumerate(ROW_LAYOUT):
        for column in range(COLUMNS):
            cell = image.crop(
                (column * CELL_W, row * CELL_H, (column + 1) * CELL_W, (row + 1) * CELL_H)
            )
            alpha = cell.getchannel("A")
            nontransparent = sum(alpha.histogram()[1:])
            used = column < count
            if used and nontransparent < min_used_pixels:
                errors.append(f"{name} row {row} col {column} too sparse ({nontransparent})")
            if not used and nontransparent != 0:
                errors.append(f"{name} row {row} unused col {column} not transparent")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="validate generated atlases")
    parser.add_argument("--out", type=Path, default=ASSETS, help="output pets folder")
    args = parser.parse_args()

    failed = False
    args.out.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        pet_id = f"{spec.slug}--{AUTHOR_SLUG}"
        pack_dir = args.out / pet_id
        write_manifest(pack_dir, spec)
        atlas = build_atlas(spec)
        atlas_path = pack_dir / "spritesheet.webp"
        atlas.save(atlas_path, format="WEBP", lossless=True)

        if args.validate:
            errors = validate_atlas(atlas_path)
            status = "OK" if not errors else f"FAIL: {errors}"
            print(f"{pet_id}: {status}")
            failed = failed or bool(errors)
        else:
            print(f"{pet_id}: wrote {atlas_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
