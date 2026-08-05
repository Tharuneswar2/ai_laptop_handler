# 🎤 AI Laptop Voice Handler (Nova)

A **modular, voice-controlled laptop assistant** that listens through your microphone, understands your intent, performs safe laptop actions, and speaks the response back in a natural voice.

Built as a clean, extensible Python project — designed for laptops with limited GPU resources (~4 GB VRAM or CPU-only).

---

## ✨ Features

| Category | Capabilities |
|----------|-------------|
| **Voice I/O** | Speech-to-text (Whisper Tiny), text-to-speech (pyttsx3), wake word detection |
| **File Ops** | Create, move, rename, delete (with confirmation), search files |
| **App Control** | Open/close apps, list running applications |
| **Browser** | Google search, YouTube search, open URLs, open GitHub |
| **System Info** | Battery, RAM, CPU, disk usage, volume, brightness, screenshot, lock screen |
| **Terminal** | Safe allowlist-only command execution (no dangerous commands) |
| **AI Chat** | Summarize text, explain code, general Q&A (with Ollama/Gemini) |
| **API** | REST API for programmatic access and future frontend integration |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│              (pipeline coordinator)                          │
│                                                             │
│  🎤 Microphone → [listener] → [intent_parser] → [router]  │
│                                       ↓                     │
│                              ┌────────┴────────┐            │
│                              │   Tool Modules  │            │
│                              │  file | app     │            │
│                              │  browser | sys  │            │
│                              │  terminal | ai  │            │
│                              └────────┬────────┘            │
│                                       ↓                     │
│                              [speaker] → 🔊 Response        │
│                                                             │
│  📊 memory.py ←── logs everything ──→ data/history.db      │
└─────────────────────────────────────────────────────────────┘
```

### Folder Structure

```
ai-laptop-handler/
├── main.py                 # Entry point (voice/text/API modes)
├── config.py               # Centralized configuration
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── voice/
│   ├── listener.py         # Microphone → text (faster-whisper)
│   ├── speaker.py          # Text → speech (pyttsx3)
│   └── wakeword.py         # Wake word detection
├── brain/
│   ├── llm.py              # LLM provider abstraction
│   ├── intent_parser.py    # Text → structured Intent
│   └── memory.py           # Conversation history (SQLite)
├── router/
│   └── tool_router.py      # Intent → correct tool handler
├── tools/
│   ├── file_tools.py       # File/folder operations
│   ├── app_tools.py        # Open/close applications
│   ├── browser_tools.py    # Web search, open URLs
│   ├── system_tools.py     # Battery, RAM, CPU, disk, etc.
│   ├── terminal_tools.py   # Safe terminal commands
│   └── ai_tools.py         # Summarize, explain, chat
├── ui/
│   └── terminal_ui.py      # Rich terminal interface
├── api/
│   └── server.py           # FastAPI REST server (+ pet observer hook)
├── pet/                    # Desktop pet engine (Codex-compatible packs)
│   ├── integration.py      # pet + web STT bridge (main.py --pet)
│   ├── assets/pets/        # Pet packs (bundled + fetched from GitHub)
│   └── tools/fetch_pets.py # Download community packs
└── data/
    ├── history.db           # Command history (auto-created)
    └── logs/                # Log files
```

---

## 🚀 Installation

### Prerequisites

- **Python 3.10+**
- **Linux** (primary target, most features work on macOS/Windows too)
- **Microphone** (for voice mode)
- **Speakers** (for text-to-speech)

### Setup

```bash
# 1. Clone or navigate to the project
cd ai-laptop-handler

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Copy and configure environment variables
cp .env.example .env

# 5. (Optional) Install system tools for full functionality
sudo apt install scrot amixer brightnessctl  # screenshot, volume, brightness
```

> **Note:** The Whisper Tiny model (~75 MB) will download automatically on the first run.

---

## 🎮 How to Run

### Text Mode (recommended for first run)

No microphone needed — type commands directly:

```bash
python main.py --text
```

### Voice Mode (full experience)

Listen for wake word "Hey Nova", then speak your command:

```bash
python main.py
```

### Voice Mode (no wake word)

Start listening immediately without a wake word:

```bash
python main.py --no-wake
```

### API Server

Start the REST API for programmatic access:

```bash
python main.py --api
# Server runs on http://127.0.0.1:8000
# Docs at http://127.0.0.1:8000/docs
```

### Pet Mode (desktop pet + web STT) 🐾

Show an animated desktop pet on screen while the browser-based STT runs
in the background. The pet reacts to your commands in real time —
listening → thinking → working → happy/error — with speech bubbles:

```bash
# Start with the default pet
python main.py --pet

