"""
tools/extended_tools.py — Extended Browser and File operations for AI Desktop Agent.

Implements advanced file management and intelligent browser queries without modifying
original file_tools.py or browser_tools.py modules.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

from router.tool_router import ToolResult

logger = logging.getLogger(__name__)
HOME = Path.home()


# ─── Extended File Operations ─────────────────────────────────────────

def open_latest(file_type: str = "pdf", folder: str = "~/Downloads") -> ToolResult:
    """Find and open the newest file matching a given extension or category."""
    target_dir = Path(folder).expanduser().resolve()
    if not target_dir.exists():
        target_dir = HOME / "Downloads"

    ext = file_type.lower().strip(" .")
    matching_files = [f for f in target_dir.rglob(f"*.{ext}") if f.is_file()]

    if not matching_files:
        # Fallback search all files
        matching_files = [f for f in target_dir.iterdir() if f.is_file()]

    if not matching_files:
        return ToolResult(success=False, message=f"No recent {file_type} files found in {target_dir}")

    matching_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    newest = matching_files[0]

    # Open with default OS viewer
    try:
        if os.name == "nt":
            os.startfile(str(newest))
        else:
            opener = "open" if sys_platform_is_mac() else "xdg-open"
            subprocess.run([opener, str(newest)], check=False)
        return ToolResult(success=True, message=f"Opened newest {ext.upper()} file: '{newest.name}' ({target_dir})")
    except Exception as e:
        return ToolResult(success=False, message=f"Found newest file '{newest.name}' but failed to open: {e}")


def sys_platform_is_mac() -> bool:
    import sys
    return sys.platform == "darwin"


def find_duplicates(folder: str = "~/Downloads") -> ToolResult:
    """Find duplicate files in a directory based on file size and MD5 hash."""
    target_dir = Path(folder).expanduser().resolve()
    if not target_dir.exists():
        return ToolResult(success=False, message=f"Directory not found: {folder}")

    size_map: Dict[int, List[Path]] = {}
    for f in target_dir.rglob("*"):
        if f.is_file():
            s = f.stat().st_size
            if s > 0:
                size_map.setdefault(s, []).append(f)

    duplicates: List[List[Path]] = []
    for s, files in size_map.items():
        if len(files) > 1:
            hashes: Dict[str, List[Path]] = {}
            for f in files:
                try:
                    h = hashlib.md5(f.read_bytes()[:100000]).hexdigest()
                    hashes.setdefault(h, []).append(f)
                except Exception:
                    pass
            for h, h_files in hashes.items():
                if len(h_files) > 1:
                    duplicates.append(h_files)

    if not duplicates:
        return ToolResult(success=True, message=f"No duplicate files found in {target_dir.name}.")

    lines = []
    for group in duplicates[:5]:
        names = ", ".join(f.name for f in group)
        lines.append(f"  • Duplicates ({group[0].stat().st_size // 1024} KB): {names}")

    return ToolResult(
        success=True,
        message=f"Found {len(duplicates)} set(s) of duplicate files in {target_dir.name}:\n" + "\n".join(lines),
        data={"duplicates": [[str(f) for f in g] for g in duplicates]},
    )


def clean_downloads() -> ToolResult:
    """Organize Downloads directory into sorted subfolders (Images, Docs, Code, Media)."""
    downloads = HOME / "Downloads"
    if not downloads.exists():
        return ToolResult(success=False, message="Downloads directory not found.")

    categories = {
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp"},
        "Documents": {".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv"},
        "Archives": {".zip", ".tar", ".gz", ".7z", ".rar"},
        "Code": {".py", ".js", ".html", ".css", ".json", ".sh"},
        "Executables": {".deb", ".AppImage", ".exe", ".msi"},
    }

    moved_count = 0
    for file in downloads.iterdir():
        if file.is_file() and not file.name.startswith("."):
            ext = file.suffix.lower()
            target_cat = "Others"
            for cat, exts in categories.items():
                if ext in exts:
                    target_cat = cat
                    break

            cat_dir = downloads / target_cat
            cat_dir.mkdir(exist_ok=True)
            try:
                shutil.move(str(file), str(cat_dir / file.name))
                moved_count += 1
            except Exception:
                pass

    return ToolResult(success=True, message=f"Cleaned Downloads folder: organized {moved_count} file(s) into subdirectories.")


def archive_downloads() -> ToolResult:
    """Zip or move downloads files older than 30 days into an Archive folder."""
    downloads = HOME / "Downloads"
    archive_dir = downloads / "Archive"
    archive_dir.mkdir(exist_ok=True)

    moved = 0
    now = time.time()
    for file in downloads.iterdir():
        if file.is_file() and not file.name.startswith(".") and file.parent != archive_dir:
            # Check age > 7 days
            if (now - file.stat().st_mtime) > (7 * 86400):
                try:
                    shutil.move(str(file), str(archive_dir / file.name))
                    moved += 1
                except Exception:
                    pass

    return ToolResult(success=True, message=f"Archived {moved} older file(s) into {archive_dir}")


def move_screenshots() -> ToolResult:
    """Move screenshot files from Desktop/Downloads to a dedicated Screenshots directory."""
    pictures_dir = HOME / "Pictures" / "Screenshots"
    pictures_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    search_dirs = [HOME / "Desktop", HOME / "Downloads", HOME]
    for s_dir in search_dirs:
        if s_dir.exists():
            for f in s_dir.glob("*[S|s]creenshot*"):
                if f.is_file():
                    try:
                        shutil.move(str(f), str(pictures_dir / f.name))
                        moved += 1
                    except Exception:
                        pass

    return ToolResult(success=True, message=f"Moved {moved} screenshot(s) to {pictures_dir}")


# ─── Extended Browser Operations ──────────────────────────────────────

DOCS_MAPPING = {
    "fastapi": "https://fastapi.tiangolo.com",
    "python": "https://docs.python.org/3/",
    "react": "https://react.dev",
    "nextjs": "https://nextjs.org/docs",
    "next": "https://nextjs.org/docs",
    "vue": "https://vuejs.org/guide/introduction.html",
    "docker": "https://docs.docker.com",
    "tailwindcss": "https://tailwindcss.com/docs",
    "tailwind": "https://tailwindcss.com/docs",
    "uvicorn": "https://www.uvicorn.org",
    "pydantic": "https://docs.pydantic.dev",
}


def open_doc(topic: str) -> ToolResult:
    """Directly open official documentation for a technology or search Google Docs."""
    if not topic:
        return ToolResult(success=False, message="No documentation topic provided.")

    t_clean = topic.lower().strip()
    url = DOCS_MAPPING.get(t_clean)

    if not url:
        # Check partial key match
        for k, u in DOCS_MAPPING.items():
            if k in t_clean:
                url = u
                break

    if not url:
        encoded = urllib.parse.quote_plus(f"{topic} official documentation")
        url = f"https://www.google.com/search?q={encoded}"

    try:
        webbrowser.open(url)
        return ToolResult(success=True, message=f"Opened documentation for '{topic}': {url}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open docs: {e}")


def watch_tutorial(topic: str) -> ToolResult:
    """Open YouTube search tailored for tutorials."""
    if not topic:
        return ToolResult(success=False, message="No tutorial topic specified.")

    query = f"{topic} tutorial full course"
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.youtube.com/results?search_query={encoded}"

    try:
        webbrowser.open(url)
        return ToolResult(success=True, message=f"Opened YouTube tutorials for '{topic}'.")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open YouTube: {e}")
