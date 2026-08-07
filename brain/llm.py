"""
brain/llm.py — LLM abstraction layer.

Provides a unified interface for two distinct tasks:
  - Intent extraction: turn a user command into a structured JSON intent.
  - Free-form text generation: chat, summaries, code explanations.

Backends:
  - RuleBasedProvider: keyword/regex matching (default, fully offline)
  - OllamaProvider:    local Ollama server (optional)
  - GeminiProvider:    Google Gemini API (optional, requires API key)

Usage:
    provider = get_provider()
    intent_json = provider.generate("open chrome")             # structured intent
    answer = provider.generate_text("hi", CHAT_SYSTEM_PROMPT)  # free-form text

Intent extraction uses Pydantic structured output (Ollama `format=<json schema>`)
so the model is constrained to return valid, schema-checked JSON.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

try:
    import ollama
except ImportError:
    ollama = None

logger = logging.getLogger(__name__)


# ─── Structured Output Schema ─────────────────────────────────────────

class IntentResponse(BaseModel):
    """
    Pydantic schema for intent extraction.

    Passed to Ollama as `format=IntentResponse.model_json_schema()` so the
    model must emit JSON matching this structure; the result is re-validated
    with `model_validate_json` for a canonical dict.
    """
    tool: Literal["file", "app", "browser", "system", "terminal", "ai"]
    action: str = ""
    params: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# ─── Default System Prompts ───────────────────────────────────────────

CHAT_SYSTEM_PROMPT = (
    "You are Nova, a friendly desktop assistant running on the user's laptop. "
    "Answer questions concisely and helpfully in plain natural language. "
    "Never output JSON or markdown unless the user asks for it."
)

INTENT_SYSTEM_PROMPT = """You are an intent extraction engine for a voice-controlled Windows laptop assistant.
Extract the user's command into a JSON object with EXACTLY these keys:
- "tool": one of "file", "app", "browser", "system", "terminal", "ai"
- "action": the action to perform (see valid actions below)
- "params": a JSON object of parameters for the action
- "confidence": a float between 0 and 1

RULES:
1. To open, launch, or start an application, ALWAYS use tool "app", action "open",
   with params {"app_name": "<app name>"}. NEVER use "terminal" for this.
2. "open file explorer" maps to tool "app", action "open", params {"app_name": "file explorer"}.
3. Use "terminal" only for real shell commands (list files, show directory, check versions).
4. Use "browser" for web searches and opening websites.

Valid actions per tool:
- file: create_file, create_folder, move, rename, delete, search
- app: open, close, list
- browser: open_url, google_search, youtube_search, open_github
- system: battery, ram, cpu, disk, volume, brightness, screenshot, lock_screen
- terminal: run
- ai: summarize, explain_code, chat

Examples:
User: "open vs code" -> {"tool": "app", "action": "open", "params": {"app_name": "vs code"}, "confidence": 0.98}
User: "open chrome and search for weather" -> {"tool": "browser", "action": "google_search", "params": {"query": "weather"}, "confidence": 0.95}
User: "open file explorer" -> {"tool": "app", "action": "open", "params": {"app_name": "file explorer"}, "confidence": 0.98}
User: "what is my battery level" -> {"tool": "system", "action": "battery", "params": {}, "confidence": 0.98}
User: "list files" -> {"tool": "terminal", "action": "run", "params": {"command": "ls"}, "confidence": 0.95}
User: "create a folder called projects" -> {"tool": "file", "action": "create_folder", "params": {"path": "projects"}, "confidence": 0.98}
User: "take a screenshot" -> {"tool": "system", "action": "screenshot", "params": {}, "confidence": 0.98}

Respond with ONLY the JSON object. No markdown fences, no extra text."""


# ─── Base Provider ────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a structured intent JSON string for the given command."""
        ...

    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str = "") -> str:
        """Generate free-form text (chat / summarize / explain)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is ready to use."""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


# ─── Rule-Based Provider (default, fully offline) ────────────────────

