"""
conversation/conversation.py — Main conversational creator-assistant engine.

Coordinates intent understanding, safety checks, task execution,
and natural response generation. Integrates with the existing
parse_intent + route pipeline.
"""

import logging
import re
import time
from typing import Optional, Tuple

from conversation.schemas import (
    CreatorIntent,
    IntentType,
    SafetyLevel,
    TaskResult,
    TaskState,
    INTENT_SAFETY,
    INTENT_TOOL_MAP,
)
from conversation.memory import ConversationMemory
from conversation.safety import SafetyGate
from conversation.response_builder import ResponseBuilder
from conversation.task_orchestrator import TaskOrchestrator

logger = logging.getLogger(__name__)


# Intent classification patterns (simple keyword matching for the conversation layer)
_INTENT_PATTERNS = [
    # Open app
    (r"\b(?:open|launch|start|run)\s+(.+)", IntentType.OPEN_APP, ["app_name"]),
    # Close app
    (r"\b(?:close|quit|exit|stop)\s+(.+)", IntentType.CLOSE_APP, ["app_name"]),
    # Search web
    (r"\b(?:search|google|look up|find)\s+(?:for\s+)?(.+)", IntentType.SEARCH_WEB, ["query"]),
    # Summarize
    (r"\b(?:summarize|summary|tldr)\s*(.+)?", IntentType.SUMMARIZE_TEXT, ["text"]),
    # Screenshot
    (r"\b(?:take|capture)\s+(?:a\s+)?screenshot\b", IntentType.SCREENSHOT, []),
    # Check status
    (r"\b(?:check|show|get|what(?:'s| is))\s+(?:my\s+)?(?:battery|ram|cpu|disk|status)\b", IntentType.CHECK_STATUS, []),
    # List apps
    (r"\b(?:list|show)\s+(?:installed\s+)?(?:apps|applications|programs)\b", IntentType.LIST_APPS, []),
    # Create project
    (r"\b(?:create|make|new)\s+(?:a\s+)?project\s+(?:called|named)?\s*(.+)?", IntentType.CREATE_PROJECT, ["name"]),
    # Run script
    (r"\b(?:run|execute)\s+(.+)", IntentType.RUN_SCRIPT, ["command"]),
    # Volume/brightness
    (r"\b(?:set|change)\s+(?:volume|brightness)\s+(?:to\s+)?(\d+)", IntentType.CONTROL_SETTING, ["level"]),
]


