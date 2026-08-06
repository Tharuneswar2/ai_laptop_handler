"""
brain/memory.py — Conversation memory, history persistence, and context state resolution.

Stores recent interactions in memory (deque) for context, persists commands to SQLite,
and tracks desktop context state (last_app, last_project, last_file, last_command)
for anaphoric pronoun resolution ("open it", "run it again", "open my backend").
"""

import logging
import re
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Global in-memory context store
_CONTEXT_STATE: Dict[str, Any] = {
    "last_app": "chrome",
    "last_file": "",
    "last_folder": "",
    "last_project": "",
    "last_command": "",
    "last_query": "",
    "preferred_browser": "chrome",
    "favorite_ide": "vscode",
    "preferred_terminal": "bash",
}


class Memory:
    """
    Short-term conversation memory + long-term SQLite history + Context Reference Resolver.
    """

    def __init__(self, db_path: Path = None, max_items: int = None):
        import config

        self.max_items = max_items or config.MEMORY_MAX_ITEMS
        self.db_path = db_path or config.HISTORY_DB
        self.recent: deque = deque(maxlen=self.max_items)
        self._init_db()

    def _init_db(self) -> None:
        """Create the history and state tables if they don't exist."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    user_text   TEXT    NOT NULL,
                    intent      TEXT    DEFAULT '',
                    result      TEXT    DEFAULT '',
                    status      TEXT    DEFAULT 'ok',
                    duration_ms INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
            logger.info("History database ready at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize history DB: %s", e)

    def update_context(self, key: str, value: Any) -> None:
        """Update a context state attribute."""
        if value:
            _CONTEXT_STATE[key] = str(value)
            try:
                conn = sqlite3.connect(str(self.db_path))
                conn.execute(
                    "INSERT INTO state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    def get_context_state(self) -> Dict[str, Any]:
        """Get copy of current desktop context state."""
        return dict(_CONTEXT_STATE)

    def resolve_reference(self, text: str) -> str:
        """
        Resolve anaphoric pronouns and implicit references in user text.

        Examples:
          - "open it" -> "open <last_app or last_project>"
          - "close it" -> "close <last_app>"
          - "run it again" -> "<last_command>"
          - "search it on google" -> "search <last_query> on google"
          - "open my backend" -> "open project backend"
          - "open the last pdf" -> "open newest pdf"
        """
        if not text:
            return text

        resolved = text.strip()
        lower = resolved.lower()

        # 1. "run it again" / "execute it again"
        if re.search(r"\b(run|execute)\s+it\s+again\b", lower):
            last_cmd = _CONTEXT_STATE.get("last_command")
            if last_cmd:
                return last_cmd

        # 2. "search it on google" / "search it"
        if re.search(r"\bsearch\s+it(\s+on\s+google)?\b", lower):
            last_q = _CONTEXT_STATE.get("last_query")
            if last_q:
                return f"search google for {last_q}"

        # 3. "open it" / "launch it"
        if re.search(r"^\b(open|launch)\s+it\b", lower):
            last_app = _CONTEXT_STATE.get("last_app")
            last_proj = _CONTEXT_STATE.get("last_project") or _CONTEXT_STATE.get("last_opened_project")
            target = last_proj or last_app
            if target:
                return f"open {target}"

        # 4. "open my last project" / "open my latest project" / "continue yesterday's work"
        if re.search(r"\bopen\s+(my\s+)?(last|latest|recent)\s+project\b", lower) or "continue yesterday" in lower:
            last_proj = _CONTEXT_STATE.get("last_opened_project") or _CONTEXT_STATE.get("last_project")
            if last_proj:
                return f"open project {last_proj}"
            return "open recent project"

        # 5. "open it again" / "run it again"
        if re.search(r"\b(open|run)\s+it\s+again\b", lower):
            last_cmd = _CONTEXT_STATE.get("last_command")
            last_proj = _CONTEXT_STATE.get("last_project")
            if last_cmd:
                return last_cmd
            if last_proj:
                return f"open project {last_proj}"

        # 6. "close it"
        if re.search(r"^\bclose\s+it\b", lower):
            last_app = _CONTEXT_STATE.get("last_app")
            if last_app:
                return f"close {last_app}"

        # 7. "open my backend" / "open backend"
        if re.search(r"\bopen\s+(my\s+)?backend\b", lower):
            return "open project backend"

        # 8. "open the last pdf" / "open newest pdf"
        if re.search(r"\bopen\s+(the\s+)?(last|newest|recent)\s+pdf\b", lower):
            return "open newest pdf"

        return resolved

    def add(
        self,
        user_text: str,
        intent: str,
        result: str,
        status: str = "ok",
        duration_ms: int = 0,
    ) -> None:
        """Add interaction to memory & update context state."""
        timestamp = datetime.now().isoformat()

        # Update context state based on interaction
        if "app.open" in intent:
            m = re.search(r"app_name':\s*'([^']+)'", str(user_text) + str(result))
            if m:
                self.update_context("last_app", m.group(1))
            elif "opened" in result.lower():
                words = result.split()
                if len(words) > 1:
                    self.update_context("last_app", words[-1].strip("."))

        if "vscode" in intent or "project" in intent:
            self.update_context("last_project", user_text.replace("open project", "").strip())

        if "terminal" in intent or "developer" in intent:
            self.update_context("last_command", user_text)

        if "browser" in intent:
            self.update_context("last_query", user_text)

        entry = {
            "timestamp": timestamp,
            "user_text": user_text,
            "intent": intent,
            "result": result,
            "status": status,
        }
        self.recent.append(entry)

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "INSERT INTO history (timestamp, user_text, intent, result, status, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp, user_text, intent, result, status, duration_ms),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to save to history DB: %s", e)

    def get_recent(self, n: int = 5) -> list[dict]:
        """Return the last N interactions from short-term memory."""
        return list(self.recent)[-n:]

    def get_context_string(self, n: int = 5) -> str:
        """Format recent history as a context string for the LLM."""
        recent = self.get_recent(n)
        if not recent:
            return "No previous interactions."

        lines = []
        for entry in recent:
            lines.append(f"User: {entry['user_text']} → {entry['intent']} → {entry['result']}")
        return "\n".join(lines)

    def get_history(self, limit: int = 50) -> list[dict]:
        """Fetch history from the SQLite database."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.error("Failed to fetch history: %s", e)
            return []

    def clear(self) -> None:
        """Clear both short-term memory and persistent history."""
        self.recent.clear()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("DELETE FROM history")
            conn.commit()
            conn.close()
            logger.info("History cleared.")
        except Exception as e:
            logger.error("Failed to clear history: %s", e)
