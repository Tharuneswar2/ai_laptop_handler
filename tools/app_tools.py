"""
tools/app_tools.py — Application management (open, close, list).

Uses configurable app-name → command mappings from config.py.
Cross-platform: `cmd /c start` on Windows, direct exec on Linux/macOS.
"""

import logging
import os
import subprocess

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def _get_app_command(app_name: str) -> str | None:
    """Look up the executable command for an app name."""
    import config

    name = app_name.lower().strip()
    return config.APP_MAPPINGS.get(name)


def _process_name(command: str) -> str:
    """Derive a process image name (exe on Windows) from a launch command."""
    base = command.split(" ")[0].split("/")[-1]
    if os.name == "nt" and not base.lower().endswith(".exe"):
        return base + ".exe"
    return base


def open_app(app_name: str) -> ToolResult:
    """
    Open an application by its friendly name.

    Args:
        app_name: Friendly name like "chrome", "vs code", "file explorer".
    """
    name = (app_name or "").lower().strip()
    if not name:
        return ToolResult(
            success=False,
            message="I didn't catch which app to open. Please repeat the app name.",
        )

    import config

    command = config.APP_MAPPINGS.get(name, name)
    logger.info("Opening app '%s' (command: '%s')", name, command)

    try:
        if os.name == "nt":
            # `start "" <name>` resolves registered apps from PATH / App Paths
            subprocess.Popen(
                ["cmd", "/c", "start", "", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        else:
            subprocess.Popen(
                [command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        logger.info("Opened app: %s", app_name)
        return ToolResult(success=True, message=f"Opened {app_name}.")
    except FileNotFoundError:
        return ToolResult(success=False, message=f"App '{app_name}' not found. Is it installed?")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open {app_name}: {e}")


def close_app(app_name: str) -> ToolResult:
    """
    Close an application (requires confirmation).

    Uses `taskkill` on Windows and `pkill` on Linux/macOS.
    """
    import config

    command = config.APP_MAPPINGS.get(app_name.lower().strip(), app_name.lower().strip())

    # Confirmation
    try:
        response = input(f"⚠️  Close {app_name}? (yes/no): ").strip().lower()
        if response not in ("yes", "y"):
            return ToolResult(success=False, message=f"Close {app_name} cancelled.")
    except (EOFError, KeyboardInterrupt):
        return ToolResult(success=False, message="Close cancelled.")

    try:
        proc_name = _process_name(command)
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/IM", proc_name, "/F"],
                capture_output=True, text=True, timeout=5,
            )
        else:
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
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5,
            )
            running_procs = {
                line.split(",")[0].strip('"').lower()
                for line in result.stdout.strip().splitlines()
                if line.strip()
            }
        else:
            result = subprocess.run(
                ["ps", "-eo", "comm"], capture_output=True, text=True, timeout=5,
            )
            running_procs = set(result.stdout.strip().split("\n"))

        for app_name, command in config.APP_MAPPINGS.items():
            proc_name = _process_name(command).lower()
            if proc_name in running_procs and app_name not in running:
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


def open_folder(path: str = "", name: str = "") -> ToolResult:
    """Open a folder in the native file explorer."""
    from pathlib import Path
    target = Path(path).expanduser().resolve() if path else Path.home()
    if not target.exists():
        return ToolResult(success=False, message=f"Folder not found: {path}")

    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", str(target)])
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return ToolResult(success=True, message=f"Opened '{name or target.name}' in File Explorer ({target}).")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open folder: {e}")


def open_terminal(path: str = "", name: str = "") -> ToolResult:
    """Open a terminal / command prompt window at the given directory path."""
    from pathlib import Path
    target = Path(path).expanduser().resolve() if path else Path.home()

    try:
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", "start", "cmd"], cwd=str(target))
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", "-a", "Terminal", str(target)])
        else:
            subprocess.Popen(["x-terminal-emulator"], cwd=str(target))
        return ToolResult(success=True, message=f"Opened terminal in '{target}'.")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open terminal: {e}")


# ─── Handler ──────────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route app tool actions."""
    action = intent.action
    params = intent.params
    name = params.get("name", "") or params.get("app_name", "")
    path = params.get("path", "")

    if action == "open":
        return open_app(name)
    elif action == "close":
        return close_app(name)
    elif action == "list":
        return list_running_apps()
    elif action in ("open_folder", "open_explorer"):
        return open_folder(path=path, name=name)
    elif action in ("open_terminal", "terminal"):
        return open_terminal(path=path, name=name)
    else:
        return ToolResult(success=False, message=f"Unknown app action: {action}")
