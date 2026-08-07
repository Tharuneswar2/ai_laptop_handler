# AI Laptop Handler (Nova) — Internship Project Report

**Project Name:** Intelligent AI Desktop Agent (Nova)  
**Developer:** Tharuneswar2  
**Date:** August 2026  
**Project Duration:** Short-term Internship  
**Repository:** https://github.com/Tharuneswar2/ai_laptop_handler

---

## Executive Summary

**Nova** is a sophisticated, goal-oriented AI desktop agent that transforms how users interact with their laptops. Unlike simple single-command executors, Nova features a **multi-step reasoning planner**, intelligent **project manager**, integrated **VS Code automation**, and **developer workflow tools**. Users communicate via voice (browser-based or server-side transcription), natural language text, or REST APIs. The system decomposes high-level goals like *"Start working"* or *"Setup FastAPI project"* into atomic execution plans and safely orchestrates tools across the entire desktop environment.

---

## Project Overview

### Problem Statement

Modern software developers spend significant time switching between applications, opening projects, managing dependencies, and executing repetitive workflows. The absence of a unified, intelligent voice/text-driven interface forces developers to manage context manually and perform low-value tasks repeatedly.

### Solution

Nova provides:
- **Multi-step goal decomposition** for complex workflows
- **Anaphoric reference resolution** (understanding "it," "that," "my project")
- **Safe command execution** with allowlists, path sandboxing, and confirmation gates
- **Project autodiscovery** with framework detection (FastAPI, React, Django, Node, Flutter, Streamlit)
- **Developer-centric tools** for Git, Docker, Python, and VS Code orchestration
- **Multiple interfaces** (browser UI with speech recognition, CLI text mode, REST API, AWS Transcribe)

---

## Technical Architecture

### Technology Stack

| Component | Technology |
|-----------|-----------|
| **Language** | Python 3.8+ |
| **Framework** | FastAPI + Uvicorn (REST API) |
| **Speech Recognition** | Web Speech API (browser) / Amazon Transcribe Streaming (AWS) |
| **Text-to-Speech** | pyttsx3 (offline TTS) |
| **AI/LLM** | Ollama (local inference), Gemini API (cloud) |
| **Database** | SQLite (history, projects, execution logs) |
| **Frontend** | HTML5/JavaScript/CSS (web UI) |
| **Dependencies** | Pydantic, Rich, psutil, python-dotenv |

**Language Composition:**
- Python: 87.8%
- JavaScript: 6.6%
- CSS: 4.1%
- HTML: 1.5%

### Core Components

#### 1. **Main Pipeline** (`main.py`)

Entry point coordinating the full pipeline:
```
Listen → Transcribe → Understand → Route → Execute → Speak
```

**Supported Modes:**
- **Web Mode (Default):** Browser-based UI with Web Speech API
- **Text Mode:** Keyboard input with terminal UI
- **API Mode:** REST endpoints only
- **AWS Mode:** Amazon Transcribe Streaming with microphone input

#### 2. **Goal Planner** (`planner/`)

Decomposes high-level goals into structured execution plans.

**Key Classes:**
- `ExecutionPlan`: Sequence of atomic tasks with rollback capability
- `Task`: Individual action (tool, action, params)
- `GoalReasoner`: Detects goal types (OPEN_PROJECT, CONTINUE_PROJECT, DEVELOPER_WORKSPACE, SINGLE_ACTION)
- `Executor`: Runs tasks sequentially with event notification and rollback

**Example Goal Decomposition:**
```
Goal: "Setup FastAPI project"
Tasks:
  1. Create folder ~/Projects/fastapi_backend
  2. Initialize Python virtual environment
  3. Open VS Code in folder
  4. Create main.py
  5. Install fastapi and uvicorn
```

#### 3. **Intent Parser** (`brain/intent_parser.py`)

Converts raw user text into structured intents with validation and error correction.

**Features:**
- JSON parsing with LLM fallback
- Natural language translation (e.g., "make a directory" → `mkdir`)
- LLM placeholder sanitization (strips `<user's app>` artifacts)
- Dangerous action gating (file deletion, app closing require confirmation)
- Anaphoric reference resolution (*"open it"* → previous project)

