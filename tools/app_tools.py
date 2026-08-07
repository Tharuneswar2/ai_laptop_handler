"""Application management with full laptop access: Win32, UWP/Store, Start Menu, and registry."""

import csv
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)

try:
    import winreg
except ImportError:
    winreg = None


# ─── Helpers ───────────────────────────────────────────────────────────

def _process_name(command: str) -> str:
    base = command.split(" ")[0].split("/")[-1]
    return base if os.name != "nt" or base.lower().endswith(".exe") else f"{base}.exe"


def _normalize_app_name(app_name: str) -> str:
    import config

    name = (app_name or "").lower().strip()
    for prefix in ("the ", "my "):
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    if name in config.APP_MAPPINGS:
        return name
    for alias in sorted(config.APP_MAPPINGS, key=len, reverse=True):
        if alias in name or name in alias:
            return alias
    return name


def _normalize_key(value: str) -> str:
    """Normalize a name for fuzzy matching: lowercase, strip spaces/separators."""
    return re.sub(r"[\s\-_\.]+", "", (value or "").lower())


def _start_menu_links() -> list:
    """Return all Start Menu .lnk shortcut paths for the current user and all users."""
    if os.name != "nt":
        return []
    dirs = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    links = []
    for base in dirs:
        if base.exists():
            links.extend(p for p in base.rglob("*.lnk") if p.is_file())
    return links


