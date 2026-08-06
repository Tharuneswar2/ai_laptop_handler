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
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "rule_based")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL","phi3:mini")      # small model for Ollama
OLLAMA_URL = "http://localhost:11434"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# ─── Memory ───────────────────────────────────────────────────────────
MEMORY_MAX_ITEMS = 20           # keep last N interactions in context

# ─── Platform Detection ───────────────────────────────────────────────
import platform
IS_WINDOWS = platform.system() == "Windows"

# ─── App Mappings ─────────────────────────────────────────────────────
# Map friendly names → executable commands (platform-specific).
if IS_WINDOWS:
    # Windows: launched via `cmd /c start <name>` (name resolved from PATH
    # or the App Paths registry). "explorer" opens File Explorer.
    APP_MAPPINGS = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "brave": "brave",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "terminal": "cmd",
        "command prompt": "cmd",
        "powershell": "powershell",
        "file explorer": "explorer",
        "file manager": "explorer",
        "files": "explorer",
        "explorer": "explorer",
        "this pc": "explorer",
        "calculator": "calc",
        "settings": "ms-settings:",
        "notepad": "notepad",
        "text editor": "notepad",
        "paint": "mspaint",
        "word": "winword",
        "excel": "excel",
        "powerpoint": "powerpnt",
        "outlook": "outlook",
        "spotify": "spotify",
        "discord": "discord",
        "slack": "slack",
        "vlc": "vlc",
        "gimp": "gimp",
        "obs": "obs",
        "libreoffice": "libreoffice",
        "thunderbird": "thunderbird",
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
        "file explorer": "nautilus",
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

# ─── Terminal Safety ──────────────────────────────────────────────────
if IS_WINDOWS:
    ALLOWED_TERMINAL_COMMANDS = {
        "dir", "pwd", "whoami", "ver", "date", "time", "hostname",
        "echo", "cls", "cd", "where python", "where git",
        "python --version", "pip --version",
        "git status",
    }
else:
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
