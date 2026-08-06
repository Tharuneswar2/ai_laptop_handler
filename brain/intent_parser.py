"""
brain/intent_parser.py — Parse and validate structured intents.

Takes raw text from the user, runs it through the LLM provider,
and returns a validated Intent dataclass ready for routing.
"""

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── Intent Data Structure ────────────────────────────────────────────

@dataclass
class Intent:
    """Represents a parsed user intent ready for tool routing."""
    tool: str = ""          # "file", "app", "browser", "system", "terminal", "ai"
    action: str = ""        # "create_folder", "open", "search", etc.
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    raw_text: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if the intent has minimum required fields."""
        return bool(self.tool and self.action)

    def __str__(self) -> str:
        return f"Intent(tool={self.tool}, action={self.action}, params={self.params}, confidence={self.confidence:.2f})"


# ─── Valid Tool/Action Combinations ───────────────────────────────────

VALID_ACTIONS = {
    "file": {"create_file", "create_folder", "move", "rename", "delete", "search"},
    "app": {"open", "close", "list"},
    "browser": {"open_url", "google_search", "youtube_search", "open_github"},
    "system": {"battery", "ram", "cpu", "disk", "volume", "brightness", "screenshot", "lock_screen"},
    "terminal": {"run"},
    "ai": {"summarize", "explain_code", "chat"},
}

# Actions that require confirmation before execution
DANGEROUS_ACTIONS = {
    ("file", "delete"),
    ("app", "close"),
}


# ─── Parsing Functions ───────────────────────────────────────────────

def parse_json_safely(raw: str) -> dict:
    """
    Parse a JSON string, handling common LLM output quirks.

    Args:
        raw: Raw JSON string (possibly with markdown code fences).

    Returns:
        Parsed dict, or empty dict on failure.
    """
    if not raw:
        return {}

    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse failed: %s — raw: %s", e, raw[:200])
        return {}


# LLM providers sometimes route "open X" to the wrong tool. These verbs
# always mean "launch an application", so they can be safely remapped.
_OPEN_VERB_RE = re.compile(r"^(open|launch|start)\s+(.+)$", re.IGNORECASE)
_OPEN_COMMAND_RE = re.compile(r"^(?:open|launch|start)(?:\s+-a)?\s+(.+)$", re.IGNORECASE)

# System actions the model invents that are really "open file explorer".
_FILE_EXPLORER_ACTIONS = {
    "open_file_explorer", "open_file_manager", "open_explorer", "explore",
    "open_files", "file_explorer", "show_file_explorer",
}


def _normalize_data(data: dict, raw_text: str) -> dict:
    """
    Correct common LLM mis-routes before validation.

    Fixes observed failures such as:
      - "open vs code"      → terminal.run with a hallucinated command
      - "open file explorer" → system.open_file_explorer (invalid action)

    Args:
        data: Raw intent dict from the LLM provider.
        raw_text: Original user command.

    Returns:
        Corrected intent dict.
    """
    if not data:
        return data

    tool = str(data.get("tool", "")).lower().strip()
    action = str(data.get("action", "")).lower().strip()
    params = data.get("params", {})
    if not isinstance(params, dict):
        params = {}
    confidence = float(data.get("confidence", 0.5))

    def _remap(new_tool: str, new_action: str, new_params: dict, conf: float) -> dict:
        return {"tool": new_tool, "action": new_action, "params": new_params, "confidence": conf}

    # system.open_file_explorer → app.open "file explorer"
    if tool == "system" and action in _FILE_EXPLORER_ACTIONS:
        return _remap("app", "open", {"app_name": "file explorer"}, max(confidence, 0.7))

    # terminal.run that actually contains app-launch syntax (e.g. "open -a VSCode")
    if tool == "terminal" and action == "run":
        cmd = str(params.get("command", "")).strip()
        m = _OPEN_COMMAND_RE.match(cmd)
        if m:
            return _remap("app", "open", {"app_name": m.group(1).strip()}, max(confidence, 0.7))

    # "open chrome and search X" → browser.google_search
    if tool == "app" and action == "open":
        app_name = str(params.get("app_name", ""))
        m = re.match(r"^(.+?)\s+and\s+search\s+(.+)$", app_name, re.IGNORECASE)
        if m:
            return _remap("browser", "google_search", {"query": m.group(2).strip()}, max(confidence, 0.6))

    # Raw text explicitly says "open/launch X" but the model sent it to a
    # destination that cannot open apps (chat fallback, system, terminal.run).
    if tool in ("ai", "system") or (tool == "terminal" and action == "run"):
        m = _OPEN_VERB_RE.match(raw_text.strip())
        if m and m.group(1).lower() != "start":
            return _remap("app", "open", {"app_name": m.group(2).strip()}, max(confidence, 0.8))

    # Bare acknowledgments must never trigger system/terminal/app actions
    if re.fullmatch(
        r"(?:yes|yeah|yep|yup|no|nope|ok|okay|sure|alright|thanks|thank you|hi|hello|hey)[\s.,!?]*",
        raw_text.strip(), re.IGNORECASE,
    ):
        if tool != "ai":
            return _remap("ai", "chat", {"text": raw_text.strip()}, max(confidence, 0.3))

    # Conversational questions the model over-eagerly turned into a web search
    if tool == "browser" and action == "google_search":
        if re.match(r"^(?:tell me about|tell me|explain|define)\b", raw_text.strip(), re.IGNORECASE):
            return _remap("ai", "chat", {"text": raw_text.strip()}, max(confidence, 0.5))

    # ai.summarize / ai.explain_code with no text → treat as plain chat
    if tool == "ai" and action in ("summarize", "explain_code") and not str(params.get("text", "")).strip():
        return _remap("ai", "chat", {"text": raw_text.strip()}, max(confidence, 0.3))

    return data


def validate_intent(data: dict, raw_text: str = "") -> Intent:
    """
    Validate parsed intent data and return an Intent object.

    Args:
        data: Dict with tool, action, params, confidence fields.
        raw_text: Original user text for reference.

    Returns:
        Validated Intent. Invalid intents get tool="ai", action="chat".
    """
    tool = data.get("tool", "").lower().strip()
    action = data.get("action", "").lower().strip()
    params = data.get("params", {})
    confidence = float(data.get("confidence", 0.5))

    # Ensure params is a dict
    if not isinstance(params, dict):
        params = {}

    # Validate tool exists
    if tool not in VALID_ACTIONS:
        logger.warning("Unknown tool '%s', falling back to AI chat.", tool)
        return Intent(
            tool="ai", action="chat",
            params={"text": raw_text or str(params)},
            confidence=0.2, raw_text=raw_text,
        )

    # Validate action exists for tool
    if action not in VALID_ACTIONS[tool]:
        logger.warning("Invalid action '%s' for tool '%s', falling back.", action, tool)
        return Intent(
            tool="ai", action="chat",
            params={"text": raw_text or str(params)},
            confidence=0.2, raw_text=raw_text,
        )

    return Intent(
        tool=tool,
        action=action,
        params=params,
        confidence=confidence,
        raw_text=raw_text,
    )


def requires_confirmation(intent: Intent) -> bool:
    """Check if an intent requires user confirmation before execution."""
    return (intent.tool, intent.action) in DANGEROUS_ACTIONS


def parse_intent(text: str) -> Intent:
    """
    Full pipeline: take user text → LLM → validated Intent.

    Args:
        text: Raw user text (e.g., "create a folder called projects").

    Returns:
        Validated Intent ready for routing.
    """
    from brain.llm import get_provider

    if not text or not text.strip():
        return Intent(tool="ai", action="chat", params={"text": ""}, confidence=0.0, raw_text=text)

    provider = get_provider()
    logger.info("Parsing intent with %s: '%s'", provider.name, text[:80])

    try:
        raw_json = provider.generate(text)
        data = parse_json_safely(raw_json)

        if not data:
            logger.warning("Provider returned unparseable output.")
            return Intent(
                tool="ai", action="chat",
                params={"text": text},
                confidence=0.1, raw_text=text,
            )

        data = _normalize_data(data, text)
        intent = validate_intent(data, raw_text=text)
        logger.info("Parsed intent: %s", intent)
        return intent

    except Exception as e:
        logger.error("Intent parsing failed: %s", e)
        return Intent(
            tool="ai", action="chat",
            params={"text": text},
            confidence=0.0, raw_text=text,
        )