class RuleBasedProvider(LLMProvider):
    """
    Maps user commands to structured intents using keyword matching.
    This is the default provider — no downloads, no API keys, no GPU.
    """

    # Patterns: list of (regex_pattern, tool, action, param_extractor)
    # ORDER MATTERS — more specific patterns must come before generic ones.
    PATTERNS = [
        # Terminal multi-command
        (r"open terminal and run (.+)", "terminal", "run", lambda m: {"command": m.group(1).strip()}),

        # 1. Browser operations
        (r"search (.+?) (?:on|in) youtube", "browser", "youtube_search", lambda m: {"query": m.group(1).strip()}),
        (r"open (.+?) (?:on|in) youtube", "browser", "youtube_search", lambda m: {"query": m.group(1).strip()}),
        (r"(?:open |go to )youtube", "browser", "youtube_search", lambda m: {"query": ""}),
        (r"(?:open |go to )github", "browser", "open_github", lambda m: {}),
        (r"(?:open |go to )google", "browser", "open_url", lambda m: {"url": "https://google.com"}),
        (r"open (.+?) documentation", "browser", "google_search", lambda m: {"query": f"{m.group(1).strip()} documentation"}),
        (r"open the first result for (.+)", "browser", "google_search", lambda m: {"query": m.group(1).strip()}),
        (r"bookmark (?:this )?page", "browser", "bookmark", lambda m: {}),
        (r"close (?:this )?tab", "browser", "close_tab", lambda m: {}),
        (r"(?:open |go to )(?:the )?(?:url |website |site )(.+)", "browser", "open_url", lambda m: {"url": m.group(1).strip()}),
        (r"(?:search for|find) (?:my |the )?(resume|notes|pdf|document)", "file", "search", lambda m: {"pattern": m.group(1).strip()}),
        (r"(?:google |web )?search (?:for )?(.+?)(?:\s+on\s+(?:google|the web))?$", "browser", "google_search", lambda m: {"query": m.group(1).strip()}),

        # 1b. Project creation
        (r"create(?:d)? (?:a |a new |new )?project (?:name )?(?:called |named )(.+)", "project", "create", lambda m: {"name": m.group(1).strip()}),
        (r"create(?:d)? (?:a |a new |new )?project (.+)", "project", "create", lambda m: {"name": m.group(1).strip()}),
        (r"make (?:a |a new |new )?project (?:name )?(?:called |named )(.+)", "project", "create", lambda m: {"name": m.group(1).strip()}),
        (r"set up a (?:new )?project (?:called |named )(.+)", "project", "create", lambda m: {"name": m.group(1).strip()}),

        # 1c. Installed applications
        (r"(?:list|show|display).*installed (?:apps|applications|software|programs)", "app", "list_installed", lambda m: {}),
        (r"(?:list|show|display).*applications installed(?: in| on| the| my| pc| computer| laptop)*", "app", "list_installed", lambda m: {}),

        # 2. File & Folder operations
        (r"create (?:a )?(?:new )?folder (?:in (.+) )?(?:called |named )?(.+)", "file", "create_folder", lambda m: {"path": m.group(2).strip()}),
        (r"make (?:a )?(?:new )?folder (?:called |named )?(.+)", "file", "create_folder", lambda m: {"path": m.group(1).strip()}),
        (r"create (?:a )?file (?:called |named )?(.+)", "file", "create_file", lambda m: {"path": m.group(1).strip()}),
        (r"make (?:a )?file (?:called |named )?(.+)", "file", "create_file", lambda m: {"path": m.group(1).strip()}),
        (r"rename (.+) to (.+)", "file", "rename", lambda m: {"source": m.group(1).strip(), "new_name": m.group(2).strip()}),
        (r"move (.+) to (.+)", "file", "move", lambda m: {"source": m.group(1).strip(), "destination": m.group(2).strip()}),
        (r"delete (?:the )?(?:file |folder )?(.+)", "file", "delete", lambda m: {"path": m.group(1).strip()}),
        (r"remove (?:the )?(?:file |folder )?(.+)", "file", "delete", lambda m: {"path": m.group(1).strip()}),
        (r"clean downloads(?: folder)?", "file", "clean_downloads", lambda m: {}),
        (r"archive (?:the )?(.+)(?: folder)?", "file", "archive", lambda m: {"path": m.group(1).strip()}),
        (r"unzip (?:the )?(.+)", "file", "unzip", lambda m: {"path": m.group(1).strip()}),
        (r"find duplicate images", "file", "find_duplicates", lambda m: {"type": "images"}),
        (r"copy (?:this )?file to (.+)", "file", "copy", lambda m: {"destination": m.group(1).strip()}),
        (r"open (?:the )?(?:newest|last|recent) pdf", "file", "open_newest_pdf", lambda m: {}),
        (r"find (?:the )?(?:newest|last|recent) pdf", "file", "find_newest_pdf", lambda m: {}),
        (r"(?:find|search for) (?:my |the )?(.+)", "file", "search", lambda m: {"pattern": m.group(1).strip()}),

        # 3. VS Code & Workspace Specific Operations
        (r"open (?:the )?recent workspace", "vscode", "open_recent", lambda m: {}),
        (r"reopen (?:the )?last workspace", "vscode", "reopen_last_workspace", lambda m: {}),

        # 4. App & Window Management Operations
        (r"close chrome", "app", "close", lambda m: {"app_name": "chrome"}),
        (r"close vs code", "app", "close", lambda m: {"app_name": "vscode"}),
        (r"close all apps", "app", "close_all", lambda m: {}),
        (r"minimize (?:the )?(?:current )?window", "desktop", "minimize", lambda m: {}),
        (r"maximize (?:the )?(?:current )?window", "desktop", "maximize", lambda m: {}),
        (r"switch to (.+)", "desktop", "focus_app", lambda m: {"app_name": m.group(1).strip()}),
        (r"focus (.+)", "desktop", "focus_app", lambda m: {"app_name": m.group(1).strip()}),
        (r"restore my session", "desktop", "restore_session", lambda m: {}),
        (r"open terminal", "app", "open_terminal", lambda m: {}),
        (r"open (?:file )?explorer", "app", "open_folder", lambda m: {}),
        (r"open (.+)", "app", "open", lambda m: {"app_name": m.group(1).strip()}),
        (r"launch (.+)", "app", "open", lambda m: {"app_name": m.group(1).strip()}),
        (r"start (.+)", "app", "open", lambda m: {"app_name": m.group(1).strip()}),
        (r"close (.+)", "app", "close", lambda m: {"app_name": m.group(1).strip()}),
        (r"(?:list|show) (?:running |open )?apps", "app", "list", lambda m: {}),
        (r"what(?:'s| is) running", "app", "list", lambda m: {}),

        # 5. System Operations
        (r"(?:show |check |get )?battery(?: (?:status|level|info))?", "system", "battery", lambda m: {}),
        (r"(?:how much )?battery", "system", "battery", lambda m: {}),
        (r"(?:show |check |get )?(?:ram|memory)(?: (?:usage|status|info))?", "system", "ram", lambda m: {}),
        (r"(?:show |check |get )?cpu(?: (?:usage|status|info))?", "system", "cpu", lambda m: {}),
        (r"(?:show |check |get )?disk(?: (?:usage|space|status|info))?", "system", "disk", lambda m: {}),
        (r"how much (?:disk )?space(?: is left)?", "system", "disk", lambda m: {}),
        (r"(?:take |capture )?(?:a )?screenshot", "system", "screenshot", lambda m: {}),
        (r"lock (?:the )?(?:screen|computer|laptop)", "system", "lock_screen", lambda m: {}),
        (r"(?:set |change )?volume (?:to )?(\d+)", "system", "volume", lambda m: {"level": int(m.group(1))}),
        (r"increase brightness", "system", "brightness_up", lambda m: {}),
        (r"decrease brightness", "system", "brightness_down", lambda m: {}),
        (r"(?:set |change )?brightness (?:to )?(\d+)", "system", "brightness", lambda m: {"level": int(m.group(1))}),
        (r"show running processes", "app", "list", lambda m: {}),
        (r"why is my laptop slow", "system", "diagnose_performance", lambda m: {}),

        # 6. Terminal & Developer Workflow Operations
        (r"open terminal and run (.+)", "terminal", "run", lambda m: {"command": m.group(1).strip()}),
        (r"run (?:the )?backend(?: server)?", "developer", "run_backend", lambda m: {}),
        (r"run git status", "developer", "git_status", lambda m: {}),
        (r"show git log", "developer", "git_log", lambda m: {}),
        (r"run (git|python|ls|pwd|df|du|whoami|uptime)", "terminal", "run", lambda m: {"command": m.group(1).strip()}),
        (r"(?:run|execute) (.+)", "terminal", "run", lambda m: {"command": m.group(1).strip()}),
        (r"install dependencies(?: for this project)?", "developer", "pip_install", lambda m: {}),
        (r"create (?:a )?virtual environment", "developer", "create_venv", lambda m: {}),
        (r"activate (?:the )?virtual environment", "developer", "activate_venv", lambda m: {}),
        (r"pull (?:the )?latest changes", "developer", "git_pull", lambda m: {}),
        (r"commit (?:the )?changes", "developer", "git_commit", lambda m: {}),
        (r"push to github", "developer", "git_push", lambda m: {}),

        # 7. AI Operations
        (r"explain (?:this )?(?:code )?(.+)?", "ai", "explain_code", lambda m: {"text": m.group(1).strip() if m.group(1) else ""}),
        (r"summarize (?:this )?(.+)?", "ai", "summarize", lambda m: {"text": m.group(1).strip() if m.group(1) else ""}),
        (r"chat with this pdf", "ai", "chat_pdf", lambda m: {}),
        (r"read (?:the )?screenshot", "vision", "read_screen", lambda m: {}),
        (r"what is on my screen", "vision", "read_screen", lambda m: {}),
        (r"extract text from (?:this )?image", "vision", "ocr", lambda m: {}),
        (r"help me understand this error", "ai", "debug_error", lambda m: {}),
        (r"suggest a fix for this bug", "ai", "debug_error", lambda m: {}),
    ]

    def generate(self, prompt: str) -> str:
        """Match user text against patterns and return structured JSON intent."""
        text = prompt.lower().strip()

        for pattern, tool, action, extractor in self.PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    params = extractor(match)
                except Exception:
                    params = {}

                intent = {
                    "tool": tool,
                    "action": action,
                    "params": params,
                    "confidence": 0.85,
                }
                logger.info("Rule matched: %s → %s.%s", text, tool, action)
                return json.dumps(intent)

        # Fallback: general chat
        intent = {
            "tool": "ai",
            "action": "chat",
            "params": {"text": prompt},
            "confidence": 0.3,
        }
        logger.info("No rule matched for: '%s', falling back to AI chat.", text)
        return json.dumps(intent)

    def generate_text(self, prompt: str, system_prompt: str = "") -> str:
        """Rule-based provider cannot produce free-form text."""
        return ""

    def is_available(self) -> bool:
        return True