# Start with a specific pet pack
python main.py --pet cat
python main.py --pet hu-tao

# List installed pet packs
python main.py --list-pets

# Download community pets from awesome-codex-pet (GitHub)
python main.py --fetch-pets
# ...or a single pack
python main.py --fetch-pets hu-tao
```

Then open `http://127.0.0.1:8000` in Chrome/Edge and speak — "Hey Nova,
open Chrome" — the pet listens, thinks and celebrates right on your desktop.

**Pets from GitHub, automatically available:**
`python main.py --fetch-pets` downloads the whole
[awesome-codex-pet](https://github.com/legeling/awesome-codex-pet)
`pets/` collection into `pet/assets/pets/`. No code changes needed —
the engine discovers packs on every launch. You can also point the engine
at your own clone or any folder full of packs:

```bash
export PET_PACKS_DIR=/path/to/awesome-codex-pet/pets
python main.py --pet
```

---

## 🗣️ Example Voice Commands

| Command | What happens |
|---------|-------------|
| "Hey Nova, open Chrome" | Opens Google Chrome |
| "Hey Nova, open VS Code" | Opens Visual Studio Code |
| "Hey Nova, create a folder called projects" | Creates `~/projects` |
| "Hey Nova, search FastAPI tutorial on YouTube" | Searches YouTube |
| "Hey Nova, how much disk space is left?" | Shows disk usage stats |
| "Hey Nova, check battery" | Shows battery percentage |
| "Hey Nova, take a screenshot" | Captures screen to ~/Pictures |
| "Hey Nova, list running apps" | Shows open applications |
| "Hey Nova, lock the screen" | Locks the screen |
| "Hey Nova, set volume to 50" | Sets volume to 50% |

---

## 🧠 AI Brain Configuration

The intent parser uses a **rule-based engine** by default (fully offline). For smarter AI features:

### Option 1: Ollama (local LLM, recommended)

```bash
# Install Ollama: https://ollama.com
ollama pull phi3:mini
# Edit .env: LLM_PROVIDER=ollama
```

### Option 2: Google Gemini (cloud API)

```bash
# Get a key: https://aistudio.google.com
# Edit .env:
#   LLM_PROVIDER=gemini
#   GEMINI_API_KEY=your_key_here
```

---

## 🔒 Safety Design

This project takes safety seriously:

| Protection | Details |
|-----------|---------|
| **No unrestricted shell** | Terminal uses a strict command allowlist |
| **No silent deletion** | Delete operations require explicit confirmation |
| **Path sandboxing** | File operations restricted to home directory |
| **No dangerous commands** | `rm`, `sudo`, `chmod`, pipes, redirects — all blocked |
| **Subprocess safety** | All commands use `shell=False` |
| **Action logging** | Every command is logged to `data/history.db` |

### Allowed Terminal Commands

```
ls, pwd, du, df, whoami, uname, date, uptime, free,
hostname, git status, python --version, pip --version
```

---

## 🧩 Extending the Project

### Adding a new tool

1. Create `tools/my_tool.py` with a `handle(intent: Intent) -> ToolResult` function
2. Add the tool name to `VALID_ACTIONS` in `brain/intent_parser.py`
3. Register it in `router/tool_router.py`'s `_load_handlers()`
4. Add matching patterns in `brain/llm.py`'s `RuleBasedProvider`

### Adding a new app mapping

Edit `config.py` → `APP_MAPPINGS`:

```python
APP_MAPPINGS = {
    "my_app": "my-app-command",
    ...
}
```

### Swapping the TTS engine

Replace the implementation in `voice/speaker.py`. The interface (`speak(text)`) stays the same.

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/status` | Health check |
| `POST` | `/command` | Execute a text command |
| `GET` | `/history` | Get command history |

### Example API call

```bash
curl -X POST http://127.0.0.1:8000/command \
  -H "Content-Type: application/json" \
  -d '{"text": "check battery"}'
```

---

## 🔮 Future Improvements

- [ ] Piper TTS for more natural voice
- [ ] OpenWakeWord for better wake word detection
- [ ] Web frontend dashboard
- [ ] Plugin system for community tools
- [ ] Multi-language support
- [ ] Context-aware follow-up commands
- [ ] Scheduled tasks / reminders
- [ ] Clipboard integration
- [ ] Music player control

---

## 📝 License

MIT License — free for personal and educational use.

---

Built with ❤️ as an internship-ready AI project.
