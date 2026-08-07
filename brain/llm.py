"""
brain/llm.py — LLM abstraction layer.

Provides a unified interface for generating text from different backends:
  - RuleBasedProvider: keyword/regex matching (default, fully offline)
  - OllamaProvider:    local Ollama server (optional)
  - GeminiProvider:    Google Gemini API (optional, requires API key)

Usage:
    provider = get_provider()
    result = provider.generate("open chrome")
"""

import json
import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# Voice aliases are normalized before routing so every supported Windows app
# has one stable app_name and never needs an LLM decision.
WINDOWS_APP_ALIASES = {
    "vs code": "vs code", "vscode": "vs code", "visual studio code": "vs code",
    "chrome": "chrome", "google chrome": "chrome",
    "edge": "edge", "microsoft edge": "edge", "ms edge": "edge",
    "file explorer": "file explorer", "explorer": "file explorer",
    "files": "file explorer", "windows explorer": "file explorer", "file manager": "file explorer",
    "microsoft store": "microsoft store", "store": "microsoft store", "windows store": "microsoft store",
    "notepad": "notepad", "text editor": "notepad",
    "calculator": "calculator", "calc": "calculator",
    "paint": "paint", "mspaint": "paint",
    "command prompt": "command prompt", "cmd": "command prompt",
    "powershell": "powershell",
    "task manager": "task manager", "taskmgr": "task manager",
    "settings": "settings", "windows settings": "settings",
    "control panel": "control panel",
    "spotify": "spotify", "discord": "discord", "vlc": "vlc", "vlc media player": "vlc",
    "word": "word", "microsoft word": "word", "ms word": "word",
    "excel": "excel", "microsoft excel": "excel", "ms excel": "excel",
    "powerpoint": "powerpoint", "microsoft powerpoint": "powerpoint", "ms powerpoint": "powerpoint", "ppt": "powerpoint",
    "photoshop": "photoshop", "intellij": "intellij", "android studio": "android studio",
    "blender": "blender", "obs": "obs",
}

_APP_NAMES_PATTERN = "|".join(re.escape(k) for k in sorted(WINDOWS_APP_ALIASES.keys(), key=len, reverse=True))


def _canonical_app_params(match: re.Match) -> dict:
    """Return the canonical app name captured by a supported-app rule."""
    try:
        raw_name = match.group(1).lower().strip()
    except (IndexError, AttributeError):
        return {}
    canonical = WINDOWS_APP_ALIASES.get(raw_name, raw_name)
    return {"app_name": canonical}