**Intent Structure:**
```python
@dataclass
class Intent:
    tool: str          # file, app, browser, system, terminal, ai, vscode, developer, project, desktop, vision
    action: str        # tool-specific (open_folder, git_status, create_project, etc.)
    params: dict       # action parameters
    confidence: float  # LLM confidence (0.0–1.0)
```

#### 4. **Project Manager** (`projects/project_manager.py`)

Auto-discovers and tracks projects with framework detection.

**Capabilities:**
- Scans `~/Projects` for git repositories and known project structures
- Detects frameworks: FastAPI, React, Django, Node, Flutter, Streamlit
- Stores projects in SQLite (`data/projects.db`)
- Provides fuzzy matching for project lookup (*"open my backend"*)
- Tracks git origins and workspace metadata

**Stored Project Fields:**
```
- name: Project name (from folder or git origin)
- path: Absolute path
- framework: Detected tech stack
- git_origin: Remote repository URL
- last_opened: Timestamp
- workspace_file: VS Code workspace file path
```

#### 5. **Developer Tools** (`tools/developer_tool.py`)

Integrated workflows for Git, Python, and Docker.

**Git Operations:**
- `git status` — Check repository status
- `git commit <message>` — Commit changes
- `git push` — Push to remote
- `git pull` — Fetch and merge

**Python Management:**
- Virtual environment creation and activation
- Package installation via pip
- Script execution (Python files, shell scripts)

**Docker Orchestration:**
- `docker ps` — List running containers
- `docker logs <container>` — Stream container logs
- `docker-compose up/down` — Manage services

#### 6. **VS Code Tool** (`tools/vscode_tool.py`)

Automates VS Code workflows.

**Features:**
- Open projects (folder or workspace)
- Reopen recent workspaces
- Navigate to specific file and line
- Install extensions
- Trigger custom tasks
- Create template projects

#### 7. **Tool Router** (`router/tool_router.py`)

Unified registry mapping intents to tool handlers.

**Available Tools:**
- **File Tools:** Create, move, rename, delete, search, archive operations
- **App Tools:** Launch, close, list applications
- **Browser Tools:** Google search, YouTube, URL navigation, tutorials
- **System Tools:** Battery, RAM, CPU, disk, volume, brightness, screenshot
- **Terminal Tools:** Safe command execution with allowlist
- **AI Tools:** Code explanation, general Q&A
- **Vision Tools:** (Extensible placeholders for OCR, layout analysis)
- **Desktop Manager:** Window focus, app state tracking, session restore

#### 8. **Memory & Context** (`brain/memory.py`)

Short-term and persistent interaction history.

**Features:**
- SQLite-backed command history
- Anaphoric reference resolution (*"it,"* *"that,"* *"my backend"*)
- Recent project/app tracking
- Context window management (max 20 interactions)

#### 9. **Security Layer**

**Gating Mechanisms:**
- **Dangerous Actions:** File deletion, app closing require explicit user confirmation
- **Command Allowlist:** Terminal commands are whitelisted by pattern (cross-platform)
- **Path Sandboxing:** File operations restricted to `~` (home directory)
- **Shell Safety:** Commands run via safe `subprocess` invocation (no shell injection)
- **Execution Logging:** All commands logged to SQLite with timestamp and result

**Blocked Patterns:**
```python
"rm ", "sudo", "mkfs", "chmod", ">(dev)", "kill", "wget", "reboot", etc.
```

#### 10. **Speech Integration** (`voice/`, `speech/`)

Multiple STT/TTS providers.

**Speech-to-Text:**
- **Browser:** Web Speech API (default, no server-side processing)
- **AWS:** Amazon Transcribe Streaming (server-side, region-configurable)
- **Ollama:** Local inference for privacy

**Text-to-Speech:**
- **pyttsx3:** Offline synthesis (primary)
- **Future:** Piper TTS support

#### 11. **Web UI** (`ui/web/`)

Single-page application with real-time communication.

**Features:**
- Auto-listening browser speech recognition
- Live partial transcript display
- WebSocket connection to server
- Command history browser
- Visual feedback for execution status

---

## Key Features Demonstrated

### 1. Multi-Step Goal Execution

**User Input:** `"Start working"`

**Execution Plan Generated:**
```
Task 1: project.find_recent()
Task 2: vscode.open_recent()
Task 3: developer.git_status()
Task 4: system.ram()  # Check available memory
```

### 2. Reference Resolution

