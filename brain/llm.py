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
        (r"(?:google |web )?search (?:for )?(.+?)(?:\s+on\s+(?:google|the web))?$", "browser", "google_search", lambda m: {"query": m.group(1).strip()}),

        # File operations
        (r"create (?:a )?folder (?:called |named )?(.+)", "file", "create_folder", lambda m: {"path": m.group(1).strip()}),
        (r"make (?:a )?folder (?:called |named )?(.+)", "file", "create_folder", lambda m: {"path": m.group(1).strip()}),
        (r"create (?:a )?file (?:called |named )?(.+)", "file", "create_file", lambda m: {"path": m.group(1).strip()}),
        (r"make (?:a )?file (?:called |named )?(.+)", "file", "create_file", lambda m: {"path": m.group(1).strip()}),
        (r"delete (?:the )?(?:file |folder )?(.+)", "file", "delete", lambda m: {"path": m.group(1).strip()}),
        (r"remove (?:the )?(?:file |folder )?(.+)", "file", "delete", lambda m: {"path": m.group(1).strip()}),
        (r"move (.+) to (.+)", "file", "move", lambda m: {"source": m.group(1).strip(), "destination": m.group(2).strip()}),
        (r"rename (.+) to (.+)", "file", "rename", lambda m: {"source": m.group(1).strip(), "new_name": m.group(2).strip()}),
        (r"(?:find|look for) (?:files? )?(?:called |named )?(.+)", "file", "search", lambda m: {"pattern": m.group(1).strip()}),

        # App operations
        (r"open (.+)", "app", "open", lambda m: {"app_name": m.group(1).strip()}),
        (r"launch (.+)", "app", "open", lambda m: {"app_name": m.group(1).strip()}),
        (r"start (.+)", "app", "open", lambda m: {"app_name": m.group(1).strip()}),
        (r"close (.+)", "app", "close", lambda m: {"app_name": m.group(1).strip()}),
        (r"(?:list|show) (?:running |open )?apps", "app", "list", lambda m: {}),
        (r"what(?:'s| is) running", "app", "list", lambda m: {}),

        # System operations
        (r"(?:show |check |get )?battery(?: (?:status|level|info))?", "system", "battery", lambda m: {}),
        (r"(?:how much )?battery", "system", "battery", lambda m: {}),
        (r"(?:show |check |get )?(?:ram|memory)(?: (?:usage|status|info))?", "system", "ram", lambda m: {}),
        (r"(?:show |check |get )?cpu(?: (?:usage|status|info))?", "system", "cpu", lambda m: {}),
        (r"(?:show |check |get )?disk(?: (?:usage|space|status|info))?", "system", "disk", lambda m: {}),
        (r"how much (?:disk )?space", "system", "disk", lambda m: {}),
        (r"(?:take |capture )?(?:a )?screenshot", "system", "screenshot", lambda m: {}),
        (r"lock (?:the )?(?:screen|computer|laptop)", "system", "lock_screen", lambda m: {}),
        (r"(?:set |change )?volume (?:to )?(\d+)", "system", "volume", lambda m: {"level": int(m.group(1))}),
        (r"(?:set |change )?brightness (?:to )?(\d+)", "system", "brightness", lambda m: {"level": int(m.group(1))}),

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

    def is_available(self) -> bool:
        return True


# ─── Ollama Provider (optional) ──────────────────────────────────────

class OllamaProvider(LLMProvider):
    """Connect to a local Ollama server for intent extraction."""

    SYSTEM_PROMPT = """You are an intent extraction engine for a voice-controlled laptop assistant.
Given a user command, extract the intent as a JSON object with these fields:
- "tool": one of "file", "app", "browser", "system", "terminal", "ai"
- "action": the specific action to perform
- "params": a dict of parameters for the action
- "confidence": float between 0 and 1

Valid actions per tool:
- file: create_file, create_folder, move, rename, delete, search
- app: open, close, list
- browser: open_url, google_search, youtube_search, open_github
- system: battery, ram, cpu, disk, volume, brightness, screenshot, lock_screen
- terminal: run
- ai: summarize, explain_code, chat

Respond ONLY with valid JSON. No extra text."""

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
                return result.get("response", "{}")
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
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                return text
        except Exception as e:
            logger.error("Gemini API request failed: %s", e)
            return json.dumps({"tool": "ai", "action": "chat", "params": {"text": prompt}, "confidence": 0.2})

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