def _strip_markdown_json(raw: str) -> str:
    """Strip markdown code block wrappers from JSON string."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return cleaned


# ─── Base Provider ────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a response from the given prompt. Returns JSON string."""
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
        # Browser operations (before file/app to catch "search X on youtube" first)
        (r"search (.+?) on youtube", "browser", "youtube_search", lambda m: {"query": m.group(1).strip()}),
        (r"(?:open |go to )youtube", "browser", "youtube_search", lambda m: {"query": ""}),
        (r"(?:open |go to )github", "browser", "open_github", lambda m: {}),
        (r"(?:open |go to )(?:the )?(?:url |website |site )(.+)", "browser", "open_url", lambda m: {"url": m.group(1).strip()}),
        (r"^(?:google|web search|search)(?: for)? (.+?)(?:\s+on\s+(?:google|the web))?$", "browser", "google_search", lambda m: {"query": m.group(1).strip()}),

        # File operations
        (r"create (?:a )?folder (?:called |named )?(.+)", "file", "create_folder", lambda m: {"path": m.group(1).strip()}),
        (r"make (?:a )?folder (?:called |named )?(.+)", "file", "create_folder", lambda m: {"path": m.group(1).strip()}),
        (r"create (?:a )?file (?:called |named )?(.+)", "file", "create_file", lambda m: {"path": m.group(1).strip()}),
        (r"make (?:a )?file (?:called |named )?(.+)", "file", "create_file", lambda m: {"path": m.group(1).strip()}),
        (r"(?:delete|remove) (?:the )?(?:file |folder )?(?:called |named )?(.+)", "file", "delete", lambda m: {"path": m.group(1).strip()}),
        (r"move (?:the )?(?:file |folder )?(.+) to (.+)", "file", "move", lambda m: {"source": m.group(1).strip(), "destination": m.group(2).strip()}),
        (r"rename (?:the )?(?:file |folder )?(.+) to (.+)", "file", "rename", lambda m: {"source": m.group(1).strip(), "new_name": m.group(2).strip()}),
        (r"(?:find|look for) (?:files? |folders? )?(?:called |named )?(.+)", "file", "search", lambda m: {"pattern": m.group(1).strip()}),

        # Canonical Windows application names. Evaluated before generic app/file/terminal patterns.
        (r"(?:open|launch|start|execute) (?:the )?(" + _APP_NAMES_PATTERN + r")$", "app", "open", _canonical_app_params),
        (r"^(" + _APP_NAMES_PATTERN + r")$", "app", "open", _canonical_app_params),
        (r"(?:open|launch|start|execute) (?:the )?(.+)", "app", "open", lambda m: {"app_name": WINDOWS_APP_ALIASES.get(m.group(1).lower().strip(), m.group(1).strip())}),
        (r"(?:close|exit|quit|stop) (?:the )?(" + _APP_NAMES_PATTERN + r")$", "app", "close", _canonical_app_params),
        (r"(?:close|exit|quit|stop) (?:the )?(.+)", "app", "close", lambda m: {"app_name": m.group(1).strip()}),
        (r"(?:list|show) (?:running |open )?apps", "app", "list", lambda m: {}),
        (r"what(?:'s| is) running", "app", "list", lambda m: {}),

        # System operations
        (r"^(?:sleep|exit|goodbye|stop listening|stop|go to sleep|turn off)$", "system", "sleep", lambda m: {}),
        (r"(?:show |check |get )?battery(?: (?:status|level|info))?", "system", "battery", lambda m: {}),
        (r"(?:how much )?battery", "system", "battery", lambda m: {}),
        (r"(?:show |check |get )?(?:ram|memory)(?: (?:usage|status|info))?", "system", "ram", lambda m: {}),
        (r"(?:show |check |get )?cpu(?: (?:usage|status|info))?", "system", "cpu", lambda m: {}),
        (r"(?:show |check |get )?disk(?: (?:usage|space|status|info))?", "system", "disk", lambda m: {}),
        (r"how much (?:disk )?space", "system", "disk", lambda m: {}),
        (r"(?:take |capture )?(?:a )?screenshot", "system", "screenshot", lambda m: {}),
        (r"lock (?:the )?(?:screen|computer|laptop)", "system", "lock_screen", lambda m: {}),
        (r"(?:set |change )?volume (?:to )?(\d+)%?", "system", "volume", lambda m: {"level": int(m.group(1))}),
        (r"(?:set |change )?brightness (?:to )?(\d+)%?", "system", "brightness", lambda m: {"level": int(m.group(1))}),

        # Terminal operations
        (r"(?:run |execute )(?:command )?(.+)", "terminal", "run", lambda m: {"command": m.group(1).strip()}),
        (r"(?:show |get )?(?:current )?(?:directory|pwd)", "terminal", "run", lambda m: {"command": "pwd"}),
        (r"list files", "terminal", "run", lambda m: {"command": "ls"}),

        # AI operations
        (r"summarize (?:this )?(.+)", "ai", "summarize", lambda m: {"text": m.group(1).strip()}),
        (r"explain (?:this )?(?:code )?(.+)", "ai", "explain_code", lambda m: {"text": m.group(1).strip()}),
    ]

    def generate(self, prompt: str) -> str:
        """Match user text against patterns and return structured JSON intent."""
        text = prompt.lower().strip()
        text = re.sub(r"[.!?]+$", "", text).strip()

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
                    "confidence": 1.0,
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

    def is_available(self) -> bool:
        return True


# ─── Ollama Provider (optional) ──────────────────────────────────────

