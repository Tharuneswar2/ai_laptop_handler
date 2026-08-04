"""
tools/ai_tools.py — AI utility features (summarize, explain code, chat).

Uses the LLM provider from brain/llm.py for generation.
Falls back gracefully when no LLM is available.
"""

import logging

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def _get_llm_response(prompt: str) -> str:
    """Get a text response from the best available LLM provider."""
    from brain.llm import get_provider, RuleBasedProvider

    provider = get_provider()

    # Rule-based provider can't do free-form text generation
    if isinstance(provider, RuleBasedProvider):
        return ""

    try:
        return provider.generate(prompt)
    except Exception as e:
        logger.error("LLM generation failed: %s", e)
        return ""


def summarize(text: str) -> ToolResult:
    """Summarize the given text using the LLM."""
    if not text:
        return ToolResult(success=False, message="No text provided to summarize.")

    prompt = f"Summarize the following text concisely:\n\n{text}"
    response = _get_llm_response(prompt)

    if response:
        return ToolResult(success=True, message=f"Summary: {response}")
    else:
        return ToolResult(
            success=False,
            message="Text summarization requires an LLM (Ollama or Gemini). "
                    "Set up Ollama locally or add a GEMINI_API_KEY to .env.",
        )


def explain_code(text: str) -> ToolResult:
    """Explain code using the LLM."""
    if not text:
        return ToolResult(success=False, message="No code provided to explain.")

    prompt = f"Explain the following code in simple terms:\n\n{text}"
    response = _get_llm_response(prompt)

    if response:
        return ToolResult(success=True, message=f"Explanation: {response}")
    else:
        return ToolResult(
            success=False,
            message="Code explanation requires an LLM (Ollama or Gemini). "
                    "Set up Ollama locally or add a GEMINI_API_KEY to .env.",
        )


def chat(text: str) -> ToolResult:
    """General chat / Q&A."""
    if not text:
        return ToolResult(success=True, message="I'm Nova, your laptop assistant! How can I help?")

    prompt = f"Answer this question briefly and helpfully:\n\n{text}"
    response = _get_llm_response(prompt)

    if response:
        return ToolResult(success=True, message=response)
    else:
        # Friendly fallback when no LLM is available
        return ToolResult(
            success=True,
            message=f"I heard you say: \"{text}\". "
                    "I can help with file operations, opening apps, web searches, "
                    "and system info. For AI chat, set up Ollama or add a Gemini API key.",
        )


# ─── Handler ──────────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route AI tool actions."""
    action = intent.action
    params = intent.params

    if action == "summarize":
        return summarize(params.get("text", ""))
    elif action == "explain_code":
        return explain_code(params.get("text", ""))
    elif action == "chat":
        return chat(params.get("text", ""))
    else:
        return ToolResult(success=False, message=f"Unknown AI action: {action}")
