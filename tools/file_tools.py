"""File and folder operations with an AI-managed storage boundary."""

import logging
import shutil
from pathlib import Path

import config
from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)
AI_STORAGE = config.AI_STORAGE_DIR.resolve()


def _inside_storage(path: Path) -> bool:
    try:
        path.resolve().relative_to(AI_STORAGE)
        return True
    except ValueError:
        return False


def _storage_path(raw: str) -> Path:
    """Return a normalized path inside AI storage, or reject an external path."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("A file or folder name is required.")

    candidate = Path(value).expanduser()
    # Names and relative paths default to the assistant-owned storage root.
    target = (AI_STORAGE / candidate) if not candidate.is_absolute() else candidate
    target = target.resolve()
    if not _inside_storage(target):
        raise ValueError(
            f"Path '{target}' is outside AI storage ({AI_STORAGE}). "
            "Creation, changes, and deletion are restricted to AI storage."
        )
    return target


def _audit_denial(action: str, raw_path: str, reason: str) -> ToolResult:
    logger.warning("Denied %s for path '%s': %s", action, raw_path, reason)
    return ToolResult(False, f"{action.title()} denied: {reason}", {
        "action": action, "path": raw_path, "reason": reason, "policy": "ai_storage_only",
    })


def create_file(path: str) -> ToolResult:
    try:
        target = _storage_path(path)
        if target.exists():
            return ToolResult(False, f"File already exists: {target}", {"path": str(target)})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        logger.info("Created AI-managed file: %s", target)
        return ToolResult(True, f"Created file: {target}", {"path": str(target), "storage_root": str(AI_STORAGE)})
    except ValueError as exc:
        return _audit_denial("create file", path, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Failed to create file: {exc}")


def create_folder(path: str) -> ToolResult:
    try:
        target = _storage_path(path)
        if target.exists():
            return ToolResult(False, f"Folder already exists: {target}", {"path": str(target)})
        target.mkdir(parents=True, exist_ok=True)
        logger.info("Created AI-managed folder: %s", target)
        return ToolResult(True, f"Created folder: {target}", {"path": str(target), "storage_root": str(AI_STORAGE)})
    except ValueError as exc:
        return _audit_denial("create folder", path, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Failed to create folder: {exc}")


def move_file(source: str, destination: str) -> ToolResult:
    try:
        src, dst = _storage_path(source), _storage_path(destination)
        if not src.exists():
            return ToolResult(False, f"Source not found: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        logger.info("Moved AI-managed path: %s to %s", src, dst)
        return ToolResult(True, f"Moved {src.name} to {dst}", {"source": str(src), "destination": str(dst)})
    except ValueError as exc:
        return _audit_denial("move", f"{source} -> {destination}", str(exc))
    except Exception as exc:
        return ToolResult(False, f"Failed to move: {exc}")


def rename_file(source: str, new_name: str) -> ToolResult:
    try:
        src = _storage_path(source)
        if not src.exists():
            return ToolResult(False, f"Not found: {src}")
        if Path(new_name).name != new_name:
            return _audit_denial("rename", new_name, "The new name must not contain a path.")
        target = src.parent / new_name
        src.rename(target)
        logger.info("Renamed AI-managed path: %s to %s", src, target)
        return ToolResult(True, f"Renamed {src.name} to {new_name}", {"path": str(target)})
    except ValueError as exc:
        return _audit_denial("rename", source, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Failed to rename: {exc}")


def delete_file(path: str) -> ToolResult:
    """Delete only AI-managed files/folders; no terminal prompt blocks API clients."""
    try:
        target = _storage_path(path)
        if not target.exists():
            return ToolResult(False, f"Not found: {target}")
        if target == AI_STORAGE:
            return _audit_denial("delete", path, "The AI storage root itself cannot be deleted.")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        logger.info("Deleted AI-managed path: %s", target)
        return ToolResult(True, f"Deleted: {target}", {"path": str(target), "policy": "ai_storage_only"})
    except ValueError as exc:
        return _audit_denial("delete", path, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Failed to delete: {exc}")


def search_files(pattern: str, search_dir: str = None) -> ToolResult:
    try:
        base = Path(search_dir).expanduser().resolve() if search_dir else AI_STORAGE
        if not base.exists() or not base.is_dir():
            return ToolResult(False, f"Search directory not found: {base}")
        matches = list(base.rglob(f"*{pattern}*"))[:20]
        return ToolResult(True, f"Found {len(matches)} file(s) matching '{pattern}'.", {"files": [str(m) for m in matches]})
    except Exception as exc:
        return ToolResult(False, f"Search failed: {exc}")


def handle(intent: Intent) -> ToolResult:
    action, params = intent.action, intent.params
    if action == "create_file":
        return create_file(params.get("path", ""))
    if action == "create_folder":
        return create_folder(params.get("path", ""))
    if action == "move":
        return move_file(params.get("source", ""), params.get("destination", ""))
    if action == "rename":
        return rename_file(params.get("source", ""), params.get("new_name", ""))
    if action == "delete":
        return delete_file(params.get("path", ""))
    if action == "search":
        return search_files(params.get("pattern", ""), params.get("search_dir"))
    return ToolResult(False, f"Unknown file action: {action}")