class OllamaProvider(LLMProvider):
    """Connect to a local Ollama server for intent extraction."""

    SYSTEM_PROMPT = """You extract one structured intent for a Windows voice-controlled laptop assistant.
Return ONLY one valid JSON object with exactly these keys: tool, action, params, confidence.

Allowed tools/actions:
- file: create_file, create_folder, move, rename, delete, search
- app: open, close, list
- browser: open_url, google_search, youtube_search, open_github
- system: battery, ram, cpu, disk, volume, brightness, screenshot, lock_screen, sleep
- terminal: run
- ai: summarize, explain_code, chat

Strict classification rules:
1. Opening any application (e.g. "open file explorer", "open vs code", "open chrome", "open explorer", "open files", "open calculator", "open photoshop") is ALWAYS tool="app", action="open". NEVER convert an app command into create_folder, create_file, or any file action.
2. Canonical app names: "file explorer", "vs code", "chrome", "edge", "calculator", "notepad", "command prompt", "powershell", "task manager", "settings", "control panel", "microsoft store", "spotify", "discord", "vlc", "word", "excel", "powerpoint".
3. A file action requires an explicit file verb like "create folder", "make folder", "create file", "delete", "move", "rename", "find file".
4. NEVER invent Linux paths (/home/...), Windows paths (C:\\...), user directories, filenames, or parameters not spoken by the user. If no path is given, use only the spoken name.
5. For conversational or unclear requests, return tool="ai", action="chat", params={"text":"<original command>"}.

Examples:
User: open file explorer
{"tool":"app","action":"open","params":{"app_name":"file explorer"},"confidence":1.0}
User: open explorer
{"tool":"app","action":"open","params":{"app_name":"file explorer"},"confidence":1.0}
User: open files
{"tool":"app","action":"open","params":{"app_name":"file explorer"},"confidence":1.0}
User: open vs code
{"tool":"app","action":"open","params":{"app_name":"vs code"},"confidence":1.0}
User: open chrome
{"tool":"app","action":"open","params":{"app_name":"chrome"},"confidence":1.0}
User: create folder projects
{"tool":"file","action":"create_folder","params":{"path":"projects"},"confidence":1.0}
User: create file test.txt
{"tool":"file","action":"create_file","params":{"path":"test.txt"},"confidence":1.0}
User: search python on youtube
{"tool":"browser","action":"youtube_search","params":{"query":"python"},"confidence":1.0}

Do not include Markdown, explanations, or additional keys."""

    def __init__(self):
        import config
        self.model = config.OLLAMA_MODEL
        self.url = config.OLLAMA_URL

    def generate(self, prompt: str) -> str:
        """Send prompt to Ollama and return the response."""
        import urllib.request

        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "system": self.SYSTEM_PROMPT,
            "stream": False,
            "format": "json",
        }).encode()

        req = urllib.request.Request(
            f"{self.url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                resp_text = result.get("response", "{}")
                return _strip_markdown_json(resp_text)
        except Exception as e:
            logger.error("Ollama request failed: %s", e)
            return json.dumps({"tool": "ai", "action": "chat", "params": {"text": prompt}, "confidence": 0.2})

    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        import urllib.request

        try:
            req = urllib.request.Request(f"{self.url}/api/tags")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False


# ─── Gemini Provider (optional) ──────────────────────────────────────

class GeminiProvider(LLMProvider):
    """Use Google Gemini API for intent extraction (requires API key)."""

    SYSTEM_PROMPT = OllamaProvider.SYSTEM_PROMPT  # reuse the same system prompt

    def __init__(self):
        import config
        self.api_key = config.GEMINI_API_KEY
        self.model = config.GEMINI_MODEL

    def generate(self, prompt: str) -> str:
        """Send prompt to Gemini API and return the response."""
        import urllib.request

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = json.dumps({
            "contents": [{"parts": [{"text": f"{self.SYSTEM_PROMPT}\n\nUser command: {prompt}"}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }).encode()

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "{}")
                        return _strip_markdown_json(text)
                return json.dumps({"tool": "ai", "action": "chat", "params": {"text": prompt}, "confidence": 0.2})
        except Exception as e:
            logger.error("Gemini API request failed: %s", e)
            return json.dumps({"tool": "ai", "action": "chat", "params": {"text": prompt}, "confidence": 0.2})

    def is_available(self) -> bool:
        return bool(self.api_key and str(self.api_key).strip())


# ─── Provider Factory ────────────────────────────────────────────────

def get_provider() -> LLMProvider:
    """
    Auto-detect and return the best available LLM provider.

    Priority: config setting → Ollama (if running) → Gemini (if API key set) → rule-based fallback.
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

    # Auto-detect: try Ollama, then Gemini, then rule-based fallback
    if provider_name == "auto":
        ollama = OllamaProvider()
        if ollama.is_available():
            logger.info("Auto-detected Ollama server.")
            return ollama
        gemini = GeminiProvider()
        if gemini.is_available():
            logger.info("Auto-detected Gemini API key.")
            return gemini

    # Default: rule-based (always works)
    logger.info("Using rule-based intent provider (fully offline).")
    return RuleBasedProvider()
