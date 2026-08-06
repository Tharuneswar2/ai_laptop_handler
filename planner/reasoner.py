"""
planner/reasoner.py — Enhanced Goal Reasoner with Negative Guards & App Destination Extraction.

Detects user goal types (OPEN_PROJECT, CONTINUE_PROJECT, DEVELOPER_WORKSPACE, etc.)
from raw or resolved command text while guarding against false positives (browser searches,
simple app opening, file operations).
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GoalType(Enum):
    OPEN_PROJECT = "open_project"
    CONTINUE_PROJECT = "continue_project"
    DEVELOPER_WORKSPACE = "developer_workspace"
    AMBIGUOUS_PROJECT = "ambiguous_project"
    SINGLE_ACTION = "single_action"


@dataclass
class Goal:
    """Structured goal representation."""
    type: GoalType
    target_project: str = ""
    target_app: str = "vscode"  # default app target: vscode, explorer, terminal
    raw_text: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


class GoalReasoner:
    """
    Analyzes user requests to identify high-level goals with negative guard filtering.
    """

    # Negative guards — commands matching these MUST NOT be classified as OPEN_PROJECT
    BROWSER_KEYWORDS = ["youtube", "google", "github", "search", "url", "website", "site", "bookmark", "tab", "documentation", "docs", "tutorial"]
    PLAIN_APPS = ["chrome", "firefox", "vs code", "vscode", "terminal", "file explorer", "explorer", "cmd", "command prompt", "calculator", "notepad"]
    FILE_KEYWORDS = ["folder", "file", "pdf", "resume", "archive", "downloads", "screenshots", "image", "images", "notes.txt", "exam-notes.txt"]

    OPEN_PROJECT_PATTERNS = [
        r"\bopen\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:project|repository|repo|backend|code)\s*(?:in\s+(.+))?\b",
        r"\bopen\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:project|repository|repo|backend)\b",
        r"\bopen\s+(?:my\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+in\s+(?:vs\s*code|vscode|code|file\s+explorer|explorer|terminal)\b",
        r"\bopen\s+(?:project\s+)?([a-zA-Z0-9_\-\.]+)\b",
    ]

    CONTINUE_PATTERNS = [
        r"\bcontinue\s+(?:my\s+|yesterday's\s+)?(?:work|project|backend|frontend|code|task)\b",
        r"\bcontinue\s+([a-zA-Z0-9_\-\.]+)(?:\s+project)?\b",
        r"\bopen\s+(?:my\s+)?(?:last|latest|recent)\s+project\b",
    ]

    DEV_WORKSPACE_PATTERNS = [
        r"\b(start working|prepare for coding|start coding|coding mode|work on backend)\b",
    ]

    def _extract_app_target(self, text: str) -> tuple[str, str]:
        """Extract app target (vscode, explorer, terminal) and return cleaned target project text."""
        lower = text.lower()
        app = "vscode"

        if "file explorer" in lower or "explorer" in lower or "in folder" in lower:
            app = "explorer"
        elif "terminal" in lower or "cmd" in lower or "command prompt" in lower:
            app = "terminal"
        elif "vscode" in lower or "vs code" in lower or "in code" in lower:
            app = "vscode"

        # Remove "in <app>" or "in <anything>" suffix from target
        clean_text = re.sub(r"\s+in\s+(file\s+explorer|explorer|terminal|cmd|vscode|vs\s*code|code|[a-zA-Z0-9_\-]+)\s*$", "", text, flags=re.IGNORECASE).strip()
        return clean_text, app

    def detect_goal(self, text: str) -> Goal:
        """
        Analyze text and return detected Goal object.
        Applies guard filters first to avoid false positives.
        """
        if not text or not text.strip():
            return Goal(type=GoalType.SINGLE_ACTION, raw_text=text)

        raw = text.strip()
        lower = raw.lower()

        # GUARD 1: Browser operations
        for kw in self.BROWSER_KEYWORDS:
            if kw in lower:
                return Goal(type=GoalType.SINGLE_ACTION, raw_text=raw)

        # GUARD 2: Plain app launch commands ("open chrome", "open vs code", "open terminal")
        for app_name in self.PLAIN_APPS:
            if lower == f"open {app_name}" or lower == f"open {app_name}." or lower == f"hey nova, open {app_name}":
                return Goal(type=GoalType.SINGLE_ACTION, raw_text=raw)

        # GUARD 3: File operations ("create folder", "open newest pdf", "find resume")
        if any(lower.startswith(prefix) for prefix in ["create ", "make ", "delete ", "remove ", "rename ", "move ", "find ", "search for ", "clean ", "archive ", "unzip "]):
            return Goal(type=GoalType.SINGLE_ACTION, raw_text=raw)

        if "pdf" in lower or "folder called" in lower or "file called" in lower or "duplicate" in lower:
            return Goal(type=GoalType.SINGLE_ACTION, raw_text=raw)

        # 1. Continue Project Patterns
        for pat in self.CONTINUE_PATTERNS:
            m = re.search(pat, lower)
            if m:
                target = m.group(1).strip() if m.groups() and m.group(1) else ""
                if target in ("my", "yesterday's", "last", "latest", "recent", "work", "project"):
                    target = ""
                clean_target, app = self._extract_app_target(target or raw)
                return Goal(
                    type=GoalType.CONTINUE_PROJECT,
                    target_project=target,
                    target_app=app,
                    raw_text=raw,
                )

        # 2. Developer Workspace Patterns
        for pat in self.DEV_WORKSPACE_PATTERNS:
            if re.search(pat, lower):
                return Goal(
                    type=GoalType.DEVELOPER_WORKSPACE,
                    raw_text=raw,
                )

        # 3. Open Project Patterns
        for pat in self.OPEN_PROJECT_PATTERNS:
            m = re.search(pat, lower)
            if m:
                raw_target = m.group(1).strip()
                clean_target, app = self._extract_app_target(raw_target)

                # Clean noise words except backend
                clean_target = re.sub(r"\b(project|repository|repo|code)\b", "", clean_target, flags=re.IGNORECASE).strip()
                clean_target = re.sub(r"\b(the|my)\b", "", clean_target, flags=re.IGNORECASE).strip()
                if not clean_target and "backend" in raw_target.lower():
                    clean_target = "backend"

                if clean_target and clean_target not in self.PLAIN_APPS and clean_target not in self.FILE_KEYWORDS:
                    return Goal(
                        type=GoalType.OPEN_PROJECT,
                        target_project=clean_target,
                        target_app=app,
                        raw_text=raw,
                    )

        # 4. Explicit project/backend keyword check
        if " project" in lower or "backend" in lower:
            words = lower.split()
            if "open" in words or "launch" in words:
                clean_target, app = self._extract_app_target(lower)
                clean_target = clean_target.replace("open", "").replace("launch", "").replace("project", "").replace("backend", "").replace("my", "").replace("the", "").strip()
                if clean_target:
                    return Goal(
                        type=GoalType.OPEN_PROJECT,
                        target_project=clean_target,
                        target_app=app,
                        raw_text=raw,
                    )

        return Goal(type=GoalType.SINGLE_ACTION, raw_text=raw)