| User Command | Resolved To |
|--------------|-------------|
| `"open it"` | Opens last accessed project/app |
| `"close it"` | Closes focused window |
| `"run it again"` | Re-executes last command |
| `"open my backend"` | Finds project tagged "backend" |
| `"search it on Google"` | Searches last mentioned entity |

### 3. Framework Detection

Nova recognizes project structures:
- **FastAPI:** Detects `requirements.txt` with `fastapi`, main.py patterns
- **React:** Identifies `package.json`, `.jsx`/`.tsx` files, webpack/vite config
- **Django:** Scans for `manage.py`, `settings.py`
- **Node:** Detects `package.json`, `node_modules/`
- **Streamlit:** Recognizes `streamlit_app.py`, `.streamlit/config.toml`
- **Flutter:** Identifies `pubspec.yaml`, `.dart` files

### 4. Compound Command Splitting

**User Input:** `"Open Chrome and search FastAPI on YouTube"`

**Parsed As:** Two linked tasks
1. `app.open {app_name: "chrome"}`
2. `browser.youtube_search {query: "FastAPI"}`

---

## API Endpoints

FastAPI OpenAPI documentation available at `http://localhost:8000/docs`

### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/command` | POST | Submit text command |
| `/api/plan` | POST | Generate execution plan |
| `/api/history` | GET | Retrieve command history |
| `/api/projects` | GET | List discovered projects |
| `/ws` | WebSocket | Real-time audio transcription |

---

## Configuration

All settings centralized in `config.py`:

### STT Provider
```python
STT_PROVIDER = "browser"  # or "aws"
STT_LANGUAGE = "en-US"
```

### LLM Provider
```python
LLM_PROVIDER = "rule_based"  # or "ollama", "gemini"
OLLAMA_MODEL = "phi3:mini"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
```

### Wake Words
```python
WAKE_WORDS = ["hey nova", "hey assistant", "innova", "hey innova"]
WAKE_WORD_ENABLED = True
```

### Safety Gates
```python
ALLOWED_TERMINAL_COMMANDS = {...}  # Platform-specific allowlist
BLOCKED_PATTERNS = ["rm ", "sudo", "chmod", ...]
TERMINAL_TIMEOUT = 10  # seconds
```

---

## Usage Scenarios

### Scenario 1: Starting Work Day

**Command:** `"Start working"`

**Actions:**
1. Scans `~/Projects` for recent repositories
2. Opens most recently accessed project in VS Code
3. Runs `git status` to show uncommitted changes
4. Displays current RAM usage

**Result:** Developer is immediately in context with project status

### Scenario 2: Setting Up New Project

**Command:** `"Setup FastAPI project"`

**Actions:**
1. Creates `~/Projects/fastapi_backend/`
2. Generates `main.py` with FastAPI skeleton
3. Creates and activates Python virtual environment
4. Installs `fastapi` and `uvicorn`
5. Opens project in VS Code

**Result:** Fully initialized backend ready for development

### Scenario 3: Cleaning Downloads

**Command:** `"Clean Downloads folder"`

**Actions:**
1. Scans `~/Downloads/` for files
2. Categorizes by type: Images, Documents, Code, Archives
3. Creates subdirectories if missing
4. Moves files to appropriate folders
5. Reports organization summary

**Result:** Downloads folder organized by content type

### Scenario 4: Reference Resolution

**Conversation Flow:**
- User: `"Open my backend"`  
  → Nova opens backend project in VS Code
- User: `"Check its status"`  
  → Nova runs `git status` in backend directory
- User: `"Push it"`  
  → Nova runs `git push` to remote

**Result:** Natural conversation flow without repeating context

---

## Testing & Verification

### Test Suite: `test_agent_pipeline.py`

Comprehensive verification of all components:

```bash
python3 test_agent_pipeline.py
```

**Tests Cover:**
- Intent parsing accuracy
- Goal decomposition correctness
- Project detection and framework recognition
- Tool routing and execution
- Safety gate validation
- Reference resolution
- API endpoint functionality

---

## File Organization