class ConversationEngine:
    """
    Main conversational creator-assistant engine.

    Flow:
    1. Receive raw text from creator
    2. Check creator safety
    3. Parse to structured intent
    4. Check if clarification is needed
    5. If ready, dispatch task through existing handlers
    6. Build natural response
    7. Update memory
    8. Return conversational result
    """

    def __init__(self):
        self.memory = ConversationMemory()
        self.safety = SafetyGate()
        self.response_builder = ResponseBuilder()
        self.orchestrator = TaskOrchestrator()
        self._last_intent: Optional[CreatorIntent] = None

    def process(self, text: str, speaker_id: Optional[str] = None) -> Tuple[str, Optional[TaskResult]]:
        """
        Process a user utterance through the full conversational pipeline.

        Args:
            text: Raw text from speech recognition
            speaker_id: Optional speaker identifier (None = single-user mode)

        Returns:
            (assistant_response_text, optional_task_result)
        """
        if not text or not text.strip():
            return self.response_builder.confused(), None

        text = text.strip()
        logger.info("[Conversation] Received: '%s'", text[:80])

        # 1. Creator safety check
        is_creator = self.safety.verify_creator(speaker_id)
        if not is_creator:
            response = self.response_builder.blocked()
            self._record_turn("creator", text)
            self._record_turn("assistant", response)
            logger.warning("[Safety] Unknown speaker blocked: '%s'", text[:40])
            return response, None

        # 2. Record creator turn
        self._record_turn("creator", text)

        # 3. Check if this is a clarification response
        if self.memory.state.pending_confirmation and self.memory.state.missing_params:
            return self._handle_clarification(text)

        # 4. Parse intent
        intent = self._parse_intent(text)
        self._last_intent = intent

        logger.info("[Intent] %s confidence=%.2f", intent.intent_type.value, intent.confidence)

        # 5. Check if clarification is needed
        if intent.needs_clarification:
            self.memory.set_awaiting_clarification(
                intent.missing_params,
                intent.clarification_question,
            )
            response = self.response_builder.needs_clarification(intent.clarification_question)
            self._record_turn("assistant", response)
            return response, None

        # 5b. Handle greetings and farewells directly
        if intent.intent_type == IntentType.CONVERSATION:
            if intent.params.get("greeting"):
                response = self.response_builder.greeting()
                self._record_turn("assistant", response)
                return response, None
            if intent.params.get("farewell"):
                response = self.response_builder.farewell()
                self._record_turn("assistant", response)
                return response, None

        # 6. Safety gate
        allowed, reason = self.safety.check_intent_safety(intent)
        if not allowed:
            response = self.response_builder.blocked()
            self._record_turn("assistant", response)
            logger.warning("[Safety] Blocked: %s - %s", intent.intent_type.value, reason)
            return response, None

        # 7. Execute task
        self.memory.set_current_task(f"{intent.intent_type.value}: {text[:60]}")
        result = self.orchestrator.execute_intent(intent)
        self.memory.clear_current_task()

        # 8. Build response
        if result.success:
            response = self.response_builder.task_completed(intent, result)
        else:
            response = self.response_builder.task_failed(intent, result)

        # 9. Record assistant turn
        self._record_turn("assistant", response, intent, result)

        return response, result

    def _parse_intent(self, text: str) -> CreatorIntent:
        """
        Parse raw text into a structured CreatorIntent.

        Uses the existing parse_intent as the primary parser,
        then maps the result to CreatorIntent format.
        """
        # Pre-check: detect incomplete commands that need clarification
        text_lower = text.lower().strip()

        # Greetings — return proper conversational response
        _greeting_words = {
            "hello", "hi", "hai", "hey", "good morning", "good afternoon",
            "good evening", "howdy", "greetings", "sup", "what's up",
            "hey nova", "hey assistant", "innova", "hey innova",
        }
        if text_lower in _greeting_words or text_lower.rstrip("!.?") in _greeting_words:
            return CreatorIntent(
                intent_type=IntentType.CONVERSATION,
                confidence=0.95,
                params={"text": text, "greeting": True},
                raw_text=text,
                tool="ai",
                action="chat",
            )

        # Farewells
        _farewell_words = {"bye", "goodbye", "see you", "see ya", "goodnight", "good night", "quit", "exit"}
        if text_lower in _farewell_words or text_lower.rstrip("!.?") in _farewell_words:
            return CreatorIntent(
                intent_type=IntentType.CONVERSATION,
                confidence=0.95,
                params={"text": text, "farewell": True},
                raw_text=text,
                tool="ai",
                action="chat",
            )

        # Incomplete search commands
        if text_lower in ("search", "search for", "google", "google search", "look up"):
            return CreatorIntent(
                intent_type=IntentType.SEARCH_WEB,
                confidence=0.8,
                params={},
                missing_params=["query"],
                raw_text=text,
                tool="browser",
                action="google_search",
                needs_clarification=True,
                clarification_question="What would you like me to search for?",
            )

        # Incomplete open commands
        if text_lower in ("open", "launch", "start"):
            return CreatorIntent(
                intent_type=IntentType.OPEN_APP,
                confidence=0.8,
                params={},
                missing_params=["app_name"],
                raw_text=text,
                tool="app",
                action="open",
                needs_clarification=True,
                clarification_question="Which app should I open?",
            )

        # Incomplete close commands
        if text_lower in ("close", "quit", "exit", "stop"):
            return CreatorIntent(
                intent_type=IntentType.CLOSE_APP,
                confidence=0.8,
                params={},
                missing_params=["app_name"],
                raw_text=text,
                tool="app",
                action="close",
                needs_clarification=True,
                clarification_question="Which app should I close?",
            )

        # Incomplete run commands
        if text_lower in ("run", "execute"):
            return CreatorIntent(
                intent_type=IntentType.RUN_SCRIPT,
                confidence=0.8,
                params={},
                missing_params=["command"],
                raw_text=text,
                tool="terminal",
                action="run",
                needs_clarification=True,
                clarification_question="What command should I run?",
            )

        # Incomplete create project
        if text_lower in ("create project", "new project", "make project"):
            return CreatorIntent(
                intent_type=IntentType.CREATE_PROJECT,
                confidence=0.8,
                params={},
                missing_params=["name"],
                raw_text=text,
                tool="project",
                action="create",
                needs_clarification=True,
                clarification_question="What should I name the project?",
            )

        # First, try the existing parse_intent for accurate routing
        from brain.intent_parser import parse_intent
        from planner.task import ExecutionPlan

        parsed = parse_intent(text)

        # If it's an ExecutionPlan, handle it as a multi-step task
        if isinstance(parsed, ExecutionPlan):
            return CreatorIntent(
                intent_type=IntentType.UNKNOWN,  # will be dispatched via plan
                confidence=0.9,
                params={"plan": parsed},
                raw_text=text,
                tool="planner",
                action="execute_plan",
            )

        # Map existing Intent to CreatorIntent
        intent = parsed
        intent_type = self._map_tool_to_intent(intent.tool, intent.action)
        safety_level = INTENT_SAFETY.get(intent_type, SafetyLevel.SAFE)

        # Check for missing required params
        missing = []
        clarification = ""
        needs_clarification = False

        # Example: search without query
        if intent_type == IntentType.SEARCH_WEB and not intent.params.get("query"):
            missing.append("query")
            clarification = "What would you like me to search for?"
            needs_clarification = True

        # Example: open app without name
        if intent_type == IntentType.OPEN_APP and not intent.params.get("app_name"):
            missing.append("app_name")
            clarification = "Which app should I open?"
            needs_clarification = True

        # Example: close app without name
        if intent_type == IntentType.CLOSE_APP and not intent.params.get("app_name"):
            missing.append("app_name")
            clarification = "Which app should I close?"
            needs_clarification = True

        # Example: create project without name
        if intent_type == IntentType.CREATE_PROJECT and not intent.params.get("name"):
            missing.append("name")
            clarification = "What should I name the project?"
            needs_clarification = True

        return CreatorIntent(
            intent_type=intent_type,
            confidence=intent.confidence,
            params=intent.params,
            required_params=list(intent.params.keys()),
            missing_params=missing,
            safety_level=safety_level,
            raw_text=text,
            tool=intent.tool,
            action=intent.action,
            needs_clarification=needs_clarification,
            clarification_question=clarification,
        )

    def _map_tool_to_intent(self, tool: str, action: str) -> IntentType:
        """Map existing tool.action to IntentType."""
        mapping = {
            ("app", "open"): IntentType.OPEN_APP,
            ("app", "close"): IntentType.CLOSE_APP,
            ("app", "list"): IntentType.LIST_APPS,
            ("app", "list_installed"): IntentType.LIST_APPS,
            ("browser", "google_search"): IntentType.SEARCH_WEB,
            ("browser", "youtube_search"): IntentType.SEARCH_WEB,
            ("browser", "open_url"): IntentType.SEARCH_WEB,
            ("ai", "summarize"): IntentType.SUMMARIZE_TEXT,
            ("ai", "explain_code"): IntentType.SUMMARIZE_TEXT,
            ("ai", "chat"): IntentType.CONVERSATION,
            ("file", "search"): IntentType.READ_FILE,
            ("file", "create_file"): IntentType.WRITE_FILE,
            ("file", "create_folder"): IntentType.WRITE_FILE,
            ("terminal", "run"): IntentType.RUN_SCRIPT,
            ("system", "battery"): IntentType.CHECK_STATUS,
            ("system", "ram"): IntentType.CHECK_STATUS,
            ("system", "cpu"): IntentType.CHECK_STATUS,
            ("system", "disk"): IntentType.CHECK_STATUS,
            ("system", "volume"): IntentType.CONTROL_SETTING,
            ("system", "brightness"): IntentType.CONTROL_SETTING,
            ("system", "screenshot"): IntentType.SCREENSHOT,
            ("system", "lock_screen"): IntentType.CONTROL_SETTING,
            ("project", "create"): IntentType.CREATE_PROJECT,
            ("project", "create_project"): IntentType.CREATE_PROJECT,
            ("vscode", "open_project"): IntentType.OPEN_APP,
            ("developer", "git_status"): IntentType.CHECK_STATUS,
        }
        return mapping.get((tool, action), IntentType.UNKNOWN)

    def _handle_clarification(self, text: str) -> Tuple[str, Optional[TaskResult]]:
        """Handle a clarification response from the creator."""
        # Simple: if we have a pending intent and the user provides a value, fill it in
        if self._last_intent and self.memory.state.missing_params:
            for param in self.memory.state.missing_params:
                if param in ("app_name", "name"):
                    self._last_intent.params[param] = text
                elif param == "query":
                    self._last_intent.params["query"] = text
                elif param == "command":
                    self._last_intent.params["command"] = text

            self._last_intent.needs_clarification = False
            self._last_intent.missing_params = []
            self.memory.state.missing_params = []
            self.memory.state.pending_confirmation = False

            # Now execute
            self.memory.set_current_task(f"{self._last_intent.intent_type.value}: {text[:60]}")
            result = self.orchestrator.execute_intent(self._last_intent)
            self.memory.clear_current_task()

            if result.success:
                response = self.response_builder.task_completed(self._last_intent, result)
            else:
                response = self.response_builder.task_failed(self._last_intent, result)

            self._record_turn("assistant", response, self._last_intent, result)
            return response, result

        # Fallback: treat as a new command
        self.memory.state.pending_confirmation = False
        self.memory.state.missing_params = []
        return self.process(text)

    def _record_turn(
        self,
        speaker: str,
        text: str,
        intent: Optional[CreatorIntent] = None,
        result: Optional[TaskResult] = None,
    ) -> None:
        """Record a conversation turn."""
        from conversation.schemas import ConversationTurn
        turn = ConversationTurn(
            speaker=speaker,
            text=text,
            intent=intent,
            result=result,
            timestamp=time.time(),
        )
        self.memory.record_turn(turn)

    def get_state(self) -> dict:
        """Get current conversation state as a dict."""
        return {
            "current_task": self.memory.state.current_task,
            "last_instruction": self.memory.state.last_instruction,
            "turn_count": self.memory.state.turn_count,
            "pending_confirmation": self.memory.state.pending_confirmation,
            "active_execution": self.memory.state.active_execution,
        }

    def reset(self) -> None:
        """Reset the conversation engine."""
        self.memory.reset()
        self.orchestrator.reset()
        self._last_intent = None
        logger.info("Conversation engine reset.")


# Singleton instance
_engine: Optional[ConversationEngine] = None


def get_conversation_engine() -> ConversationEngine:
    """Return the singleton conversation engine."""
    global _engine
    if _engine is None:
        _engine = ConversationEngine()
    return _engine
