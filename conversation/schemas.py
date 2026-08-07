"""
conversation/schemas.py — Data structures for the conversational creator-assistant layer.

Defines intent types, task schemas, safety levels, and conversation state.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IntentType(str, Enum):
    """Supported intent types."""
    OPEN_APP = "OPEN_APP"
    CLOSE_APP = "CLOSE_APP"
    SEARCH_WEB = "SEARCH_WEB"
    SUMMARIZE_TEXT = "SUMMARIZE_TEXT"
    READ_FILE = "READ_FILE"
    WRITE_FILE = "WRITE_FILE"
    RUN_SCRIPT = "RUN_SCRIPT"
    CHECK_STATUS = "CHECK_STATUS"
    CONTROL_SETTING = "CONTROL_SETTING"
    CREATE_PROJECT = "CREATE_PROJECT"
    LIST_APPS = "LIST_APPS"
    SCREENSHOT = "SCREENSHOT"
    CONVERSATION = "CONVERSATION"
    UNKNOWN = "UNKNOWN"


class SafetyLevel(str, Enum):
    """Safety classification for intents."""
    SAFE = "safe"             # No risk, always allowed
    MODERATE = "moderate"     # Minor side effects (open app, search web)
    SENSITIVE = "sensitive"   # File/system modifications
    BLOCKED = "blocked"       # Never allowed from unknown speakers


class TaskState(str, Enum):
    """Current state of a task."""
    PENDING = "pending"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CreatorIntent:
    """Structured intent parsed from user speech."""
    intent_type: IntentType
    confidence: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)
    required_params: List[str] = field(default_factory=list)
    missing_params: List[str] = field(default_factory=list)
    safety_level: SafetyLevel = SafetyLevel.SAFE
    priority: int = 5  # 1=highest, 10=lowest
    raw_text: str = ""
    tool: str = ""          # mapped to existing tool name
    action: str = ""        # mapped to existing action name
    needs_clarification: bool = False
    clarification_question: str = ""


@dataclass
class TaskResult:
    """Result from task execution."""
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    speaker: str           # "creator" or "assistant"
    text: str
    intent: Optional[CreatorIntent] = None
    result: Optional[TaskResult] = None
    timestamp: float = 0.0


@dataclass
class ConversationState:
    """Current state of the conversation."""
    current_task: str = ""
    last_instruction: str = ""
    missing_params: List[str] = field(default_factory=list)
    active_execution: bool = False
    pending_confirmation: bool = False
    last_result: Optional[TaskResult] = None
    turn_count: int = 0
    creator_verified: bool = True  # default to True for single-user mode


# Safety classification map
INTENT_SAFETY: Dict[IntentType, SafetyLevel] = {
    IntentType.OPEN_APP: SafetyLevel.MODERATE,
    IntentType.CLOSE_APP: SafetyLevel.MODERATE,
    IntentType.SEARCH_WEB: SafetyLevel.SAFE,
    IntentType.SUMMARIZE_TEXT: SafetyLevel.SAFE,
    IntentType.READ_FILE: SafetyLevel.MODERATE,
    IntentType.WRITE_FILE: SafetyLevel.SENSITIVE,
    IntentType.RUN_SCRIPT: SafetyLevel.SENSITIVE,
    IntentType.CHECK_STATUS: SafetyLevel.SAFE,
    IntentType.CONTROL_SETTING: SafetyLevel.MODERATE,
    IntentType.CREATE_PROJECT: SafetyLevel.MODERATE,
    IntentType.LIST_APPS: SafetyLevel.SAFE,
    IntentType.SCREENSHOT: SafetyLevel.SAFE,
    IntentType.CONVERSATION: SafetyLevel.SAFE,
    IntentType.UNKNOWN: SafetyLevel.SAFE,
}

# Map from intent types to existing tool.action routing
INTENT_TOOL_MAP: Dict[IntentType, tuple] = {
    IntentType.OPEN_APP: ("app", "open"),
    IntentType.CLOSE_APP: ("app", "close"),
    IntentType.SEARCH_WEB: ("browser", "google_search"),
    IntentType.SUMMARIZE_TEXT: ("ai", "summarize"),
    IntentType.READ_FILE: ("file", "search"),
    IntentType.WRITE_FILE: ("file", "create_file"),
    IntentType.RUN_SCRIPT: ("terminal", "run"),
    IntentType.CHECK_STATUS: ("system", "battery"),
    IntentType.CONTROL_SETTING: ("system", "volume"),
    IntentType.CREATE_PROJECT: ("project", "create"),
    IntentType.LIST_APPS: ("app", "list_installed"),
    IntentType.SCREENSHOT: ("system", "screenshot"),
}
