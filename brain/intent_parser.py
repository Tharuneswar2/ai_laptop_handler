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

    @classmethod
    def from_json(cls, json_str: str, raw_text: str = "") -> "Intent":
        """Build an Intent instance from a JSON string."""
        import json
        try:
            data = json.loads(json_str)
            return cls(
                tool=data.get("tool", "ai"),
                action=data.get("action", "chat"),
                params=data.get("params", {}),
                confidence=data.get("confidence", 0.5),
                raw_text=raw_text,
            )
        except Exception:
            return cls(tool="ai", action="chat", params={"text": raw_text}, confidence=0.3, raw_text=raw_text)


# ─── Valid Tool/Action Combinations ───────────────────────────────────

VALID_ACTIONS = {
    "file": {"create_file", "create_folder", "move", "rename", "delete", "search", "open_latest", "find_duplicates", "clean_downloads", "archive_downloads", "archive", "unzip", "copy", "open_newest_pdf", "find_newest_pdf", "move_screenshots"},
    "app": {"open", "close", "list", "open_folder", "open_terminal", "close_all"},
    "browser": {"open_url", "google_search", "youtube_search", "open_github", "open_doc", "watch_tutorial", "bookmark", "close_tab"},
    "system": {"battery", "ram", "cpu", "disk", "volume", "brightness", "brightness_up", "brightness_down", "diagnose_performance", "screenshot", "lock_screen"},
    "terminal": {"run"},
    "ai": {"summarize", "explain_code", "chat", "chat_pdf", "debug_error"},
    "vscode": {"open_project", "open_recent", "create_project", "open_workspace", "open_file", "install_extension", "run_task", "run_terminal", "reopen_last_workspace"},
    "developer": {"git_status", "git_commit", "git_push", "git_pull", "git_log", "create_venv", "activate_venv", "pip_install", "run_python", "run_backend", "docker_ps", "docker_logs", "docker_compose_up"},
    "project": {"find", "open_recent", "list", "list_projects", "scan", "scan_projects", "add", "remove"},
    "desktop": {"focus_app", "switch_app", "restore_session", "close_all", "minimize", "maximize", "get_state"},
    "vision": {"ocr_screen", "analyze_screen", "detect_objects", "screen_understanding", "read_screen", "ocr"},
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


def is_goal_request(text: str) -> bool:
    """Check if the text represents a high-level goal requiring multi-step planning."""
    from planner.reasoner import GoalReasoner, GoalType
    reasoner = GoalReasoner()
    goal = reasoner.detect_goal(text)
    if goal.type in (GoalType.OPEN_PROJECT, GoalType.CONTINUE_PROJECT, GoalType.DEVELOPER_WORKSPACE):
        return True

    lower = text.lower().strip()
    goal_patterns = [
        r"\b(start working|prepare for coding|start coding|coding mode)\b",
        r"\b(continue (my |yesterday's )?work|continue (my |the )?project)\b",
        r"\b(setup|create|build|init)\s+(fastapi|python|react|node)\b",
        r"\b(run|start|launch)\s+(my\s+)?backend\b",
        r"\b(push (latest )?changes|deploy (backend|project))\b",
        r"\b(build docker|docker compose)\b",
        r"\b(clean|archive)\s+downloads\b",
        r"\bopen (vs code|vscode)\s+(and|then)\s+create\b",
        r"\b(open|watch)\s+.*(documentation|docs|tutorial)\b",
    ]
    for pattern in goal_patterns:
        if re.search(pattern, lower):
            return True
    return False


def parse_intent(text: str):
    """
    Full pipeline: take user text → resolve context → parse Intent or ExecutionPlan.

    Args:
        text: Raw user text (e.g., "create a folder called projects").

    Returns:
        Intent or ExecutionPlan ready for execution.
    """
    from brain.llm import get_provider
    from brain.memory import Memory

    if not text or not text.strip():
        return Intent(tool="ai", action="chat", params={"text": ""}, confidence=0.0, raw_text=text)

    # 1. Anaphoric pronoun resolution ("open it", "run it again", "close it")
    try:
        mem = Memory()
        resolved_text = mem.resolve_reference(text)
    except Exception:
        resolved_text = text

    # 2. Goal detection for multi-step planning
    if is_goal_request(resolved_text):
        from planner.planner import create_plan
        plan = create_plan(resolved_text)
        if not plan.is_empty:
            logger.info("Parsed request '%s' as multi-step ExecutionPlan (%d tasks)", text, len(plan.tasks))
            return plan

    provider = get_provider()
    logger.info("Parsing intent with %s: '%s' (resolved: '%s')", provider.name, text[:80], resolved_text[:80])

    try:
        raw_json = provider.generate(resolved_text)
        data = parse_json_safely(raw_json)

        if not data:
            logger.warning("Provider returned unparseable output.")
            return Intent(
                tool="ai", action="chat",
                params={"text": resolved_text},
                confidence=0.1, raw_text=resolved_text,
            )

        data = _normalize_data(data, resolved_text)
        intent = validate_intent(data, raw_text=resolved_text)
        logger.info("Parsed intent: %s", intent)
        return intent

    except Exception as e:
        logger.error("Intent parsing failed: %s", e)
        return Intent(
            tool="ai", action="chat",
            params={"text": resolved_text},
            confidence=0.0, raw_text=resolved_text,
        )