# ─── Ollama Provider (optional) ──────────────────────────────────────

class OllamaProvider(LLMProvider):
    """Connect to a local Ollama server for intent extraction and chat."""

    INTENT_SYSTEM_PROMPT = INTENT_SYSTEM_PROMPT
    CHAT_SYSTEM_PROMPT = CHAT_SYSTEM_PROMPT

    def __init__(self):
        import config
        self.model = config.OLLAMA_MODEL
        self.url = config.OLLAMA_URL

    @property
    def _client(self) -> "ollama.Client":
        """Lazily build the Ollama client for the configured URL."""
        if ollama is None:
            raise RuntimeError("The 'ollama' python package is not installed.")
        return ollama.Client(host=self.url)

    def generate(self, prompt: str) -> str:
        """
        Extract a structured intent JSON string from the user command.

        Uses Pydantic structured output: the model is given the JSON schema
        for IntentResponse and the reply is validated back through it.
        """
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                format=IntentResponse.model_json_schema(),
            )
            intent = IntentResponse.model_validate_json(response.message.content)
            return intent.model_dump_json()
        except Exception as e:
            logger.error("Ollama intent request failed: %s", e)
            return json.dumps({"tool": "ai", "action": "chat", "params": {"text": prompt}, "confidence": 0.2})

    def generate_text(self, prompt: str, system_prompt: str = "") -> str:
        """Generate free-form text (chat / summarize / explain)."""
        system = system_prompt or self.CHAT_SYSTEM_PROMPT
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.message.content
        except Exception as e:
            logger.error("Ollama chat request failed: %s", e)
            return ""

    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            self._client.list()
            return True
        except Exception:
            return False


