"""
conversation/memory.py — Short-term conversation memory for the creator-assistant layer.

Tracks current task, last instruction, missing parameters, active state,
pending confirmations, and recent results. Lightweight and scoped.
"""

import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional

from conversation.schemas import ConversationState, ConversationTurn, TaskResult

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Short-term memory for the conversational creator-assistant.

    Maintains:
    - Current task context
    - Last user instruction
    - Missing parameters
    - Active execution state
    - Pending confirmations
    - Recent results (last N turns)
    """

    def __init__(self, max_turns: int = 20):
        self.state = ConversationState()
        self.turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self._context: Dict[str, Any] = {}

    def record_turn(self, turn: ConversationTurn) -> None:
        """Record a conversation turn."""
        self.turns.append(turn)
        self.state.turn_count += 1

        if turn.speaker == "creator":
            self.state.last_instruction = turn.text
        elif turn.speaker == "assistant" and turn.result:
            self.state.last_result = turn.result

    def set_current_task(self, task: str) -> None:
        """Set the current active task description."""
        self.state.current_task = task
        self.state.active_execution = True

    def clear_current_task(self) -> None:
        """Clear the current task."""
        self.state.current_task = ""
        self.state.active_execution = False
        self.state.pending_confirmation = False
        self.state.missing_params = []

    def set_awaiting_clarification(self, missing_params: List[str], question: str) -> None:
        """Mark that we need clarification from the creator."""
        self.state.missing_params = missing_params
        self.state.pending_confirmation = True

    def set_pending_confirmation(self, pending: bool = True) -> None:
        """Set or clear pending confirmation state."""
        self.state.pending_confirmation = pending

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return self._context.get(key, default)

    def set_context(self, key: str, value: Any) -> None:
        """Set a context value."""
        self._context[key] = value

    def get_recent_turns(self, n: int = 5) -> List[ConversationTurn]:
        """Get the last N conversation turns."""
        return list(self.turns)[-n:]

    def get_last_assistant_response(self) -> Optional[str]:
        """Get the last assistant response text."""
        for turn in reversed(self.turns):
            if turn.speaker == "assistant":
                return turn.text
        return None

    def get_conversation_summary(self) -> str:
        """Get a brief summary of recent conversation for context."""
        recent = self.get_recent_turns(5)
        if not recent:
            return "No recent conversation."
        lines = []
        for turn in recent:
            prefix = "Creator" if turn.speaker == "assistant" else "You"
            lines.append(f"{prefix}: {turn.text[:100]}")
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all conversation state."""
        self.state = ConversationState()
        self.turns.clear()
        self._context.clear()
        logger.info("Conversation memory reset.")
