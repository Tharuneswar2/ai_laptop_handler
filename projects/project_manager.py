"""
projects/project_manager.py — Project Database and Project Manager for AI Desktop Agent.

Maintains a database of software projects, detects frameworks, scans workspaces,
and supports opening, listing, and querying projects.
"""

import json
import logging
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)

PROJECTS_DB = config.DATA_DIR / "projects.db"
DEFAULT_SCAN_DIRS = [
    Path.home() / "Projects",
    Path.home() / "Coding",
    Path.home() / "Personal_Designs",
    Path.home() / "Workspace",
    Path.home(),
]


class ProjectManager:
    """
    Manages project tracking, persistence, framework detection, and scanning.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or PROJECTS_DB
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database table for projects."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    UNIQUE NOT NULL,
                    path        TEXT    NOT NULL,
                    framework   TEXT    DEFAULT 'Python',
                    git_repo    TEXT    DEFAULT '',
                    workspace   TEXT    DEFAULT '',
                    last_opened TEXT    DEFAULT '',
                    tags        TEXT    DEFAULT ''
                )
            """)
            conn.commit()
            conn.close()
            logger.info("Project database ready at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize project database: %s", e)

    def _detect_framework(self, path: Path) -> str:
        """Detect software framework used in project path."""
        if not path.exists() or not path.is_dir():
            return "Unknown"

        files = [f.name.lower() for f in path.iterdir() if f.is_file()]

        if "package.json" in files:
            try:
                content = (path / "package.json").read_text(encoding="utf-8", errors="ignore").lower()
                if "next" in content:
                    return "Next.js"
                if "react" in content:
                    return "React"
                if "vue" in content:
                    return "Vue"
                if "express" in content:
                    return "Express/Node"
                return "Node.js"
            except Exception:
                return "Node.js"

        if "requirements.txt" in files or "pyproject.toml" in files or "setup.py" in files:
            reqs = ""
            if "requirements.txt" in files:
                try:
                    reqs = (path / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
                except Exception:
                    pass
            if "fastapi" in reqs:
                return "FastAPI"
            if "django" in reqs or "manage.py" in files:
                return "Django"
            if "flask" in reqs:
                return "Flask"
            if "streamlit" in reqs:
                return "Streamlit"
            return "Python"

        if "pubspec.yaml" in files:
            return "Flutter"
        if "cargo.toml" in files:
            return "Rust"
        if "go.mod" in files:
            return "Go"
        if "pom.xml" in files or "build.gradle" in files:
            return "Java/Kotlin"

        return "General"

    def _get_git_repo(self, path: Path) -> str:
        """Extract remote git origin URL if present."""
        git_dir = path / ".git"
        if not git_dir.exists():
            return ""

        try:
            res = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return "git"

    def add_project(
        self,
        name: str,
        path: str,
        framework: str = None,
        tags: str = "",
    ) -> ToolResult:
        """Add or update a project in the database."""
        p_path = Path(path).expanduser().resolve()
        if not p_path.exists():
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        detected_framework = framework or self._detect_framework(p_path)
        git_repo = self._get_git_repo(p_path)
        last_opened = datetime.now().isoformat()

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                INSERT INTO projects (name, path, framework, git_repo, workspace, last_opened, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    path=excluded.path,
                    framework=excluded.framework,
                    git_repo=excluded.git_repo,
                    last_opened=excluded.last_opened,
                    tags=excluded.tags
            """, (name, str(p_path), detected_framework, git_repo, "", last_opened, tags))
            conn.commit()
            conn.close()
            logger.info("Added project '%s' (%s) at %s", name, detected_framework, p_path)
            return ToolResult(success=True, message=f"Tracked project '{name}' ({detected_framework}) at {p_path}")
        except Exception as e:
            logger.error("Failed to add project: %s", e)
            return ToolResult(success=False, message=f"Failed to save project: {e}")

    def remove_project(self, name: str) -> ToolResult:
        """Remove a project from tracking by name."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.execute("DELETE FROM projects WHERE LOWER(name) = LOWER(?)", (name.strip(),))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            if deleted > 0:
                return ToolResult(success=True, message=f"Removed project tracking for '{name}'.")
            return ToolResult(success=False, message=f"Project '{name}' not found in database.")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to remove project: {e}")

    def scan_projects(self, max_depth: int = 2) -> ToolResult:
        """Scan common project directories to auto-discover projects."""
        discovered = 0
        for base in DEFAULT_SCAN_DIRS:
            if not base.exists() or not base.is_dir():
                continue

            try:
                for item in base.iterdir():
                    if item.is_dir() and not item.name.startswith((".", "node_modules", "venv", "__pycache__")):
                        # Check if directory looks like a project
                        if (item / ".git").exists() or (item / "requirements.txt").exists() or (item / "package.json").exists() or (item / "main.py").exists():
                            res = self.add_project(name=item.name, path=str(item))
                            if res.success:
                                discovered += 1
            except Exception as e:
                logger.warning("Error scanning directory %s: %s", base, e)

        return ToolResult(
            success=True,
            message=f"Scanned project workspaces. Currently tracking {len(self.list_projects_data())} projects ({discovered} new/updated).",
        )

    def list_projects_data(self) -> List[Dict[str, Any]]:
        """Fetch all tracked projects as dicts."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM projects ORDER BY last_opened DESC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error("Failed to list projects: %s", e)
            return []

    def list_projects(self) -> ToolResult:
        """Format and return all tracked projects."""
        projects = self.list_projects_data()
        if not projects:
            # Try auto-scanning if database is empty
            self.scan_projects()
            projects = self.list_projects_data()

        if not projects:
            return ToolResult(success=True, message="No projects currently tracked.")

        lines = [f"• {p['name']} ({p['framework']}) → {p['path']}" for p in projects]
        return ToolResult(
            success=True,
            message=f"Tracked Projects ({len(projects)}):\n" + "\n".join(lines),
            data={"projects": projects},
        )

    def find_project(self, query: str) -> Optional[Dict[str, Any]]:
        """Search for a project matching a query string (name, tag, path, framework)."""
        if not query:
            return None

        q = query.lower().strip()
        projects = self.list_projects_data()

        # 1. Exact name match
        for p in projects:
            if p["name"].lower() == q:
                return p

        # 2. Substring name match
        for p in projects:
            if q in p["name"].lower() or p["name"].lower() in q:
                return p

        # 3. Tag or framework match
        for p in projects:
            if q in p["framework"].lower() or q in p["tags"].lower():
                return p

        # 4. Fallback search on disk if not in DB
        for base in DEFAULT_SCAN_DIRS:
            candidate = base / query
            if candidate.exists() and candidate.is_dir():
                self.add_project(candidate.name, str(candidate))
                return {"name": candidate.name, "path": str(candidate), "framework": self._detect_framework(candidate)}

        return None

    def open_recent_project(self) -> ToolResult:
        """Fetch and mark the most recently accessed project."""
        projects = self.list_projects_data()
        if not projects:
            self.scan_projects()
            projects = self.list_projects_data()

        if not projects:
            return ToolResult(success=False, message="No recent projects found.")

        recent = projects[0]
        # Update last_opened timestamp
        self.touch_project(recent["name"])
        return ToolResult(
            success=True,
            message=f"Found recent project '{recent['name']}' at {recent['path']}",
            data={"project": recent},
        )

    def touch_project(self, name: str) -> None:
        """Update last_opened timestamp for project."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("UPDATE projects SET last_opened = ? WHERE LOWER(name) = LOWER(?)",
                         (datetime.now().isoformat(), name.strip()))
            conn.commit()
            conn.close()
        except Exception:
            pass


# Singleton instance
_project_manager_instance = None


def get_project_manager() -> ProjectManager:
    """Return the global ProjectManager instance."""
    global _project_manager_instance
    if _project_manager_instance is None:
        _project_manager_instance = ProjectManager()
    return _project_manager_instance


# ─── Handler ──────────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route project tool actions."""
    action = intent.action
    params = intent.params
    pm = get_project_manager()

    if action == "find":
        query = params.get("name", "") or params.get("query", "")
        p = pm.find_project(query)
        if p:
            pm.touch_project(p["name"])
            return ToolResult(
                success=True,
                message=f"Found project '{p['name']}' ({p['framework']}) at {p['path']}",
                data={"project": p},
            )
        return ToolResult(success=False, message=f"Project '{query}' not found.")

    elif action == "open_recent":
        return pm.open_recent_project()

    elif action in ("list", "list_projects"):
        return pm.list_projects()

    elif action in ("scan", "scan_projects"):
        return pm.scan_projects()

    elif action == "add":
        name = params.get("name", "")
        path = params.get("path", "")
        return pm.add_project(name, path, tags=params.get("tags", ""))

    elif action == "remove":
        return pm.remove_project(params.get("name", ""))

    else:
        return ToolResult(success=False, message=f"Unknown project action: {action}")
