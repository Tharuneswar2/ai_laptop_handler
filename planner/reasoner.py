"""
planner/reasoner.py — Goal Reasoner for AI Desktop Agent.

Detects user goal types (OPEN_PROJECT, CONTINUE_PROJECT, DEVELOPER_WORKSPACE, etc.)
from raw or resolved command text before intent routing.
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
    raw_text: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


class GoalReasoner:
    """
    Analyzes user requests to identify high-level goals.
    """

    OPEN_PROJECT_PATTERNS = [
        r"\bopen\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:project|repository|repo|code)\s*(?:in\s+(?:vs\s*code|vscode|code))?\b",
        r"\bopen\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+in\s+(?:vs\s*code|vscode|code)\b",
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

    def detect_goal(self, text: str) -> Goal:
        """
        Analyze text and return detected Goal object.
        """
        if not text or not text.strip():
            return Goal(type=GoalType.SINGLE_ACTION, raw_text=text)

        raw = text.strip()
        lower = raw.lower()

        # 1. Continue Project Patterns
        for pat in self.CONTINUE_PATTERNS:
            m = re.search(pat, lower)
            if m:
                target = m.group(1).strip() if m.groups() and m.group(1) else ""
                if target in ("my", "yesterday's", "last", "latest", "recent", "work", "project"):
                    target = ""
                return Goal(
                    type=GoalType.CONTINUE_PROJECT,
                    target_project=target,
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
                target = m.group(1).strip()
                # Clean noise words from target
                target = re.sub(r"\b(in|on|using|with)\s+(vscode|vs code|code)\b", "", target).strip()
                if target and target not in ("file", "folder", "browser", "chrome", "settings", "terminal", "app"):
                    return Goal(
                        type=GoalType.OPEN_PROJECT,
                        target_project=target,
                        raw_text=raw,
                    )

        # 4. Check if prompt contains explicit "project" keyword
        if " project" in lower or "backend" in lower or "repo" in lower:
            # Extract target
            words = lower.split()
            if "open" in words or "launch" in words:
                clean = lower.replace("open", "").replace("launch", "").replace("in vscode", "").replace("in vs code", "").replace("project", "").strip()
                if clean:
                    return Goal(type=GoalType.OPEN_PROJECT, target_project=clean, raw_text=raw)

        return Goal(type=GoalType.SINGLE_ACTION, raw_text=raw)