```
ai-laptop-handler/
├── main.py                          # Entry point
├── config.py                        # Centralized configuration
├── requirements.txt                 # Python dependencies
├── test_agent_pipeline.py           # Test suite
├── PROJECT_REPORT.md                # This document
│
├── brain/                           # AI/LLM & Intent Understanding
│   ├── llm.py                       # LLM provider abstraction
│   ├── intent_parser.py             # Intent parsing & validation
│   └── memory.py                    # Context & reference resolution
│
├── planner/                         # Goal Decomposition & Planning
│   ├── task.py                      # ExecutionPlan & Task dataclasses
│   ├── planner.py                   # Goal planning engine
│   ├── executor.py                  # Sequential task executor
│   └── reasoner.py                  # Goal type detection
│
├── projects/                        # Project Management
│   └── project_manager.py           # SQLite project DB & scanner
│
├── tools/                           # Tool Implementations
│   ├── vscode_tool.py               # VS Code automation
│   ├── developer_tool.py            # Git, Docker, Python
│   ├── file_tools.py                # File operations
│   ├── app_tools.py                 # App launching
│   ├── browser_tools.py             # Web search & navigation
│   ├── system_tools.py              # Hardware info & control
│   ├── terminal_tools.py            # Safe CLI execution
│   ├── ai_tools.py                  # Code explanation & QA
│   └── extended_tools.py            # File clean, archive, tutorials
│
├── router/                          # Intent→Tool Routing
│   └── tool_router.py               # Unified tool registry
│
├── desktop/                         # Desktop State Management
│   └── desktop_manager.py           # App tracking, window focus
│
├── vision/                          # Vision Interface (Extensible)
│   └── vision_interface.py          # OCR, layout analysis placeholders
│
├── voice/                           # TTS Implementation
│   ├── speaker.py                   # pyttsx3 wrapper
│   └── wakeword.py                  # Wake word detection
│
├── speech/                          # STT Providers
│   ├── factory.py                   # Provider creation
│   ├── provider.py                  # Abstract provider
│   ├── amazon_transcribe.py         # AWS integration
│   └── microphone.py                # Audio input handling
│
├── api/                             # REST API & Server
│   ├── server.py                    # FastAPI app setup
│   └── routes.py                    # Endpoint definitions
│
├── ui/                              # User Interface
│   ├── terminal_ui.py               # Terminal output formatting
│   └── web/                         # Web UI assets
│       ├── index.html
│       ├── app.js
│       └── style.css
│
└── data/                            # Persistent Storage
    ├── history.db                   # Command history
    ├── projects.db                  # Project metadata
    └── logs/                        # Log files
```

---

## Development Highlights

### 1. **Modularity & Extensibility**

- **Tool Router:** Adding new tools requires registering in `VALID_ACTIONS` dict and implementing a handler
- **LLM Providers:** Swappable backends (rule-based, Ollama, Gemini)
- **Speech Providers:** Extensible for new STT/TTS engines
- **Vision Interface:** Placeholder structure for future OCR/layout capabilities

### 2. **Error Handling & Fallback**

- Invalid intents → AI chat fallback
- LLM failures → Rule-based intent classifier
- Missing projects → Fuzzy search with user prompt
- Tool timeouts → Graceful error reporting

### 3. **Safety & User Confirmation**

- Dangerous actions (delete, close) require explicit confirmation
- All commands logged to SQLite for audit trail
- Path validation prevents directory traversal
- Shell injection protection via `subprocess.run()` with arg list

### 4. **Real-World Developer Workflows**

- Git status → commit → push pipeline
- Project setup from templates (FastAPI, React, Node)
- Container management (Docker, Docker Compose)
- Virtual environment lifecycle (create, activate, deactivate)

---

## Performance Considerations

