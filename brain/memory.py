"""
brain/memory.py — Conversation memory and history persistence.

Stores recent interactions in memory (deque) for context,
and persists all commands to SQLite for long-term history.
"""

import logging
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Memory:
    """
    Short-term conversation memory + long-term SQLite history.

    Usage:
        memory = Memory()
        memory.add("open chrome", "browser.open", "Chrome opened successfully")
        recent = memory.get_recent(5)
    """

    def __init__(self, db_path: Path = None, max_items: int = None):
        import config

        self.max_items = max_items or config.MEMORY_MAX_ITEMS
        self.db_path = db_path or config.HISTORY_DB
        self.recent: deque = deque(maxlen=self.max_items)
        self._init_db()

    def _init_db(self) -> None:
        """Create the history table if it doesn't exist."""
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
            conn.commit()
            conn.close()
            logger.info("History database ready at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize history DB: %s", e)

    def add(
        self,
        user_text: str,
        intent: str,
        result: str,
        status: str = "ok",
        duration_ms: int = 0,
    ) -> None:
        """
        Add an interaction to both short-term memory and persistent history.

        Args:
            user_text: What the user said.
            intent: The parsed intent string (e.g., "browser.open").
            result: The result of the action.
            status: "ok" or "error".
            duration_ms: How long the action took.
        """
        timestamp = datetime.now().isoformat()

        # Short-term memory
        entry = {
            "timestamp": timestamp,
            "user_text": user_text,
            "intent": intent,
            "result": result,
            "status": status,
        }
        self.recent.append(entry)

        # Long-term persistence
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
        """
        Format recent history as a context string for the LLM.

        Returns:
            Multi-line string of recent interactions.
        """
        recent = self.get_recent(n)
        if not recent:
            return "No previous interactions."

        lines = []
        for entry in recent:
            lines.append(f"User: {entry['user_text']} → {entry['intent']} → {entry['result']}")
        return "\n".join(lines)

    def get_history(self, limit: int = 50) -> list[dict]:
        """
        Fetch history from the SQLite database.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of history dicts, most recent first.
        """
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
