"""
tools/system_tools.py — System information and controls.

Supports: battery, RAM, CPU, disk, volume, brightness, screenshot, lock screen.
Uses psutil for cross-platform metrics and Linux-specific commands for controls.
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def battery_status() -> ToolResult:
    """Get battery percentage and charging status."""
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is None:
            return ToolResult(success=True, message="No battery detected (desktop PC?).")
        percent = battery.percent
        plugged = "charging" if battery.power_plugged else "on battery"
        time_left = ""
        secsleft = battery.secsleft
        if secsleft is not None and 0 < secsleft < 7 * 24 * 3600 and not battery.power_plugged:
            h, m = secsleft // 3600, (secsleft % 3600) // 60
            time_left = f", ~{h}h {m}m remaining"
        return ToolResult(success=True, message=f"Battery: {percent}% ({plugged}{time_left}).",
                          data={"percent": percent, "plugged": battery.power_plugged})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get battery info: {e}")


def ram_usage() -> ToolResult:
    """Get RAM usage."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        return ToolResult(success=True,
                          message=f"RAM: {used_gb:.1f} GB used / {total_gb:.1f} GB total ({mem.percent}% used).",
                          data={"used_gb": round(used_gb, 1), "total_gb": round(total_gb, 1), "percent": mem.percent})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get RAM info: {e}")


def cpu_usage() -> ToolResult:
    """Get CPU usage percentage."""
    try:
        import psutil
        percent = psutil.cpu_percent(interval=1)
        count = psutil.cpu_count()
        return ToolResult(success=True, message=f"CPU: {percent}% usage ({count} cores).",
                          data={"percent": percent, "cores": count})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get CPU info: {e}")


def disk_usage() -> ToolResult:
    """Get disk usage for the root partition."""
    try:
        import psutil
        root = os.environ.get("SystemDrive", "C:\\") + "\\" if os.name == "nt" else "/"
        disk = psutil.disk_usage(root)
        used_gb = disk.used / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)
        free_gb = disk.free / (1024 ** 3)
        return ToolResult(success=True,
                          message=f"Disk: {used_gb:.1f} GB used / {total_gb:.1f} GB total ({free_gb:.1f} GB free).",
                          data={"used_gb": round(used_gb, 1), "total_gb": round(total_gb, 1), "free_gb": round(free_gb, 1)})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get disk info: {e}")


def _set_volume_windows(level: int) -> bool:
    """Set the default playback volume via Windows shell volume up/down keys."""
    import ctypes
    from ctypes import wintypes

    WAVE_VOLUME_MAX = 0xFFFF
    target = int(level / 100.0 * WAVE_VOLUME_MAX)
    return ctypes.windll.winmm.waveOutSetVolume(0, (target << 16) | target) == 0


def set_volume(level: int) -> ToolResult:
    """Set system volume (0-100)."""
    level = max(0, min(100, level))
    if os.name == "nt":
        try:
            if _set_volume_windows(level):
                return ToolResult(success=True, message=f"Volume set to {level}%.")
        except Exception as e:
            logger.warning("Windows volume control failed: %s", e)
        return ToolResult(success=False, message="Volume control not available on this system.")
    try:
        subprocess.run(["amixer", "set", "Master", f"{level}%"], capture_output=True, timeout=5)
        return ToolResult(success=True, message=f"Volume set to {level}%.")
    except FileNotFoundError:
        return ToolResult(success=False, message="Volume control not available (amixer not found).")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to set volume: {e}")


def set_brightness(level: int) -> ToolResult:
    """Set screen brightness (0-100) using brightnessctl or xrandr."""
    level = max(0, min(100, level))
    if os.name == "nt":
        return ToolResult(success=False, message="Brightness control not available on this system.")
    try:
        subprocess.run(["brightnessctl", "set", f"{level}%"], capture_output=True, timeout=5)
        return ToolResult(success=True, message=f"Brightness set to {level}%.")
    except FileNotFoundError:
        pass
    try:
        result = subprocess.run(["xrandr", "--listmonitors"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            monitor = lines[1].split()[-1]
            subprocess.run(["xrandr", "--output", monitor, "--brightness", str(level / 100.0)],
                           capture_output=True, timeout=5)
            return ToolResult(success=True, message=f"Brightness set to {level}% (via xrandr).")
    except FileNotFoundError:
        pass
    return ToolResult(success=False, message="Brightness control not available.")


def take_screenshot() -> ToolResult:
    """Take a screenshot and save to ~/Pictures."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path.home() / "Pictures" / f"screenshot_{ts}.png"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        try:
            from PIL import ImageGrab
            ImageGrab.grab().save(str(filepath))
            return ToolResult(success=True, message=f"Screenshot saved to {filepath}.")
        except Exception as e:
            return ToolResult(success=False, message=f"Screenshot failed: {e}")

    for cmd in [["scrot", str(filepath)], ["gnome-screenshot", "-f", str(filepath)]]:
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
            if filepath.exists():
                return ToolResult(success=True, message=f"Screenshot saved to {filepath}.")
        except FileNotFoundError:
            continue
    return ToolResult(success=False, message="Screenshot failed. Install scrot: sudo apt install scrot")


def lock_screen() -> ToolResult:
    """Lock the screen (Windows or Linux)."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                capture_output=True, timeout=5,
            )
            return ToolResult(success=True, message="Screen locked.")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to lock screen: {e}")

    for cmd in [["loginctl", "lock-session"], ["gnome-screensaver-command", "-l"], ["xdg-screensaver", "lock"]]:
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
            return ToolResult(success=True, message="Screen locked.")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return ToolResult(success=False, message="Could not lock screen.")


def brightness_adjust(delta: int) -> ToolResult:
    """Increase or decrease brightness by delta percentage."""
    if os.name == "nt":
        return ToolResult(success=False, message="Brightness adjustment not supported on Windows.")
    try:
        sign = "+" if delta > 0 else "-"
        subprocess.run(["brightnessctl", "set", f"{abs(delta)}%{sign}"], capture_output=True, timeout=5)
        return ToolResult(success=True, message=f"Adjusted brightness ({sign}{abs(delta)}%).")
    except Exception:
        return set_brightness(75 if delta > 0 else 30)


def diagnose_performance() -> ToolResult:
    """Check high RAM/CPU usage and return diagnosis."""
    ram_res = ram_usage()
    cpu_res = cpu_usage()
    return ToolResult(
        success=True,
        message=f"Performance Diagnosis:\n• {ram_res.message}\n• {cpu_res.message}",
        data={"ram": ram_res.data, "cpu": cpu_res.data}
    )


def handle(intent: Intent) -> ToolResult:
    """Route system tool actions."""
    action = intent.action
    params = intent.params
    actions = {
        "battery": lambda: battery_status(),
        "ram": lambda: ram_usage(),
        "cpu": lambda: cpu_usage(),
        "disk": lambda: disk_usage(),
        "volume": lambda: set_volume(params.get("level", 50)),
        "brightness": lambda: set_brightness(params.get("level", 50)),
        "brightness_up": lambda: brightness_adjust(15),
        "brightness_down": lambda: brightness_adjust(-15),
        "diagnose_performance": lambda: diagnose_performance(),
        "screenshot": lambda: take_screenshot(),
        "lock_screen": lambda: lock_screen(),
    }
    handler = actions.get(action)
    if handler:
        return handler()
    return ToolResult(success=False, message=f"Unknown system action: {action}")
