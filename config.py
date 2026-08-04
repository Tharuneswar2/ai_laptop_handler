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

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ─── Wake Word ────────────────────────────────────────────────────────
WAKE_WORDS = ["hey nova", "hey assistant"]
WAKE_LISTEN_DURATION = 2        # seconds per wake-word check window
WAKE_WORD_ENABLED = True        # set False to skip wake word entirely

# ─── Voice Settings ───────────────────────────────────────────────────
WHISPER_MODEL = "tiny"          # tiny | base | small  (tiny ≈ 75 MB)
WHISPER_DEVICE = "cpu"          # cpu | cuda
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
LLM_PROVIDER = "rule_based"     # rule_based | ollama | gemini
OLLAMA_MODEL = "phi3:mini"      # small model for Ollama
OLLAMA_URL = "http://localhost:11434"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# ─── Memory ───────────────────────────────────────────────────────────
MEMORY_MAX_ITEMS = 20           # keep last N interactions in context

# ─── App Mappings (Linux) ─────────────────────────────────────────────
# Map friendly names → executable commands
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
API_HOST = "127.0.0.1"
API_PORT = 8000
