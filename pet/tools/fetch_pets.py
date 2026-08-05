"""
pet/tools/fetch_pets.py — Download community pet packs into the project.

Fetches the ``pets/`` collection of the awesome-codex-pet repository
(https://github.com/legeling/awesome-codex-pet) and installs each valid
pack into ``pet/assets/pets/``.  Once installed, packs are automatically
discovered by the engine on the next launch — no code changes needed.

Usage::

    python -m pet.tools.fetch_pets                      # fetch everything
    python -m pet.tools.fetch_pets --slug cat --slug gojo   # specific pets
    python -m pet.tools.fetch_pets --dest /some/pets     # custom destination
    python -m pet.tools.fetch_pets --force               # overwrite existing
    python -m pet.tools.fetch_pets --list-only           # list remote pack ids
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import tarfile
import tempfile
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_URL = "https://codeload.github.com/legeling/awesome-codex-pet/tar.gz/refs/heads/main"
DEFAULT_DEST = Path(__file__).resolve().parent.parent / "assets" / "pets"


class FetchError(RuntimeError):
    """Raised when downloading or installing packs fails."""


def _remote_archive() -> bytes:
    """Download the repository tarball (memory buffer)."""
    logger.info("Downloading %s", REPO_URL)
    request = urllib.request.Request(
        REPO_URL,
        headers={"User-Agent": "nova-pet-fetcher/2.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (https only)
            return response.read()
    except OSError as exc:
        raise FetchError(f"Could not download repository: {exc}") from exc


def _iter_pack_dirs(archive: bytes):
    """
    Yield ``(pack_folder_name, extracted_tmp_path)`` for every directory
    in the tarball that looks like a pet pack (has ``pet.json``).
    """
    with tempfile.TemporaryDirectory(prefix="nova-pets-") as tmp:
        root = Path(tmp)
        buffer = io.BytesIO(archive)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            # Safety: reject absolute paths and path traversal.
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in Path(member.name).parts:
                    raise FetchError(f"Unsafe path in archive: {member.name}")
            tar.extractall(root)
        repo_root = next(root.iterdir()) if root.iterdir() else root
        pets_root = repo_root / "pets"
        if not pets_root.is_dir():
            raise FetchError("Archive does not contain a pets/ directory")
        for pack_dir in sorted(pets_root.iterdir()):
            if pack_dir.is_dir() and (pack_dir / "pet.json").exists():
                yield pack_dir.name, pack_dir


def validate_pack_dir(pack_dir: Path) -> list[str]:
    """
    Validate a pack directory, returning a list of error strings.

    A valid pack has a parseable ``pet.json`` with ``id`` +
    ``spritesheetPath`` and an existing spritesheet.
    """
    errors: list[str] = []
    pet_json = pack_dir / "pet.json"
    if not pet_json.exists():
        return ["missing pet.json"]
    try:
        with pet_json.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid pet.json: {exc}"]
    if not isinstance(manifest, dict):
        return ["pet.json must be an object"]
    if "id" not in manifest:
        errors.append("pet.json missing 'id'")
    sheet = manifest.get("spritesheetPath")
    if not sheet:
        errors.append("pet.json missing 'spritesheetPath'")
    elif not (pack_dir / str(sheet)).exists():
        errors.append(f"spritesheet not found: {sheet}")
    return errors


def fetch_pets(
    dest: Path = DEFAULT_DEST,
    slugs: list[str] | None = None,
    *,
    force: bool = False,
    quiet: bool = False,
) -> dict[str, list[str]]:
    """
    Download community pet packs into ``dest``.

    Args:
        dest: Destination directory that will contain the pack folders.
        slugs: Optional list of pack folder names to install (all if empty).
        force: Overwrite packs that already exist.
        quiet: Suppress per-pack log lines.

    Returns:
        ``{"installed": [...], "skipped": [...], "failed": [...], "invalid": [...]}``
    """
    dest.mkdir(parents=True, exist_ok=True)
    stats: dict[str, list[str]] = {
        "installed": [], "skipped": [], "failed": [], "invalid": [],
    }

    archive = _remote_archive()
    for name, pack_dir in _iter_pack_dirs(archive):
        if slugs and name not in slugs:
            continue
        errors = validate_pack_dir(pack_dir)
        if errors:
            logger.warning("Skipping invalid pack %s: %s", name, ", ".join(errors))
            stats["invalid"].append(name)
            continue
        target = dest / name
        if target.exists():
            if not force:
                stats["skipped"].append(name)
                continue
            import shutil

            shutil.rmtree(target)
        import shutil

        shutil.copytree(pack_dir, target)
        stats["installed"].append(name)
        if not quiet:
            logger.info("Installed %s", name)

    return stats


def _list_remote_slugs() -> list[str]:
    """Return the pack folder names available in the repository."""
    return [name for name, _ in _iter_pack_dirs(_remote_archive())]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pet.tools.fetch_pets",
        description="Install community pet packs from awesome-codex-pet into this project.",
    )
    parser.add_argument("--slug", action="append", default=None, help="pack folder name to install (repeatable)")
    parser.add_argument("--dest", default=None, help="destination directory (default: pet/assets/pets)")
    parser.add_argument("--force", action="store_true", help="overwrite already-installed packs")
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    parser.add_argument("--list-only", action="store_true", help="list remote pack ids and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
    )

    dest = Path(args.dest) if args.dest else DEFAULT_DEST

    if args.list_only:
        for name in _list_remote_slugs():
            print(name)
        return 0

    stats = fetch_pets(
        dest=dest,
        slugs=args.slug,
        force=args.force,
        quiet=args.quiet,
    )
    print(
        f"Installed: {len(stats['installed'])}  |  Skipped (already present): "
        f"{len(stats['skipped'])}  |  Invalid: {len(stats['invalid'])}  |  Failed: {len(stats['failed'])}"
    )
    if stats["invalid"]:
        print("Invalid packs skipped:", ", ".join(stats["invalid"]))
    if stats["installed"]:
        print(f"Packs are ready — restart with: python main.py --pet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
