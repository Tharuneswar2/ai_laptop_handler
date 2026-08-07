"""
tools/app_tools.py — Application management (open, close, list).

Uses configurable app-name → command mappings from config.py.
Supports Windows and Linux, with safe subprocess usage (shell=False).
"""

import logging
import os
import subprocess
from collections.abc import Sequence


from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


DISPLAY_NAMES = {
    "vs code": "VS Code",
    "vscode": "VS Code",
    "visual studio code": "VS Code",
    "chrome": "Chrome",
    "google chrome": "Chrome",
    "edge": "Microsoft Edge",
    "microsoft edge": "Microsoft Edge",
    "ms edge": "Microsoft Edge",
    "file explorer": "File Explorer",
    "explorer": "File Explorer",
    "files": "File Explorer",
    "windows explorer": "File Explorer",
    "file manager": "File Explorer",
    "microsoft store": "Microsoft Store",
    "store": "Microsoft Store",
    "windows store": "Microsoft Store",
    "notepad": "Notepad",
    "text editor": "Notepad",
    "calculator": "Calculator",
    "calc": "Calculator",
    "paint": "Paint",
    "mspaint": "Paint",
    "command prompt": "Command Prompt",
    "cmd": "Command Prompt",
    "powershell": "PowerShell",
    "task manager": "Task Manager",
    "taskmgr": "Task Manager",
    "settings": "Settings",
    "windows settings": "Settings",
    "control panel": "Control Panel",
    "spotify": "Spotify",
    "discord": "Discord",
    "vlc": "VLC",
    "vlc media player": "VLC",
    "word": "Word",
    "microsoft word": "Word",
    "ms word": "Word",
    "excel": "Excel",
    "microsoft excel": "Excel",
    "ms excel": "Excel",
    "powerpoint": "PowerPoint",
    "microsoft powerpoint": "PowerPoint",
    "ms powerpoint": "PowerPoint",
    "ppt": "PowerPoint",
    "photoshop": "Photoshop",
    "intellij": "IntelliJ",
    "android studio": "Android Studio",
    "blender": "Blender",
    "obs": "OBS",
}


def format_app_display_name(app_name: str) -> str:
    """Format an app name into a clean, human-readable display name."""
    name_lower = app_name.lower().strip()
    if name_lower in DISPLAY_NAMES:
        return DISPLAY_NAMES[name_lower]
    return app_name.title()


def _get_app_command(app_name: str) -> str | Sequence[str] | None:
    """Look up the executable command for an app name."""
    import config

    name = app_name.lower().strip()
    return config.APP_MAPPINGS.get(name)


def _try_launch_windows_unknown_app(app_name: str) -> bool:
    """Attempt to launch an unknown application on Windows using App Paths and Start Menu."""
    if os.name != "nt":
        return False

    clean = app_name.lower().replace(" ", "").strip()
    if not clean:
        return False

    # 1. Try direct startfile
    for name_variant in (app_name, app_name + ".exe", clean, clean + ".exe"):
        try:
            os.startfile(name_variant)
            logger.info("Opened unknown app via startfile(%s)", name_variant)
            return True
        except OSError:
            pass

    # 2. Check Windows Registry App Paths
    try:
        import winreg
        for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                    for i in range(num_subkeys):
                        subkey_name = winreg.EnumKey(key, i)
                        sub_lower = subkey_name.lower().replace(" ", "")
                        if clean in sub_lower:
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                exe_path, _ = winreg.QueryValueEx(subkey, "")
                                if exe_path and os.path.exists(exe_path):
                                    os.startfile(exe_path)
                                    logger.info("Opened unknown app via Registry App Paths: %s", exe_path)
                                    return True
            except Exception:
                pass
    except ImportError:
        pass

    # 3. Check Start Menu Programs shortcuts
    start_menu_dirs = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs"),
    ]
    for sm_dir in start_menu_dirs:
        if not os.path.exists(sm_dir):
            continue
        for root, _, files in os.walk(sm_dir):
            for file in files:
                file_lower = file.lower()
                if file_lower.endswith((".lnk", ".exe")) and clean in file_lower.replace(" ", ""):
                    shortcut_path = os.path.join(root, file)
                    try:
                        os.startfile(shortcut_path)
                        logger.info("Opened unknown app via Start Menu shortcut: %s", shortcut_path)
                        return True
                    except OSError:
                        pass

    return False


def open_app(app_name: str) -> ToolResult:
    """
    Open an application by its friendly name.

    Args:
        app_name: Friendly name like "chrome", "vs code", "terminal".
    """
    import shutil

    display_name = format_app_display_name(app_name)
    command = _get_app_command(app_name)

    if not app_name.strip():
        return ToolResult(success=False, message="Please say which app to open.")

    if not command:
        # App not in explicit mappings — attempt Windows application launcher discovery
        if os.name == "nt" and _try_launch_windows_unknown_app(app_name):
            return ToolResult(success=True, message=f"Opening {display_name}.")
        # Fall back to trying direct command
        command = app_name.lower().strip()
        logger.info("App '%s' not in mappings, trying direct command: '%s'", app_name, command)

    try:
        # 1. On Windows, try os.startfile for string commands (e.g. ms-settings:, msedge.exe, notepad.exe)
        if os.name == "nt" and isinstance(command, str):
            try:
                os.startfile(command)
                logger.info("Opened app via startfile: %s", command)
                return ToolResult(success=True, message=f"Opening {display_name}.")
            except OSError:
                pass

        # 2. Resolve executable and launch via Popen
        args = [command] if isinstance(command, str) else list(command)
        exe = args[0]
        resolved = shutil.which(exe) or exe
        args[0] = resolved
        use_shell = os.name == "nt" and isinstance(resolved, str) and resolved.lower().endswith((".cmd", ".bat"))

        subprocess.Popen(
            args,
            shell=use_shell,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=os.name != "nt",
        )
        logger.info("Opened app: %s (command: %s, resolved: %s)", app_name, command, resolved)
        return ToolResult(success=True, message=f"Opening {display_name}.")
    except (FileNotFoundError, OSError):
        if os.name == "nt" and _try_launch_windows_unknown_app(app_name):
            return ToolResult(success=True, message=f"Opening {display_name}.")
        return ToolResult(success=False, message=f"App '{display_name}' not found. Is it installed?")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open {display_name}: {e}")


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
        command_name = command[0] if not isinstance(command, str) else command
        proc_name = command_name.split("/")[-1]
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
    try:
        result = subprocess.run(
            ["ps", "-eo", "comm"], capture_output=True, text=True, timeout=5,
        )
        running_procs = set(result.stdout.strip().split("\n"))
        running = []

        for app_name, command in config.APP_MAPPINGS.items():
            command_name = command[0] if not isinstance(command, str) else command
            proc_name = command_name.split("/")[-1]
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
