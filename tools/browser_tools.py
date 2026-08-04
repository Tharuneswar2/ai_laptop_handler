"""
tools/browser_tools.py — Browser operations (open URL, search, YouTube, GitHub).

Uses the system default browser via `webbrowser.open()` — zero dependencies.
"""

import logging
import urllib.parse
import webbrowser

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def open_url(url: str) -> ToolResult:
    """Open a URL in the default browser."""
    if not url:
        return ToolResult(success=False, message="No URL provided.")

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        webbrowser.open(url)
        logger.info("Opened URL: %s", url)
        return ToolResult(success=True, message=f"Opened {url}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open URL: {e}")


def google_search(query: str) -> ToolResult:
    """Search Google for the given query."""
    if not query:
        return ToolResult(success=False, message="No search query provided.")

    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}"

    try:
        webbrowser.open(url)
        logger.info("Google search: '%s'", query)
        return ToolResult(success=True, message=f"Searched Google for '{query}'.")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to search: {e}")


def youtube_search(query: str) -> ToolResult:
    """Search or open YouTube."""
    if not query:
        url = "https://www.youtube.com"
        msg = "Opened YouTube."
    else:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        msg = f"Searched YouTube for '{query}'."

    try:
        webbrowser.open(url)
        logger.info("YouTube: %s", msg)
        return ToolResult(success=True, message=msg)
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open YouTube: {e}")


def open_github() -> ToolResult:
    """Open GitHub in the default browser."""
    try:
        webbrowser.open("https://github.com")
        logger.info("Opened GitHub.")
        return ToolResult(success=True, message="Opened GitHub.")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to open GitHub: {e}")


# ─── Handler ──────────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route browser tool actions."""
    action = intent.action
    params = intent.params

    if action == "open_url":
        return open_url(params.get("url", ""))
    elif action == "google_search":
        return google_search(params.get("query", ""))
    elif action == "youtube_search":
        return youtube_search(params.get("query", ""))
    elif action == "open_github":
        return open_github()
    else:
        return ToolResult(success=False, message=f"Unknown browser action: {action}")
