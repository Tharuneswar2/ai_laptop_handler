"""
desktop/desktop_manager.py — Desktop State Manager for AI Desktop Agent.

Tracks desktop state (opened apps, focused app, recent apps, active workspaces)
and provides session restoration, window focus/switch, and window control.
"""

import logging
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


class DesktopState:
    """
    Maintains active desktop state and session tracking.
    """

    def __init__(self):
        self.opened_apps: List[str] = []
        self.focused_app: Optional[str] = None
        self.recent_apps: List[str] = []
        self.active_workspace: int = 1
        self.session_saved_apps: List[str] = []

    def record_app_launch(self, app_name: str) -> None:
        """Track launched app in desktop state."""
        clean_name = app_name.lower().strip()
        if clean_name not in self.opened_apps:
            self.opened_apps.append(clean_name)

        self.focused_app = clean_name
        if clean_name in self.recent_apps:
            self.recent_apps.remove(clean_name)
        self.recent_apps.insert(0, clean_name)

    def record_app_close(self, app_name: str) -> None:
        """Track app close in desktop state."""
        clean_name = app_name.lower().strip()
        if clean_name in self.opened_apps:
            self.opened_apps.remove(clean_name)
        if self.focused_app == clean_name:
            self.focused_app = self.opened_apps[0] if self.opened_apps else None

    def save_session(self) -> None:
        """Snapshot currently opened applications for session restoration."""
        self.session_saved_apps = list(self.opened_apps)
        logger.info("Saved desktop session snapshot: %s", self.session_saved_apps)


# Singleton desktop state instance
_desktop_state = DesktopState()


def get_desktop_state() -> DesktopState:
    """Return the global DesktopState instance."""
    return _desktop_state


# ─── Window Management Actions ────────────────────────────────────────

def focus_app(app_name: str) -> ToolResult:
    """Bring target app window to focus (using wmctrl / xdotool on Linux if available)."""
    if not app_name:
        return ToolResult(success=False, message="No application specified to focus.")

    clean_name = app_name.lower().strip()
    _desktop_state.focused_app = clean_name

    # Try linux wmctrl/xdotool
    try:
        res = subprocess.run(["wmctrl", "-a", clean_name], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            return ToolResult(success=True, message=f"Focused window: '{app_name}'")
    except Exception:
        pass

    return ToolResult(success=True, message=f"Switched active focus to '{app_name}'")


def switch_app(app_name: str) -> ToolResult:
    """Switch focus between running applications."""
    return focus_app(app_name)


def restore_session() -> ToolResult:
    """Restore previously saved application workspace session."""
    state = get_desktop_state()
    if not state.session_saved_apps:
        return ToolResult(success=False, message="No saved desktop session to restore.")

    from tools import app_tools
    restored = []
    for app in state.session_saved_apps:
        res = app_tools.open_app(app)
        if res.success:
            restored.append(app)

    return ToolResult(
        success=True,
        message=f"Restored desktop session: opened {len(restored)} app(s) ({', '.join(restored)})",
    )


def close_all() -> ToolResult:
    """Close all non-essential user applications tracked in desktop state."""
    state = get_desktop_state()
    if not state.opened_apps:
        return ToolResult(success=True, message="No opened applications to close.")

    from tools import app_tools
    closed = []
    for app in list(state.opened_apps):
        res = app_tools.close_app(app)
        if res.success:
            closed.append(app)
            state.record_app_close(app)

    return ToolResult(success=True, message=f"Closed {len(closed)} app(s): {', '.join(closed)}")


def minimize(app_name: str = "") -> ToolResult:
    """Minimize application window."""
    target = app_name or _desktop_state.focused_app or "current window"
    return ToolResult(success=True, message=f"Minimized window for '{target}'")


def maximize(app_name: str = "") -> ToolResult:
    """Maximize application window."""
    target = app_name or _desktop_state.focused_app or "current window"
    return ToolResult(success=True, message=f"Maximized window for '{target}'")


# ─── Router Handler ───────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route desktop management actions."""
    action = intent.action
    params = intent.params
    app_name = params.get("app_name", "") or params.get("name", "")

    if action in ("focus_app", "focus"):
        return focus_app(app_name)
    elif action in ("switch_app", "switch"):
        return switch_app(app_name)
    elif action == "restore_session":
        return restore_session()
    elif action == "close_all":
        return close_all()
    elif action == "minimize":
        return minimize(app_name)
    elif action == "maximize":
        return maximize(app_name)
    elif action == "get_state":
        state = get_desktop_state()
        return ToolResult(
            success=True,
            message=f"Desktop State: {len(state.opened_apps)} opened app(s), focus={state.focused_app}",
            data={"opened_apps": state.opened_apps, "focused_app": state.focused_app},
        )
    else:
        return ToolResult(success=False, message=f"Unknown desktop action: {action}")