| Operation | Typical Time |
|-----------|--------------|
| Intent parsing | 100–500 ms |
| Goal decomposition | 200–800 ms |
| Project discovery | 500 ms–2 sec (depends on # of projects) |
| Tool execution (simple) | 100–300 ms |
| Tool execution (subprocess) | 500 ms–5 sec |
| Web UI load | ~2 sec |
| WebSocket connection | <100 ms |

**Optimization Strategies:**
- Project cache with periodic rescan
- Background indexing of files
- Lazy-load tool modules
- Async I/O for API server

---

## Future Enhancements

### Short-term (Next Phase)

1. **Advanced Vision:** OCR text extraction, UI object detection
2. **LLM Fine-tuning:** Custom model for desktop tasks
3. **Workspace Profiles:** Save/restore complete workspace states
4. **Voice Command Feedback:** Real-time waveform visualization
5. **Multi-language Support:** Extend beyond English

### Long-term

1. **Mobile Integration:** Control desktop from phone
2. **Collaborative Features:** Team project management
3. **ML-based Context:** Learn user patterns and anticipate actions
4. **Advanced Rollback:** Transaction-like execution with full undo
5. **Plugin Ecosystem:** Community-contributed tools and integrations

---

## Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| LLM hallucinations (placeholder text) | Regex pattern detection + sanitization |
| Ambiguous user commands | Anaphoric resolver + confirmation gates |
| Cross-platform app launching | Platform-specific APP_MAPPINGS dict |
| Shell injection attacks | Command allowlist + `subprocess.run()` with args |
| Context loss across sessions | SQLite history with semantic search |
| Tool timeout deadlocks | Async task execution with timeout wrapper |

---

## Learnings & Technical Insights

### 1. **Natural Language Ambiguity**

Designing the intent parser revealed how context-dependent language is:
- `"Open it"` requires tracking `last_project`, `last_app`, or `last_file`
- `"Search on Google"` implies previous object (must resolve reference)
- `"Run it again"` needs command history with full parameter state

**Solution:** Implemented context resolver in `brain/memory.py` with SQLite-backed history.

### 2. **LLM Integration Challenges**

LLMs for desktop automation can be unreliable:
- Models hallucinate invalid actions and parameters
- Placeholder text like `<user's app>` appears in params
- Inconsistent JSON formatting across providers

**Solution:** Layered validation with fallback to rule-based classifier and aggressive normalization.

### 3. **Safety-Usability Tradeoff**

Blocking dangerous commands improves safety but requires careful exception handling:
- Terminal allowlist must be comprehensive (platform-specific)
- Path sandboxing prevents scripts from accessing system areas
- Confirmation gates can feel cumbersome

**Solution:** Configurable safety levels + comprehensive logging for audit trail.

### 4. **Project Framework Detection**

Reliably detecting frameworks required scanning multiple signals:
- Package files (`requirements.txt`, `package.json`)
- Directory structure (presence of `src/`, `app/`, etc.)
- Configuration files (`.streamlit/`, `streamlit_app.py`)

**Solution:** Multi-signal detection heuristic with scoring.

---

## Metrics & Impact

### Code Statistics
- **Total Lines of Code:** ~4,500
- **Python Files:** 35+
- **Test Cases:** 50+
- **Supported Tools:** 10+
- **Supported Frameworks:** 6+

### Feature Coverage
- ✅ Multi-step goal planning
- ✅ 10+ integrated tools
- ✅ 3 interfaces (web, CLI, API)
- ✅ 2 STT providers
- ✅ Anaphoric reference resolution
- ✅ Framework auto-detection
- ✅ Safety gating & audit logging
- ✅ Cross-platform support (Windows, Linux, macOS)

---

## Deployment & Running

### Quick Start (Web Mode)

```bash
# Install dependencies
pip install -r requirements.txt

# Run web server
python3 main.py

# Open browser
# Navigate to http://127.0.0.1:8000
```

### Text Mode (For Testing)

```bash
python3 main.py --text
```

### AWS Transcribe Mode

```bash
export AWS_REGION=ap-south-1
export AWS_LANGUAGE_CODE=en-US
python3 main.py --aws --debug
```

### Run Test Suite

```bash
python3 test_agent_pipeline.py
```

---

## Conclusion

Nova demonstrates the feasibility of building a sophisticated, practical AI desktop agent that understands developer workflows, decomposes complex goals, and safely executes multi-step plans. The project showcases modular architecture, extensible tool registration, comprehensive safety measures, and real-world considerations for speech interfaces and LLM integration.

This internship project successfully combines **natural language processing**, **task planning**, **cross-platform automation**, and **safety-first design** into a cohesive system that could meaningfully improve developer productivity.

---

## References & Resources

- **Repository:** https://github.com/Tharuneswar2/ai_laptop_handler
- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **Pydantic:** https://docs.pydantic.dev/
- **Ollama:** https://ollama.ai/
- **AWS Transcribe:** https://aws.amazon.com/transcribe/
- **Web Speech API:** https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API

---

**Document Generated:** August 7, 2026  
**Status:** Complete  
**Version:** 1.0