# ─── Gemini Provider (optional) ──────────────────────────────────────

class GeminiProvider(LLMProvider):
    """Use Google Gemini API for intent extraction and chat (requires API key)."""

    INTENT_SYSTEM_PROMPT = INTENT_SYSTEM_PROMPT
    CHAT_SYSTEM_PROMPT = CHAT_SYSTEM_PROMPT

    def __init__(self):
        import config
        self.api_key = config.GEMINI_API_KEY
        self.model = config.GEMINI_MODEL

    def _request(self, system_prompt: str, user_prompt: str, mime: str) -> str:
        """Send a prompt to Gemini and return the raw response text."""
        import urllib.request

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = json.dumps({
            "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser command: {user_prompt}"}]}],
            "generationConfig": {"responseMimeType": mime},
        }).encode()

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result["candidates"][0]["content"]["parts"][0]["text"]

    def generate(self, prompt: str) -> str:
        """Extract a structured intent JSON string from the user command."""
        try:
            text = self._request(self.INTENT_SYSTEM_PROMPT, prompt, "application/json")
            try:
                return IntentResponse.model_validate_json(text).model_dump_json()
            except Exception:
                return text
        except Exception as e:
            logger.error("Gemini intent request failed: %s", e)
            return json.dumps({"tool": "ai", "action": "chat", "params": {"text": prompt}, "confidence": 0.2})

    def generate_text(self, prompt: str, system_prompt: str = "") -> str:
        """Generate free-form text (chat / summarize / explain)."""
        system = system_prompt or self.CHAT_SYSTEM_PROMPT
        try:
            return self._request(system, prompt, "text/plain")
        except Exception as e:
            logger.error("Gemini chat request failed: %s", e)
            return ""

    def is_available(self) -> bool:
        return bool(self.api_key)


# ─── Provider Factory ────────────────────────────────────────────────

def get_provider() -> LLMProvider:
    """
    Auto-detect and return the best available LLM provider.

    Priority: config setting → Ollama (if running) → rule-based fallback.
    """
    import config

    provider_name = config.LLM_PROVIDER.lower()

    if provider_name == "gemini":
        provider = GeminiProvider()
        if provider.is_available():
            logger.info("Using Gemini API provider.")
            return provider
        logger.warning("Gemini API key not set, falling back.")

    if provider_name == "ollama":
        provider = OllamaProvider()
        if provider.is_available():
            logger.info("Using Ollama provider (model=%s).", provider.model)
            return provider
        logger.warning("Ollama server not available, falling back.")

    # Auto-detect: try Ollama even if not explicitly configured
    if provider_name == "auto":
        ollama = OllamaProvider()
        if ollama.is_available():
            logger.info("Auto-detected Ollama server.")
            return ollama

    # Default: rule-based (always works)
    logger.info("Using rule-based intent provider (fully offline).")
    return RuleBasedProvider()
