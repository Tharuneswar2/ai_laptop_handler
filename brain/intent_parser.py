"""
brain/intent_parser.py — Parse and validate structured intents.

Takes raw text from the user, runs it through the LLM provider,
and returns a validated Intent dataclass ready for routing.
"""

import json
import logging
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
