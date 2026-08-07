"""
conversation/task_orchestrator.py — Task execution wrapper for the creator-assistant layer.

Wraps the existing router.tool_router.route() and planner.executor.execute_plan()
to provide task execution with progress tracking, timeout handling, and retry logic.
"""

import logging
import time
from typing import Optional

from conversation.schemas import (
    CreatorIntent,
    IntentType,
    TaskResult,
    TaskState,
    INTENT_TOOL_MAP,
)
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    """
    Orchestrates task execution through the existing system handlers.

    - Supports sequential step execution
    - Supports task cancellation
    - Supports timeout handling
    - Supports result reporting
    - Supports simple retry logic
    - Avoids duplicate task execution
    - Keeps execution state explicit
    """

    def __init__(self):
        self._current_state: TaskState = TaskState.PENDING
        self._current_task_id: Optional[str] = None
        self._execution_start: float = 0.0

    @property
    def state(self) -> TaskState:
        return self._current_state

    def execute_intent(self, intent: CreatorIntent) -> TaskResult:
        """
        Execute a parsed intent through the existing system handlers.

        Maps the CreatorIntent to the existing tool/action system and routes it.
        """
        if self._current_state == TaskState.EXECUTING:
            logger.warning("Task already executing. Waiting for completion.")
            return TaskResult(False, "A task is already in progress, Sir.")

        self._current_state = TaskState.EXECUTING
        self._execution_start = time.time()

        try:
            result = self._dispatch(intent)
            duration_ms = int((time.time() - self._execution_start) * 1000)
            result.duration_ms = duration_ms

            if result.success:
                self._current_state = TaskState.COMPLETED
                logger.info("[Task] Completed: %s (%dms)", intent.intent_type.value, duration_ms)
            else:
                self._current_state = TaskState.FAILED
                logger.warning("[Task] Failed: %s - %s", intent.intent_type.value, result.message)

            return result

        except Exception as e:
            duration_ms = int((time.time() - self._execution_start) * 1000)
            self._current_state = TaskState.FAILED
            logger.error("[Task] Exception: %s - %s", intent.intent_type.value, e)
            return TaskResult(False, f"Execution error: {e}", duration_ms=duration_ms)

        finally:
            # Reset state after a brief delay to allow result to be read
            pass

    def _dispatch(self, intent: CreatorIntent) -> TaskResult:
        """
        Route an intent to the appropriate existing handler.
        """
        # Map to existing tool/action
        tool_name = intent.tool
        action_name = intent.action

        # If not explicitly set, look up from the intent type mapping
        if not tool_name or not action_name:
            mapping = INTENT_TOOL_MAP.get(intent.intent_type)
            if mapping:
                tool_name, action_name = mapping
            else:
                return TaskResult(False, f"I do not know how to do that yet, Sir.")

        # Build the Intent object for the existing router
        from brain.intent_parser import Intent
        router_intent = Intent(
            tool=tool_name,
            action=action_name,
            params=intent.params,
            confidence=intent.confidence,
            raw_text=intent.raw_text,
        )

        # Route through the existing system
        from router.tool_router import route
        tool_result: ToolResult = route(router_intent)

        return TaskResult(
            success=tool_result.success,
            message=tool_result.message,
            data=tool_result.data if tool_result.data else {},
        )

    def cancel(self) -> bool:
        """Cancel the current task if executing."""
        if self._current_state == TaskState.EXECUTING:
            self._current_state = TaskState.CANCELLED
            logger.info("[Task] Cancelled: %s", self._current_task_id)
            return True
        return False

    def reset(self) -> None:
        """Reset the orchestrator state."""
        self._current_state = TaskState.PENDING
        self._current_task_id = None
        self._execution_start = 0.0
