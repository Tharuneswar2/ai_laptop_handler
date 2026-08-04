"""
router/tool_router.py — Route parsed intents to the correct tool handler.

Uses a simple registry pattern: dict[tool_name, handler_function].
Each handler takes an Intent and returns a ToolResult.
"""

import logging
from dataclasses import dataclass

from brain.intent_parser import Intent

logger = logging.getLogger(__name__)


# ─── Result Data Structure ────────────────────────────────────────────

@dataclass
class ToolResult:
    """Standardized result from any tool execution."""
    success: bool
    message: str
    data: dict = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}

    def __str__(self) -> str:
        icon = "✅" if self.success else "❌"
        return f"{icon} {self.message}"


# ─── Tool Registry ───────────────────────────────────────────────────

# Maps tool names to their handler modules
_TOOL_HANDLERS = {}


def _load_handlers() -> dict:
    """
    Lazily load all tool handler functions.

    Each tool module must have a `handle(intent: Intent) -> ToolResult` function.
    """
    if _TOOL_HANDLERS:
        return _TOOL_HANDLERS

    from tools import file_tools, app_tools, browser_tools, system_tools, terminal_tools, ai_tools

    _TOOL_HANDLERS.update({
        "file": file_tools.handle,
        "app": app_tools.handle,
        "browser": browser_tools.handle,
        "system": system_tools.handle,
        "terminal": terminal_tools.handle,
        "ai": ai_tools.handle,
    })

    logger.info("Loaded %d tool handlers: %s", len(_TOOL_HANDLERS), list(_TOOL_HANDLERS.keys()))
    return _TOOL_HANDLERS


def route(intent: Intent) -> ToolResult:
    """
    Route an intent to the appropriate tool handler.

    Args:
        intent: A validated Intent from the intent parser.

    Returns:
        ToolResult with success status and message.
    """
    if not intent.is_valid:
        return ToolResult(
            success=False,
            message="I didn't understand that command. Could you try rephrasing?",
        )

    handlers = _load_handlers()

    handler = handlers.get(intent.tool)
    if handler is None:
        return ToolResult(
            success=False,
            message=f"Unknown tool '{intent.tool}'. Available tools: {', '.join(handlers.keys())}",
        )

    try:
        logger.info("Routing to %s.%s with params=%s", intent.tool, intent.action, intent.params)
        result = handler(intent)
        logger.info("Tool result: %s", result)
        return result
    except Exception as e:
        logger.error("Tool execution failed: %s", e, exc_info=True)
        return ToolResult(
            success=False,
            message=f"An error occurred while running {intent.tool}.{intent.action}: {e}",
        )
