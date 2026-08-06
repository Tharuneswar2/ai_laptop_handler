"""
projects/project_manager.py — Enhanced Project Manager with Fuzzy Search & Ambiguity Handling.

Maintains project database, detects project frameworks, handles project aliases,
provides fuzzy matching, and handles project disambiguation.
"""

import json
import logging
import re
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)

PROJECTS_DB = config.DATA_DIR / "projects.db"
DEFAULT_SCAN_DIRS = [
    Path.home() / "Personal_Designs",
    Path.home() / "Projects",
    Path.home() / "Coding",
    Path.home() / "Personal_Projects",
    Path.home() / "Workspace",
    Path.home(),
]

KNOWN_ALIASES = {
    "ai_laptop_handler": "ai laptop handler, nova, assistant, voice handler, laptop handler, ai handler",
    "ai-laptop-handler": "ai laptop handler, nova, assistant, voice handler, laptop handler, ai handler",
}


class ProjectManager:
    """
    Project tracking database, fuzzy search, scanner, and ambiguity resolver.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or PROJECTS_DB
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database table for projects and migrate schema."""
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
                    aliases     TEXT    DEFAULT '',
                    open_count  INTEGER DEFAULT 0
                )
            """)
            # Schema migration check
            cursor = conn.execute("PRAGMA table_info(projects)")
            cols = [row[1] for row in cursor.fetchall()]
            if "aliases" not in cols:
                conn.execute("ALTER TABLE projects ADD COLUMN aliases TEXT DEFAULT ''")
            if "open_count" not in cols:
                conn.execute("ALTER TABLE projects ADD COLUMN open_count INTEGER DEFAULT 0")

            conn.commit()
            conn.close()
            logger.info("Project database ready at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize project database: %s", e)

    def _detect_framework(self, path: Path) -> str:
        """Detect framework by scanning files in directory."""
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
        if "composer.json" in files:
            return "PHP"

        return "General"

    def register_project(
        self,
        name: str,
        path: str,
        aliases: str = "",
        framework: str = None,
        tags: str = "",
    ) -> ToolResult:
        """Register or update project in database."""
        p_path = Path(path).expanduser().resolve()
        if not p_path.exists():
            return ToolResult(success=False, message=f"Project path does not exist: {path}")

        detected_framework = framework or self._detect_framework(p_path)
        last_opened = datetime.now().isoformat()
        clean_aliases = aliases or tags or KNOWN_ALIASES.get(name.lower(), "")

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                INSERT INTO projects (name, path, framework, git_repo, workspace, last_opened, aliases, open_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET
                    path=excluded.path,
                    framework=excluded.framework,
                    last_opened=excluded.last_opened,
                    aliases=CASE WHEN excluded.aliases != '' THEN excluded.aliases ELSE projects.aliases END,
                    open_count=projects.open_count + 1
            """, (name, str(p_path), detected_framework, "", "", last_opened, clean_aliases))
            conn.commit()
            conn.close()
            return ToolResult(success=True, message=f"Registered project '{name}' ({detected_framework}) at {p_path}")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to register project: {e}")

    def add_project(self, name: str, path: str, aliases: str = "", framework: str = None, tags: str = "") -> ToolResult:
        """Alias for register_project."""
        return self.register_project(name, path, aliases=aliases, framework=framework, tags=tags)

    def remove_project(self, name: str) -> ToolResult:
        """Remove a project from tracking."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.execute("DELETE FROM projects WHERE LOWER(name) = LOWER(?)", (name.strip(),))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            if deleted > 0:
                return ToolResult(success=True, message=f"Removed project tracking for '{name}'.")
            return ToolResult(success=False, message=f"Project '{name}' not found.")
        except Exception as e:
            return ToolResult(success=False, message=f"Error removing project: {e}")

    def scan_projects(self) -> ToolResult:
        """Scan system workspace folders for projects."""
        discovered = 0
        project_indicators = [
            ".git", "package.json", "pyproject.toml", "requirements.txt",
            "Cargo.toml", "pom.xml", "go.mod", "composer.json", "main.py"
        ]

        for base in DEFAULT_SCAN_DIRS:
            if not base.exists() or not base.is_dir():
                continue
            try:
                for item in base.iterdir():
                    if item.is_dir() and not item.name.startswith((".", "node_modules", "venv", "__pycache__")):
                        has_indicator = any((item / ind).exists() for ind in project_indicators)
                        if has_indicator:
                            res = self.register_project(name=item.name, path=str(item))
                            if res.success:
                                discovered += 1
            except Exception as e:
                logger.warning("Error scanning directory %s: %s", base, e)

        projects = self.list_projects_data()
        return ToolResult(
            success=True,
            message=f"Scanned workspace directories. Currently tracking {len(projects)} projects ({discovered} updated).",
            data={"count": len(projects)},
        )

    def refresh_database(self) -> ToolResult:
        """Refresh database by re-scanning workspace directories."""
        return self.scan_projects()

    def list_projects_data(self) -> List[Dict[str, Any]]:
        """Fetch all tracked projects sorted by last opened timestamp."""
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

    def search_project(self, query: str) -> List[Dict[str, Any]]:
        """
        Fuzzy search for matching projects.
        Returns a list of candidate project dicts matching the query.
        """
        if not query:
            return []

        q = query.lower().strip()
        # Clean noise words
        q_clean = re.sub(r"\b(open|project|the|my|in|vscode|vs code|code|repo)\b", "", q).strip()
        if not q_clean:
            q_clean = q

        projects = self.list_projects_data()
        if not projects:
            self.scan_projects()
            projects = self.list_projects_data()

        matches = []
        seen_names = set()

        for p in projects:
            p_name = p["name"].lower()
            p_aliases = p.get("aliases", "").lower()
            p_framework = p.get("framework", "").lower()

            # 1. Exact name or alias match
            if q_clean == p_name or (p_aliases and q_clean in [a.strip() for a in p_aliases.split(",")]):
                if p["name"] not in seen_names:
                    matches.insert(0, p)
                    seen_names.add(p["name"])
                    continue

            # 2. Substring match on name or aliases
            if q_clean in p_name or (p_aliases and q_clean in p_aliases) or (p_name in q_clean):
                if p["name"] not in seen_names:
                    matches.append(p)
                    seen_names.add(p["name"])
                    continue

            # 3. Match on framework / tags
            if q_clean in p_framework:
                if p["name"] not in seen_names:
                    matches.append(p)
                    seen_names.add(p["name"])

        # 4. Fallback search on disk if database query yields no match
        if not matches:
            for base in DEFAULT_SCAN_DIRS:
                candidate = base / q_clean
                if candidate.exists() and candidate.is_dir():
                    self.register_project(candidate.name, str(candidate))
                    matches.append({"name": candidate.name, "path": str(candidate), "framework": self._detect_framework(candidate)})
                    break

        return matches

    def find_project(self, query: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Find project matching query.
        Returns Tuple: (single_exact_project_or_None, candidate_matches_list)
        """
        candidates = self.search_project(query)
        if not candidates:
            return (None, [])

        if len(candidates) == 1:
            return (candidates[0], candidates)

        # Check if first candidate is an exact match
        q_clean = re.sub(r"\b(open|project|the|my|in|vscode|vs code|code|repo)\b", "", query.lower()).strip()
        if candidates[0]["name"].lower() == q_clean or q_clean.replace(" ", "_") == candidates[0]["name"].lower() or q_clean.replace(" ", "-") == candidates[0]["name"].lower():
            return (candidates[0], candidates)

        return (None, candidates)

    def open_recent_project(self) -> ToolResult:
        """Fetch the most recently accessed project."""
        projects = self.list_projects_data()
        if not projects:
            self.scan_projects()
            projects = self.list_projects_data()

        if not projects:
            return ToolResult(success=False, message="No recent projects found.")

        recent = projects[0]
        self.touch_project(recent["name"])
        return ToolResult(
            success=True,
            message=f"Found recent project '{recent['name']}' at {recent['path']}",
            data={"project": recent},
        )

    def touch_project(self, name: str) -> None:
        """Update last_opened timestamp and open_count for project."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                UPDATE projects
                SET last_opened = ?, open_count = open_count + 1
                WHERE LOWER(name) = LOWER(?)
            """, (datetime.now().isoformat(), name.strip()))
            conn.commit()
            conn.close()
        except Exception:
            pass


