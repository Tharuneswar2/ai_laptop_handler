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
AI_STORAGE_DIR = PROJECT_ROOT / "ai_storage"
PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT") or (Path.home() / "Projects")).expanduser().resolve()

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
AI_STORAGE_DIR.mkdir(exist_ok=True)

# ─── STT Provider ─────────────────────────────────────────────────────
# "browser" — Web Speech API via browser (default)
# "aws"     — Amazon Transcribe Streaming (when --aws flag is used)
STT_PROVIDER = os.getenv("STT_PROVIDER", "browser")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en-US")  # BCP-47 language tag

# ─── AWS Transcribe Settings ──────────────────────────────────────────
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_LANGUAGE_CODE = os.getenv("AWS_LANGUAGE_CODE", "en-US")
AWS_SAMPLE_RATE = int(os.getenv("AWS_SAMPLE_RATE", "16000"))
AWS_VAD_ENABLED = os.getenv("AWS_VAD_ENABLED", "true").lower() in ("1", "true", "yes")
AWS_WAKE_WORD_ENABLED = os.getenv("AWS_WAKE_WORD_ENABLED", "true").lower() in ("1", "true", "yes")

# ─── Wake Word ────────────────────────────────────────────────────────
WAKE_WORDS = ["hey nova", "hey assistant", "innova", "hey innova"]
WAKE_WORD_ENABLED = True        # set False to skip wake word entirely

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
        # Browsers
        "chrome": "chrome",
        "google chrome": "chrome",
        "firefox": "firefox",
        "brave": "brave",
        "edge": "msedge",
        "microsoft edge": "msedge",
        # Editors / IDEs
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "notepad": "notepad",
        "text editor": "notepad",
        # Terminals
        "terminal": "cmd",
        "command prompt": "cmd",
        "powershell": "powershell",
        # File management
        "file explorer": "explorer",
        "file manager": "explorer",
        "files": "explorer",
        "explorer": "explorer",
        "this pc": "explorer",
        # Windows built-ins
        "start menu": "start_menu",
        "start": "start_menu",
        "calculator": "calc",
        "settings": "ms-settings:",
        "paint": "mspaint",
        "snipping tool": "ms-screenclip:",
        "task manager": "taskmgr",
        "character map": "charmap",
        "magnifier": "magnify",
        "on screen keyboard": "osk",
        # Office
        "word": "winword",
        "excel": "excel",
        "powerpoint": "powerpnt",
        "outlook": "outlook",
        "onenote": "onenote",
        # Communication
        "spotify": "spotify",
        "discord": "discord",
        "slack": "slack",
        "teams": "ms-teams:",
        "zoom": "zoom",
        "whatsapp": "whatsapp:",
        # Media
        "vlc": "vlc",
        "obs": "obs",
        # Creative
        "gimp": "gimp",
        "libreoffice": "libreoffice",
        # Mail
        "mail": "ms-mail:",
        "windows mail": "ms-mail:",
        # Store
        "store": "ms-windows-store:",
        "microsoft store": "ms-windows-store:",
        # Windows Terminal (if installed)
        "windows terminal": "wt",
        "wt": "wt",
        # Misc
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
        "mkdir", "md",
        "type",
        "tree",
        "tasklist",
        "systeminfo",
        "ipconfig",
    }
else:
    ALLOWED_TERMINAL_COMMANDS = {
        "ls", "pwd", "du", "df", "whoami", "uname",
        "git status", "python --version", "python3 --version",
        "pip --version", "pip3 --version",
        "date", "uptime", "free", "hostname",
        "cat /etc/os-release", "lsb_release -a",
        "mkdir", "touch", "tree", "ps", "top",
    }

BLOCKED_PATTERNS = [
    "rm ", "rm\t", "rmdir", "sudo", "mkfs", "dd ",
    "chmod", "chown", "> /dev", ":(){ ", "fork",
    "wget ", "curl ", "shutdown", "reboot", "poweroff",
    "kill ", "killall", "pkill",
]

TERMINAL_TIMEOUT = 10  # seconds
APP_CLOSE_TIMEOUT = 5  # seconds
SLOW_OPERATION_MS = 10_000

# ─── Logging ──────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ─── API Server ───────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ─── WebSocket ────────────────────────────────────────────────────────
WS_MAX_TEXT_LENGTH = 500        # max characters per WebSocket message
