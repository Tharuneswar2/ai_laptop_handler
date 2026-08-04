"""
tools/app_tools.py — Application management (open, close, list).

Uses configurable app-name → command mappings from config.py.
Linux-first, with safe subprocess usage (shell=False).
"""

import logging
import subprocess

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def _get_app_command(app_name: str) -> str | None:
    """Look up the executable command for an app name."""
    import config

    name = app_name.lower().strip()
    return config.APP_MAPPINGS.get(name)


def open_app(app_name: str) -> ToolResult:
    """
    Open an application by its friendly name.

    Args:
        app_name: Friendly name like "chrome", "vs code", "terminal".
    """
    command = _get_app_command(app_name)

    if not command:
        # Try running the name directly as a command
        command = app_name.lower().strip()
        logger.info("App '%s' not in mappings, trying direct command: '%s'", app_name, command)

    try:
        subprocess.Popen(
            [command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("Opened app: %s (command: %s)", app_name, command)
        return ToolResult(success=True, message=f"Opened {app_name}.")
    except FileNotFoundError:
        return ToolResult(success=False, message=f"App '{app_name}' not found. Is it installed?")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open {app_name}: {e}")


def close_app(app_name: str) -> ToolResult:
    """
    Close an application (requires confirmation).

    Uses `pkill` to send SIGTERM to the process.
    """
    command = _get_app_command(app_name) or app_name.lower().strip()

    # Confirmation
    try:
        response = input(f"⚠️  Close {app_name}? (yes/no): ").strip().lower()
        if response not in ("yes", "y"):
            return ToolResult(success=False, message=f"Close {app_name} cancelled.")
    except (EOFError, KeyboardInterrupt):
        return ToolResult(success=False, message="Close cancelled.")

    try:
        # Get the process name (basename of the command)
        proc_name = command.split("/")[-1]
        result = subprocess.run(
            ["pkill", "-f", proc_name],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            logger.info("Closed app: %s", app_name)
            return ToolResult(success=True, message=f"Closed {app_name}.")
        else:
            return ToolResult(success=False, message=f"{app_name} is not running or could not be closed.")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to close {app_name}: {e}")


def list_running_apps() -> ToolResult:
    """List common running desktop applications."""
    import config

    running = []
    try:
        result = subprocess.run(
            ["ps", "-eo", "comm"], capture_output=True, text=True, timeout=5,
        )
        running_procs = set(result.stdout.strip().split("\n"))

        for app_name, command in config.APP_MAPPINGS.items():
            proc_name = command.split("/")[-1]
            if proc_name in running_procs:
                if app_name not in running:
                    running.append(app_name)

        if running:
            app_list = ", ".join(running)
            return ToolResult(
                success=True,
                message=f"Running apps: {app_list}",
                data={"apps": running},
            )
        else:
            return ToolResult(success=True, message="No known apps detected as running.")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to list apps: {e}")


# ─── Handler ──────────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route app tool actions."""
    action = intent.action
    params = intent.params

    if action == "open":
        return open_app(params.get("app_name", ""))
    elif action == "close":
        return close_app(params.get("app_name", ""))
    elif action == "list":
        return list_running_apps()
    else:
        return ToolResult(success=False, message=f"Unknown app action: {action}")