# Singleton instance
_project_manager_instance = None


def get_project_manager() -> ProjectManager:
    """Return global ProjectManager instance."""
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

    if action in ("find", "find_project", "search_project"):
        query = params.get("name", "") or params.get("query", "") or params.get("project_name", "")
        single, candidates = pm.find_project(query)

        if single:
            pm.touch_project(single["name"])
            return ToolResult(
                success=True,
                message=f"Found project '{single['name']}' ({single['framework']}) at {single['path']}",
                data={"project": single, "path": single["path"]},
            )

        if len(candidates) > 1:
            # Format ambiguity resolution question
            lines = [f"{i+1}. {p['name']} ({p['framework']}) → {p['path']}" for i, p in enumerate(candidates[:5])]
            msg = f"I found {len(candidates)} matching projects:\n" + "\n".join(lines) + "\nWhich one would you like to open?"
            return ToolResult(
                success=True,
                message=msg,
                data={"ambiguous": True, "candidates": candidates[:5]},
            )

        return ToolResult(success=False, message=f"No matching project found for '{query}'.")

    elif action in ("open_recent", "get_recent"):
        return pm.open_recent_project()

    elif action in ("list", "list_projects"):
        projects = pm.list_projects_data()
        if not projects:
            pm.scan_projects()
            projects = pm.list_projects_data()

        lines = [f"• {p['name']} ({p['framework']}) → {p['path']}" for p in projects]
        return ToolResult(
            success=True,
            message=f"Tracked Projects ({len(projects)}):\n" + "\n".join(lines),
            data={"projects": projects},
        )

    elif action in ("scan", "scan_projects", "refresh_database"):
        return pm.scan_projects()

    elif action in ("add", "register", "register_project"):
        name = params.get("name", "") or params.get("project_name", "")
        path = params.get("path", "")
        aliases = params.get("aliases", "")
        return pm.register_project(name, path, aliases=aliases)

    elif action in ("remove", "remove_project"):
        return pm.remove_project(params.get("name", ""))

    else:
        return ToolResult(success=False, message=f"Unknown project action: {action}")
