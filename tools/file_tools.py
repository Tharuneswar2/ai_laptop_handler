"""
tools/file_tools.py — Safe file and folder operations.

Supports: create file, create folder, move, rename, delete (with confirmation), search.
All paths are sanitized via pathlib and restricted to the user's home directory.
"""

import logging
import shutil
from pathlib import Path

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)

HOME = Path.home()


# ─── Path Safety ──────────────────────────────────────────────────────

def _safe_path(raw: str) -> Path:
    """
    Resolve and sanitize a path. Expands ~ and ensures it stays
    within the user's home directory.
    """
    path = Path(raw).expanduser().resolve()

    # Block paths outside home directory
    try:
        path.relative_to(HOME)
    except ValueError:
        raise ValueError(f"Path '{path}' is outside the home directory. Blocked for safety.")

    return path


# ─── Confirmation Helper ─────────────────────────────────────────────

def _confirm(message: str) -> bool:
    """Ask the user for confirmation in the terminal."""
    try:
        response = input(f"⚠️  {message} (yes/no): ").strip().lower()
        return response in ("yes", "y")
    except (EOFError, KeyboardInterrupt):
        return False


# ─── File Operations ─────────────────────────────────────────────────

def create_file(path: str) -> ToolResult:
    """Create a new empty file."""
    try:
        target = _safe_path(path)
        if target.exists():
            return ToolResult(success=False, message=f"File already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        logger.info("Created file: %s", target)
        return ToolResult(success=True, message=f"Created file: {target}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to create file: {e}")


def create_folder(path: str) -> ToolResult:
    """Create a new directory (and any missing parents)."""
    try:
        target = _safe_path(path)
        if target.exists():
            return ToolResult(success=False, message=f"Folder already exists: {target}")
        target.mkdir(parents=True, exist_ok=True)
        logger.info("Created folder: %s", target)
        return ToolResult(success=True, message=f"Created folder: {target}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to create folder: {e}")


def move_file(source: str, destination: str) -> ToolResult:
    """Move a file or folder to a new location."""
    try:
        src = _safe_path(source)
        dst = _safe_path(destination)
        if not src.exists():
            return ToolResult(success=False, message=f"Source not found: {src}")
        shutil.move(str(src), str(dst))
        logger.info("Moved: %s → %s", src, dst)
        return ToolResult(success=True, message=f"Moved {src.name} to {dst}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to move: {e}")


def rename_file(source: str, new_name: str) -> ToolResult:
    """Rename a file or folder."""
    try:
        src = _safe_path(source)
        if not src.exists():
            return ToolResult(success=False, message=f"Not found: {src}")
        new_path = src.parent / new_name
        src.rename(new_path)
        logger.info("Renamed: %s → %s", src, new_path)
        return ToolResult(success=True, message=f"Renamed {src.name} to {new_name}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to rename: {e}")


def delete_file(path: str) -> ToolResult:
    """Delete a file or folder — requires user confirmation."""
    try:
        target = _safe_path(path)
        if not target.exists():
            return ToolResult(success=False, message=f"Not found: {target}")

        # Require confirmation
        if not _confirm(f"Are you sure you want to delete '{target}'?"):
            return ToolResult(success=False, message="Delete cancelled by user.")

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

        logger.info("Deleted: %s", target)
        return ToolResult(success=True, message=f"Deleted: {target}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to delete: {e}")


def search_files(pattern: str, search_dir: str = None) -> ToolResult:
    """Search for files matching a glob pattern."""
    try:
        base = _safe_path(search_dir) if search_dir else HOME
        matches = list(base.rglob(f"*{pattern}*"))[:20]  # limit results

        if not matches:
            return ToolResult(success=True, message=f"No files found matching '{pattern}'.")

        file_list = "\n".join(f"  • {m}" for m in matches)
        return ToolResult(
            success=True,
            message=f"Found {len(matches)} file(s) matching '{pattern}':\n{file_list}",
            data={"files": [str(m) for m in matches]},
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Search failed: {e}")


# ─── Handler ──────────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route file tool actions to the correct function."""
    action = intent.action
    params = intent.params

    if action == "create_file":
        return create_file(params.get("path", ""))
    elif action == "create_folder":
        return create_folder(params.get("path", ""))
    elif action == "move":
        return move_file(params.get("source", ""), params.get("destination", ""))
    elif action == "rename":
        return rename_file(params.get("source", ""), params.get("new_name", ""))
    elif action == "delete":
        return delete_file(params.get("path", ""))
    elif action == "search":
        return search_files(params.get("pattern", ""))
    else:
        return ToolResult(success=False, message=f"Unknown file action: {action}")
