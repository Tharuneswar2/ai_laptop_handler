"""
config.py — Centralized configuration for AI Laptop Voice Handler.

All tunable settings live here so modules stay clean and changes
are easy to make in one place.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
HISTORY_DB = DATA_DIR / "history.db"
WEB_UI_DIR = PROJECT_ROOT / "ui" / "web"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ─── STT Provider ─────────────────────────────────────────────────────
# "browser"        — Web Speech API via browser (default, no GPU needed)
# "whisper_local"  — faster-whisper running locally (needs CUDA or CPU)
# "cloud_whisper"  — future: cloud-based Whisper API
STT_PROVIDER = os.getenv("STT_PROVIDER", "browser")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en-US")  # BCP-47 language tag

# ─── Wake Word ────────────────────────────────────────────────────────
WAKE_WORDS = ["hey nova", "hey assistant"]
WAKE_LISTEN_DURATION = 2        # seconds per wake-word check window
WAKE_WORD_ENABLED = True        # set False to skip wake word entirely

# ─── Voice Settings (whisper_local mode only) ─────────────────────────
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = "int8"   # int8 for CPU, float16 for GPU
LISTEN_DURATION = 5             # default recording length (seconds)
LISTEN_MAX_DURATION = 15        # max recording for silence-based stop
SILENCE_THRESHOLD = 500         # amplitude threshold for silence
SAMPLE_RATE = 16000             # Whisper expects 16 kHz

# ─── TTS Settings ─────────────────────────────────────────────────────
TTS_ENGINE = "pyttsx3"          # pyttsx3 | piper (future)
TTS_RATE = 175                  # words per minute
TTS_VOLUME = 0.9                # 0.0 to 1.0

# ─── AI Brain ─────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_MODEL = "phi3:mini"      # small model for Ollama
OLLAMA_URL = "http://localhost:11434"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# ─── Memory ───────────────────────────────────────────────────────────
MEMORY_MAX_ITEMS = 20           # keep last N interactions in context

# ─── App Mappings (Linux) ─────────────────────────────────────────────
# Map friendly names → executable commands
if os.name == "nt":
    # Each VS Code or Explorer command explicitly asks for a fresh window.
    APP_MAPPINGS = {
        "file explorer": ["explorer.exe", "/n,"],
        "explorer": ["explorer.exe", "/n,"],
        "windows explorer": ["explorer.exe", "/n,"],
        "file manager": ["explorer.exe", "/n,"],
        "files": ["explorer.exe", "/n,"],
        "vscode": ["code", "--new-window"],
        "vs code": ["code", "--new-window"],
        "visual studio code": ["code", "--new-window"],
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "command prompt": "cmd.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "settings": "ms-settings:",
        "windows settings": "ms-settings:",
        "control panel": "control.exe",
        "microsoft store": "ms-windows-store:",
        "store": "ms-windows-store:",
        "windows store": "ms-windows-store:",
        "notepad": "notepad.exe",
        "text editor": "notepad.exe",
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "ms edge": "msedge.exe",
        "firefox": "firefox.exe",
        "spotify": "spotify.exe",
        "discord": "Discord.exe",
        "slack": "slack.exe",
        "vlc": "vlc.exe",
        "vlc media player": "vlc.exe",
        "word": "winword.exe",
        "microsoft word": "winword.exe",
        "ms word": "winword.exe",
        "excel": "excel.exe",
        "microsoft excel": "excel.exe",
        "ms excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
        "microsoft powerpoint": "powerpnt.exe",
        "ms powerpoint": "powerpnt.exe",
        "ppt": "powerpnt.exe",
    }
else:
    APP_MAPPINGS = {
    "chrome": "google-chrome",
    "google chrome": "google-chrome",
    "firefox": "firefox",
    "brave": "brave-browser",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "terminal": "gnome-terminal",
    "file manager": "nautilus",
    "files": "nautilus",
    "nautilus": "nautilus",
    "calculator": "gnome-calculator",
    "settings": "gnome-control-center",
    "text editor": "gedit",
    "gedit": "gedit",
    "spotify": "spotify",
    "discord": "discord",
    "slack": "slack",
    "obs": "obs",
    "vlc": "vlc",
    "gimp": "gimp",
    "libreoffice": "libreoffice",
    "thunderbird": "thunderbird",
}

# Browser voice mode follows the Nova wake-word flow by default. Set this to
# false in .env only when using explicit tap-to-talk command activation.
BROWSER_REQUIRE_WAKE_WORD = os.getenv("BROWSER_REQUIRE_WAKE_WORD", "true").lower() in {"1", "true", "yes"}

# ─── Terminal Safety ──────────────────────────────────────────────────
ALLOWED_TERMINAL_COMMANDS = {
    "ls", "pwd", "du", "df", "whoami", "uname",
    "git status", "python --version", "python3 --version",
    "pip --version", "pip3 --version",
    "date", "uptime", "free", "hostname",
    "cat /etc/os-release", "lsb_release -a",
}

BLOCKED_PATTERNS = [
    "rm ", "rm\t", "rmdir", "sudo", "mkfs", "dd ",
    "chmod", "chown", "> /dev", ":(){ ", "fork",
    "wget ", "curl ", "shutdown", "reboot", "poweroff",
    "kill ", "killall", "pkill",
]

TERMINAL_TIMEOUT = 10  # seconds

# ─── Logging ──────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ─── API Server ───────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ─── WebSocket ────────────────────────────────────────────────────────
WS_MAX_TEXT_LENGTH = 500        # max characters per WebSocket message
