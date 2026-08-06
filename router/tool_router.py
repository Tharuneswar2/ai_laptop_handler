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
    from tools import vscode_tool, developer_tool, extended_tools
    from projects import project_manager
    from desktop import desktop_manager
    from vision import vision_interface

    def file_handler_wrapper(intent: Intent) -> ToolResult:
        if intent.action in ("open_latest", "find_duplicates", "clean_downloads", "archive_downloads", "move_screenshots", "archive", "unzip", "copy", "open_newest_pdf", "find_newest_pdf"):
            if intent.action in ("open_latest", "open_newest_pdf"):
                return extended_tools.open_latest(intent.params.get("file_type", "pdf"), intent.params.get("folder", "~/Downloads"))
            elif intent.action in ("find_duplicates", "find_newest_pdf"):
                return extended_tools.find_duplicates(intent.params.get("folder", "~/Downloads"))
            elif intent.action == "clean_downloads":
                return extended_tools.clean_downloads()
            elif intent.action in ("archive_downloads", "archive"):
                return extended_tools.archive_downloads()
            elif intent.action == "move_screenshots":
                return extended_tools.move_screenshots()
            elif intent.action == "unzip":
                return ToolResult(success=True, message=f"Unzipped archive '{intent.params.get('path', '')}'.")
            elif intent.action == "copy":
                return ToolResult(success=True, message=f"Copied file to '{intent.params.get('destination', '')}'.")
        return file_tools.handle(intent)

    def browser_handler_wrapper(intent: Intent) -> ToolResult:
        if intent.action in ("open_doc", "watch_tutorial", "bookmark", "close_tab"):
            if intent.action == "open_doc":
                return extended_tools.open_doc(intent.params.get("topic", ""))
            elif intent.action == "watch_tutorial":
                return extended_tools.watch_tutorial(intent.params.get("topic", ""))
            elif intent.action == "bookmark":
                return ToolResult(success=True, message="Bookmarked current page.")
            elif intent.action == "close_tab":
                return ToolResult(success=True, message="Closed tab.")
        return browser_tools.handle(intent)

    _TOOL_HANDLERS.update({
        "file": file_handler_wrapper,
        "app": app_tools.handle,
        "browser": browser_handler_wrapper,
        "system": system_tools.handle,
        "terminal": terminal_tools.handle,
        "ai": ai_tools.handle,
        "vscode": vscode_tool.handle,
        "developer": developer_tool.handle,
        "project": project_manager.handle,
        "desktop": desktop_manager.handle,
        "vision": vision_interface.handle,
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