def _registry_uninstall_entries() -> list:
    """Return (DisplayName, InstallLocation, DisplayIcon) from the Windows Uninstall registry keys."""
    if winreg is None or os.name != "nt":
        return []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    entries = []
    for root, key_path in roots:
        try:
            with winreg.OpenKey(root, key_path) as uninstall_key:
                for i in range(0, winreg.QueryInfoKey(uninstall_key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(uninstall_key, i)
                        with winreg.OpenKey(uninstall_key, subkey_name) as subkey:
                            def _get(name):
                                try:
                                    value, _ = winreg.QueryValueEx(subkey, name)
                                    return value if isinstance(value, str) else ""
                                except OSError:
                                    return ""
                            entries.append((_get("DisplayName"), _get("InstallLocation"), _get("DisplayIcon")))
                    except OSError:
                        continue
        except OSError:
            continue
    return [e for e in entries if e[0]]


def _resolve_shortcut_target(lnk_path: str) -> str:
    """Resolve a Windows .lnk shortcut to its target executable path via WScript.Shell COM."""
    if os.name != "nt" or not lnk_path.lower().endswith(".lnk"):
        return lnk_path
    try:
        ps = (
            f'$sh = New-Object -ComObject WScript.Shell; '
            f'$lnk = $sh.CreateShortcut("{lnk_path}"); '
            f'Write-Output $lnk.TargetPath'
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace",
        )
        target = r.stdout.strip()
        if target and (Path(target).exists() or target.lower().endswith(".exe")):
            return target
    except Exception:
        pass
    return lnk_path


def _find_installed_app(app_name: str):
    """
    Locate an installed application on Windows by fuzzy name matching.

    Checks Start Menu shortcuts first, then the registry Uninstall keys.
    Returns a path that can be launched (shortcut / executable), or None.
    """
    if os.name != "nt":
        return None

    key = _normalize_key(app_name)
    if not key:
        return None

    # 1. Exact stem match on Start Menu shortcuts ("antigravity" -> "Antigravity.lnk")
    for link in _start_menu_links():
        if _normalize_key(link.stem) == key:
            return str(link)

    # 2. Fuzzy substring match on Start Menu shortcuts
    for link in _start_menu_links():
        stem = _normalize_key(link.stem)
        if key in stem or stem in key:
            return str(link)

    # 3. Registry Uninstall keys -- match DisplayName or InstallLocation
    for display_name, install_location, display_icon in _registry_uninstall_entries():
        if _normalize_key(display_name) == key or key in _normalize_key(display_name):
            candidates = []
            if display_icon and display_icon.lower().endswith(".exe"):
                candidates.append(display_icon)
            if install_location:
                for exe in (f"{display_name}.exe",):
                    p = Path(install_location) / exe
                    if p.exists():
                        candidates.append(str(p))
                        break
            if candidates:
                return candidates[0]

    return None


def _find_uwp_app(app_name: str) -> str:
    """
    Find a UWP / Windows Store app by name via PowerShell Get-StartApps.

    Returns the shell:AppsFolder AppID string (e.g. "Microsoft.WindowsCamera_8wekyb3d8bbwe!App"),
    or empty string if not found. Prefers exact name matches over substring matches.
    """
    if os.name != "nt":
        return ""
    try:
        key = _normalize_key(app_name)
        ps = 'Get-StartApps | ForEach-Object { "$($_.Name)|$($_.AppID)" }'
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace",
        )
        exact_match = ""
        fuzzy_match = ""
        for line in r.stdout.splitlines():
            if "|" not in line:
                continue
            name_part, appid = line.split("|", 1)
            name_key = _normalize_key(name_part.strip())
            if name_key == key:
                exact_match = appid.strip()
                break
            if not fuzzy_match and (key in name_key or name_key in key):
                fuzzy_match = appid.strip()
        return exact_match or fuzzy_match
    except Exception:
        pass
    return ""


def _resolve_app_exe(name: str) -> str:
    """
    Resolve the actual .exe process name for any app, whether in APP_MAPPINGS,
    discovered via Start Menu, or a UWP Store app.
    """
    import config

    command = config.APP_MAPPINGS.get(name, "")
    if command and command != "start_menu":
        return _process_name(command)

    installed = _find_installed_app(name)
    if installed:
        if installed.lower().endswith(".lnk"):
            target = _resolve_shortcut_target(installed)
            return Path(target).name if target else _process_name(name)
        return Path(installed).name

    uwp_id = _find_uwp_app(name)
    if uwp_id:
        pkg = uwp_id.split("!")[0] if "!" in uwp_id else uwp_id
        # UWP package names often contain dots; the process is usually the last segment
        parts = pkg.split(".")
        return parts[-1] + ".exe" if len(parts) > 1 else pkg + ".exe"

    return _process_name(name)


# ─── Core Actions ──────────────────────────────────────────────────────

def open_app(app_name: str) -> ToolResult:
    """Open an application: APP_MAPPINGS -> Start Menu -> UWP Store apps."""
    name = _normalize_app_name(app_name)
    if not name:
        return ToolResult(False, "I didn't catch which app to open. Please repeat the app name.")

    import config
    command = config.APP_MAPPINGS.get(name, name)
    logger.info("Opening app '%s' (command: '%s')", name, command)
    if command == "start_menu":
        if os.name != "nt":
            return ToolResult(False, "Start Menu toggle is only supported on Windows.")
        subprocess.Popen(["powershell", "-NoProfile", "-Command",
                          "$wshell = New-Object -ComObject WScript.Shell; $wshell.SendKeys('^{ESC}')"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ToolResult(True, "Opened Start Menu.", {"app": name})

    try:
        if os.name == "nt":
            # 1. Try APP_MAPPINGS or PATH-known command
            if name in config.APP_MAPPINGS or ":" in command or shutil.which(command):
                subprocess.Popen(["cmd", "/c", "start", "", command],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                exe = _process_name(command)
                return ToolResult(True, f"Opened {name}.", {"app": name, "command": command, "exe": exe})

            # 2. Try Start Menu / registry
            installed_path = _find_installed_app(name)
            if installed_path:
                logger.info("Resolved '%s' to installed app at %s", name, installed_path)
                # Resolve .lnk shortcut to its real .exe target
                launch_path = _resolve_shortcut_target(installed_path) if installed_path.lower().endswith(".lnk") else installed_path
                exe_name = Path(launch_path).name
                os.startfile(installed_path)
                return ToolResult(True, f"Opened {name}.", {"app": name, "path": installed_path, "exe": exe_name, "resolved": launch_path})

            # 3. Try UWP / Windows Store apps
            uwp_id = _find_uwp_app(name)
            if uwp_id:
                logger.info("Resolved '%s' to UWP app: %s", name, uwp_id)
                shell_cmd = f"explorer.exe shell:AppsFolder\\{uwp_id}"
                subprocess.Popen(["cmd", "/c", shell_cmd],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                pkg = uwp_id.split("!")[0] if "!" in uwp_id else uwp_id
                return ToolResult(True, f"Opened {name}.", {"app": name, "uwp_id": uwp_id, "exe": pkg})

            return ToolResult(False, f"App '{app_name}' not found. Is it installed?", {"app": name})

        # Non-Windows: direct exec
        subprocess.Popen([command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return ToolResult(True, f"Opened {name}.", {"app": name, "command": command})
    except FileNotFoundError:
        return ToolResult(False, f"App '{app_name}' not found. Is it installed?", {"app": name})
    except Exception as exc:
        return ToolResult(False, f"Failed to open {name}: {exc}", {"app": name})


def close_app(app_name: str) -> ToolResult:
    """Close an application by resolving its actual process name from any source."""
    import config

    name = _normalize_app_name(app_name)
    resolved_exe = _resolve_app_exe(name)

    try:
        if os.name == "nt":
            # Check if the resolved process is running
            listing = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {resolved_exe}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3,
            )
            rows = list(csv.reader(line for line in listing.stdout.splitlines() if line.strip()))
            if not any(row and row[0].lower() == resolved_exe.lower() for row in rows):
                # Fallback: search by window title for apps whose process name we can't predict
                fallback = _find_process_by_title(name)
                if fallback:
                    resolved_exe = fallback
                else:
                    return ToolResult(False, f"{name} is not running (expected process {resolved_exe}).",
                                      {"app": name, "process": resolved_exe, "reason": "not_running"})

            result = subprocess.run(
                ["taskkill", "/IM", resolved_exe, "/F", "/T"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=config.APP_CLOSE_TIMEOUT,
            )
        else:
            result = subprocess.run(
                ["pkill", "-f", resolved_exe],
                capture_output=True, text=True, timeout=config.APP_CLOSE_TIMEOUT,
            )

        if result.returncode == 0:
            logger.info("Closed app '%s' using process '%s'", name, resolved_exe)
            return ToolResult(True, f"Closed {name}.", {"app": name, "process": resolved_exe})

        reason = (result.stderr or result.stdout or "process manager returned an error").strip()
        return ToolResult(False, f"Could not close {name}: {reason}", {"app": name, "process": resolved_exe})

    except subprocess.TimeoutExpired:
        logger.warning("Timed out closing %s after %ss", name, config.APP_CLOSE_TIMEOUT)
        return ToolResult(False, f"Closing {name} timed out after {config.APP_CLOSE_TIMEOUT}s.",
                          {"app": name, "process": resolved_exe, "reason": "timeout"})
    except Exception as exc:
        return ToolResult(False, f"Failed to close {name}: {exc}", {"app": name, "process": resolved_exe})


def _find_process_by_title(app_name: str):
    """
    Last-resort fallback: search running processes by window title.
    Returns the process image name if found, else None.
    """
    if os.name != "nt":
        return None
    try:
        ps = (
            f'Get-Process | Where-Object {{$_.MainWindowTitle -like "*{app_name}*"}} '
            f'| Select-Object -First 1 -ExpandProperty ProcessName'
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace",
        )
        name = r.stdout.strip()
        if name and not name.startswith("Get-Process"):
            return name if name.lower().endswith(".exe") else f"{name}.exe"
    except Exception:
        pass
    return None


def list_running_apps() -> ToolResult:
    """List apps currently running whose processes are in APP_MAPPINGS."""
    import config
    try:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
            running_procs = {row[0].lower() for row in csv.reader(result.stdout.splitlines()) if row}
        else:
            result = subprocess.run(["ps", "-eo", "comm"], capture_output=True, text=True, timeout=5)
            running_procs = {line.lower() for line in result.stdout.splitlines()}
        running = []
        for app_name, command in config.APP_MAPPINGS.items():
            if _process_name(command).lower() in running_procs and app_name not in running:
                running.append(app_name)
        return ToolResult(True, f"Running apps: {', '.join(running) if running else 'No known apps detected.'}",
                          {"apps": running})
    except Exception as exc:
        return ToolResult(False, f"Failed to list apps: {exc}")


def list_installed_apps() -> ToolResult:
    """List applications installed on this PC (registry + Start Menu + UWP Store apps)."""
    if os.name != "nt":
        return ToolResult(False, "Listing installed apps is only supported on Windows.")

    installed = set()

    # Registry Uninstall keys (Win32 desktop apps)
    for display_name, install_location, display_icon in _registry_uninstall_entries():
        name = display_name.strip()
        if name:
            installed.add(name)

    # Start Menu shortcuts
    for link in _start_menu_links():
        installed.add(link.stem)

    # UWP / Windows Store apps via Get-StartApps
    try:
        ps = 'Get-StartApps | ForEach-Object { $_.Name }'
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace",
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("Get-"):
                installed.add(line)
    except Exception:
        pass

    names = sorted(installed, key=str.lower)
    if not names:
        return ToolResult(False, "Could not detect any installed applications.")

    lines = [f"  {n}" for n in names]
    return ToolResult(
        True,
        f"Installed applications ({len(names)}):\n" + "\n".join(lines),
        {"installed": names},
    )


def open_folder(path: str = "", name: str = "") -> ToolResult:
    target = Path(path).expanduser().resolve() if path else Path.home()
    if not target.exists():
        return ToolResult(False, f"Folder not found: {path}")
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", str(target)])
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return ToolResult(True, f"Opened '{name or target.name}' in File Explorer ({target}).", {"path": str(target)})
    except Exception as exc:
        return ToolResult(False, f"Failed to open folder: {exc}")


def open_terminal(path: str = "", name: str = "") -> ToolResult:
    target = Path(path).expanduser().resolve() if path else Path.home()
    try:
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", "start", "cmd"], cwd=str(target))
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", "-a", "Terminal", str(target)])
        else:
            subprocess.Popen(["x-terminal-emulator"], cwd=str(target))
        return ToolResult(True, f"Opened terminal in '{target}'.", {"path": str(target)})
    except Exception as exc:
        return ToolResult(False, f"Failed to open terminal: {exc}")


# ─── Router Handler ────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    action, params = intent.action, intent.params
    name = params.get("name", "") or params.get("app_name", "")
    if action == "open":
        return open_app(name)
    if action == "close":
        return close_app(name)
    if action in ("list", "list_running", "list_running_apps"):
        return list_running_apps()
    if action in ("list_installed", "list_installed_apps", "installed"):
        return list_installed_apps()
    if action in ("open_folder", "open_explorer"):
        return open_folder(params.get("path", ""), name)
    if action in ("open_terminal", "terminal"):
        return open_terminal(params.get("path", ""), name)
    return ToolResult(False, f"Unknown app action: {action}")
