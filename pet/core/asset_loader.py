"""
pet/core/asset_loader.py — Codex-style pet pack loading.

A pet pack is a folder following the ``awesome-codex-pet`` convention:

    pets/<pet-slug>--<author-slug>/
    ├── submission.json     # repository/curation metadata (optional for runtime)
    ├── pet.json            # runtime metadata: id, displayName, spritesheetPath
    └── spritesheet.webp    # atlas, 1536x1872 (v1) or 1536x2288 (v2)

Atlas layout (v1, from the awesome-codex-pet validation tools):

    1536x1872, 8 columns x 9 rows, frame 192x208
    row 0 idle (6)       row 1 running-right (8)   row 2 running-left (8)
    row 3 waving (4)     row 4 jumping (5)         row 5 failed (8)
    row 6 waiting (6)    row 7 running (6)         row 8 review (6)

v2 adds two look-direction rows.  The loader slices used cells only, so
unused cells may stay transparent (as the community validator requires).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from .state_machine import PetState

logger = logging.getLogger(__name__)

# ─── Codex atlas constants (v1 / v2) ───────────────────────────────────
COLUMNS = 8
CELL_WIDTH = 192
CELL_HEIGHT = 208
V1_ROWS = 9
V2_ROWS = 11
V1_ATLAS_SIZE = (COLUMNS * CELL_WIDTH, V1_ROWS * CELL_HEIGHT)
V2_ATLAS_SIZE = (COLUMNS * CELL_WIDTH, V2_ROWS * CELL_HEIGHT)

#: (row index, animation name, used frame count) for v1 atlases.
ROW_BY_INDEX: tuple[tuple[int, str, int], ...] = (
    (0, "idle", 6),
    (1, "running-right", 8),
    (2, "running-left", 8),
    (3, "waving", 4),
    (4, "jumping", 5),
    (5, "failed", 8),
    (6, "waiting", 6),
    (7, "running", 6),
    (8, "review", 6),
)

#: v2 adds two rows of 8 clockwise look directions (not used by the engine).
V2_ROW_BY_INDEX: tuple[tuple[int, str, int], ...] = ROW_BY_INDEX + (
    (9, "look-000-to-157.5", 8),
    (10, "look-180-to-337.5", 8),
)

#: Engine states -> default animation row name in the atlas.
DEFAULT_STATE_TO_ANIMATION: dict[PetState, str] = {
    PetState.IDLE: "idle",
    PetState.LISTENING: "waiting",
    PetState.THINKING: "review",
    PetState.WORKING: "running",
    PetState.SPEAKING: "waving",
    PetState.HAPPY: "jumping",
    PetState.SLEEPING: "idle",
    PetState.ERROR: "failed",
}

ANIMATION_ROW: dict[str, tuple[int, int]] = {
    name: (row, count) for row, name, count in ROW_BY_INDEX
}


class PetPackError(RuntimeError):
    """Raised when a pet pack cannot be loaded."""


@dataclass
class PetPack:
    """
    A loaded pet pack.

    ``frames`` maps an animation name to a tuple of RGBA PIL images sliced
    from the atlas.  ``states`` maps a :class:`PetState` to an animation name.
    """

    id: str
    display_name: str
    description: str
    pack_dir: Path
    sprite_version: int
    frames: dict[str, tuple[Image.Image, ...]] = field(default_factory=dict)
    states: dict[PetState, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def animation_for(self, state: PetState) -> str | None:
        """Return the animation row name for ``state`` (or None)."""
        return self.states.get(state)

    @property
    def animations(self) -> list[str]:
        """Names of all animations available in the atlas."""
        return list(self.frames.keys())


@dataclass
class PackManifest:
    """Parsed ``pet.json`` (+ optional ``submission.json``) metadata."""

    id: str
    display_name: str
    description: str
    spritesheet_path: str = "spritesheet.webp"
    sprite_version: int = 1
    state_overrides: dict[str, str] = field(default_factory=dict)
    animation_fps: dict[str, float] = field(default_factory=dict)
    submission: dict[str, Any] = field(default_factory=dict)


class AssetLoader:
    """
    Discovers and loads pet packs from the asset root.

    ``load_pack`` resolves a pack by id, by directory name or by path, and
    slices its spritesheet into per-animation frames ready for playback.
    """

    def __init__(
        self,
        asset_root: Path | str,
        pets_dir: str = "pets",
        packs_root: Path | str | None = None,
    ) -> None:
        self.asset_root = Path(asset_root)
        self.packs_root = Path(packs_root) if packs_root is not None else None
        self.pets_root = self.packs_root if self.packs_root is not None else self.asset_root / pets_dir

    # ─── Discovery ─────────────────────────────────────────────────────

    def discover(self) -> dict[str, Path]:
        """
        Scan the pets folder and return ``{pack_id: pack_directory}``.

        A directory counts as a pack when it contains a ``pet.json``.
        The pack id is read from ``pet.json`` (falling back to the folder
        name, matching the Codex ``<slug>--<author>`` convention).
        """
        packs: dict[str, Path] = {}
        if not self.pets_root.is_dir():
            logger.warning("Pets root not found: %s", self.pets_root)
            return packs
        for entry in sorted(self.pets_root.iterdir()):
            if not entry.is_dir():
                continue
            pet_json = entry / "pet.json"
            if not pet_json.exists():
                continue
            try:
                manifest = self._parse_manifest(pet_json)
            except PetPackError as exc:
                logger.warning("Skipping invalid pack %s: %s", entry.name, exc)
                continue
            packs[manifest.id] = entry
        return packs

    def list_pets(self) -> list[dict[str, str]]:
        """Human readable list of the installed packs (for CLIs/UI)."""
        return [
            {"id": pack_id, "dir": str(path)}
            for pack_id, path in sorted(self.discover().items())
        ]

    def resolve(self, pack: str | Path) -> Path:
        """
        Resolve ``pack`` to a pack directory.

        Accepts an id (``robot--nova``), a bare slug (``robot``, matched via
        ``pet_slug`` or the ``<slug>--<author>`` prefix), a directory name, a
        relative path under the pets root, or an absolute path.
        """
        candidate = Path(pack)
        if candidate.is_absolute() and (candidate / "pet.json").exists():
            return candidate
        relative = self.pets_root / candidate
        if (relative / "pet.json").exists():
            return relative
        # Match by id, by pet_slug, or by the <slug>--<author> prefix.
        for directory in self.discover().values():
            manifest = self._parse_manifest(directory / "pet.json")
            if manifest.id == str(pack):
                return directory
            if manifest.submission.get("pet_slug") == str(pack):
                return directory
            if manifest.id.startswith(f"{pack}--"):
                return directory
        raise PetPackError(
            f"No pet pack found for {pack!r} under {self.pets_root}. "
            "Expected a folder with pet.json + spritesheet.webp."
        )

    # ─── Loading ───────────────────────────────────────────────────────

    def load_pack(self, pack: str | Path) -> PetPack:
        """
        Load a full pet pack (metadata + sliced frames).

        Args:
            pack: Pack id, directory name or path.

        Returns:
            A :class:`PetPack` with all animations sliced and cached.

        Raises:
            PetPackError: when the pack is missing or malformed.
        """
        directory = self.resolve(pack)
        manifest = self._parse_manifest(directory / "pet.json")

        spritesheet = directory / manifest.spritesheet_path
        if not spritesheet.exists():
            raise PetPackError(f"Spritesheet missing for {manifest.id}: {spritesheet}")

        frames = self._slice_atlas(spritesheet, manifest.sprite_version)
        states = self._build_state_map(manifest, set(frames.keys()))

        return PetPack(
            id=manifest.id,
            display_name=manifest.display_name,
            description=manifest.description,
            pack_dir=directory,
            sprite_version=manifest.sprite_version,
            frames=frames,
            states=states,
            metadata={"submission": manifest.submission, "animation_fps": manifest.animation_fps},
        )

    # ─── Internals ─────────────────────────────────────────────────────

    def _parse_manifest(self, pet_json: Path) -> PackManifest:
        try:
            with pet_json.open("r", encoding="utf-8") as handle:
                raw: dict[str, Any] = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise PetPackError(f"Could not parse {pet_json}: {exc}") from exc

        if "id" not in raw:
            raise PetPackError(f"{pet_json.name} is missing required field 'id'")
        if "spritesheetPath" not in raw:
            raise PetPackError(f"{pet_json.name} is missing required field 'spritesheetPath'")

        version = int(raw.get("spriteVersionNumber", 1))
        if version not in (1, 2):
            logger.warning("Unknown spriteVersionNumber %s, treating as v1", version)
            version = 1

        submission: dict[str, Any] = {}
        submission_path = pet_json.parent / "submission.json"
        if submission_path.exists():
            try:
                with submission_path.open("r", encoding="utf-8") as handle:
                    submission = json.load(handle)
            except (OSError, json.JSONDecodeError):
                logger.warning("Ignoring malformed submission.json for %s", pet_json.parent)

        return PackManifest(
            id=str(raw["id"]),
            display_name=str(raw.get("displayName", raw["id"])),
            description=str(raw.get("description", "")),
            spritesheet_path=str(raw.get("spritesheetPath", "spritesheet.webp")),
            sprite_version=version,
            state_overrides={
                str(key).upper(): str(value)
                for key, value in (raw.get("states") or {}).items()
            },
            animation_fps={
                str(key): float(value)
                for key, value in (raw.get("animationFps") or {}).items()
            },
            submission=submission,
        )

    def _slice_atlas(
        self, path: Path, version: int
    ) -> dict[str, tuple[Image.Image, ...]]:
        """Slice a spritesheet into ``{animation_name: (frames, ...)}``."""
        try:
            with Image.open(path) as opened:
                atlas = opened.convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            raise PetPackError(f"Could not open spritesheet {path}: {exc}") from exc

        expected = V2_ATLAS_SIZE if version == 2 else V1_ATLAS_SIZE
        if atlas.size != expected:
            logger.warning(
                "Spritesheet %s is %sx%s, expected %sx%s",
                path, atlas.width, atlas.height, *expected,
            )

        row_spec = V2_ROW_BY_INDEX if version == 2 else ROW_BY_INDEX
        frames: dict[str, tuple[Image.Image, ...]] = {}
        for row, name, count in row_spec:
            cell_width = atlas.width // COLUMNS
            cell_height = atlas.height // len(row_spec)
            cells: list[Image.Image] = []
            for column in range(count):
                left = column * cell_width
                top = row * cell_height
                if left + cell_width > atlas.width or top + cell_height > atlas.height:
                    break
                cells.append(atlas.crop((left, top, left + cell_width, top + cell_height)))
            if cells:
                frames[name] = tuple(cells)
        return frames

    def _build_state_map(
        self, manifest: PackManifest, available: set[str]
    ) -> dict[PetState, str]:
        """
        Map engine states to animation row names.

        ``pet.json`` may override the default mapping with a custom
        ``"states"`` object (ignored by Codex, honoured by the engine).
        Overrides that reference a missing row fall back to the default.
        """
        states: dict[PetState, str] = {}
        for state, default in DEFAULT_STATE_TO_ANIMATION.items():
            override = manifest.state_overrides.get(state.value.upper())
            if override and override in available:
                states[state] = override
            elif default in available:
                states[state] = default
        return states


__all__ = [
    "AssetLoader",
    "PetPack",
    "PetPackError",
    "PackManifest",
    "DEFAULT_STATE_TO_ANIMATION",
    "ANIMATION_ROW",
    "CELL_WIDTH",
    "CELL_HEIGHT",
    "COLUMNS",
    "V1_ATLAS_SIZE",
    "V2_ATLAS_SIZE",
]
