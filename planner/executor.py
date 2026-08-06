"""
planner/executor.py — Sequential task execution engine for ExecutionPlans.

Executes each task in an ExecutionPlan sequentially through the Tool Router,
handles dependency validation, updates desktop memory, and supports step-by-step
logging, event broadcasting, and task rollbacks on error.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from brain.intent_parser import Intent
from planner.task import ExecutionPlan, Task
from router.tool_router import ToolResult, route

logger = logging.getLogger(__name__)


class PlanExecutor:
    """
    Executes an ExecutionPlan task-by-task.
    """

    def __init__(self, event_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.event_callback = event_callback

    def _notify(self, event: Dict[str, Any]) -> None:
        """Send event notification to callback / observer."""
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                logger.warning("Event callback failed: %s", e)

        # Also emit to server observer list if server is active
        try:
            from api.server import _emit
            _emit(event)
        except ImportError:
            pass
        except Exception:
            pass

    def execute(self, plan: ExecutionPlan) -> ToolResult:
        """
        Execute an ExecutionPlan and return a summary ToolResult.

        Args:
            plan: The ExecutionPlan to execute.

        Returns:
            ToolResult containing overall status, combined messages, and task data.
        """
        if not plan or plan.is_empty:
            return ToolResult(success=False, message="Empty execution plan.")

        logger.info("Starting ExecutionPlan %s: '%s' (%d tasks)", plan.plan_id, plan.goal, len(plan.tasks))
        plan.status = "in_progress"

        self._notify({
            "type": "plan_started",
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "total_tasks": len(plan.tasks),
        })

        results: List[ToolResult] = []
        executed_tasks: List[Task] = []
        failed_task: Optional[Task] = None
        start_time = time.time()

        for index, task in enumerate(plan.tasks):
            plan.current_step_index = index
            task.status = "running"

            self._notify({
                "type": "task_started",
                "plan_id": plan.plan_id,
                "step": index + 1,
                "total": len(plan.tasks),
                "tool": task.tool,
                "action": task.action,
                "params": task.params,
            })

            # Form intent object for router
            intent = Intent(
                tool=task.tool,
                action=task.action,
                params=task.params,
                confidence=1.0,
                raw_text=f"[{task.tool}.{task.action}] {plan.goal}",
            )

            task_start = time.time()
            result = route(intent)
            duration_ms = int((time.time() - task_start) * 1000)

            task.result = result.message
            results.append(result)

            if result.success:
                task.status = "completed"
                executed_tasks.append(task)
                logger.info("Task %d/%d [%s.%s] succeeded in %dms: %s",
                            index + 1, len(plan.tasks), task.tool, task.action, duration_ms, result.message[:100])

                self._notify({
                    "type": "task_completed",
                    "plan_id": plan.plan_id,
                    "step": index + 1,
                    "tool": task.tool,
                    "action": task.action,
                    "result": result.message,
                    "duration_ms": duration_ms,
                })
            else:
                task.status = "failed"
                failed_task = task
                logger.warning("Task %d/%d [%s.%s] failed: %s",
                               index + 1, len(plan.tasks), task.tool, task.action, result.message)

                self._notify({
                    "type": "task_failed",
                    "plan_id": plan.plan_id,
                    "step": index + 1,
                    "tool": task.tool,
                    "action": task.action,
                    "error": result.message,
                })

                # Perform rollback if rollback action exists
                self._handle_rollback(executed_tasks)
                break

        total_duration_ms = int((time.time() - start_time) * 1000)

        # Log plan execution to Memory
        try:
            from brain.memory import Memory
            mem = Memory()
            status_str = "ok" if not failed_task else "error"
            summary_msg = f"Executed plan ({len(executed_tasks)}/{len(plan.tasks)} completed): {plan.goal}"
            mem.add(
                user_text=plan.goal,
                intent=f"planner.execute_plan",
                result=summary_msg,
                status=status_str,
                duration_ms=total_duration_ms,
            )
        except Exception as e:
            logger.error("Failed to update memory after plan execution: %s", e)

        if failed_task:
            plan.status = "failed"
            self._notify({
                "type": "plan_failed",
                "plan_id": plan.plan_id,
                "failed_step": plan.current_step_index + 1,
                "error": failed_task.result,
            })
            return ToolResult(
                success=False,
                message=f"Plan halted at step {plan.current_step_index + 1} ({failed_task.tool}.{failed_task.action}): {failed_task.result}",
                data={"plan": plan.to_dict(), "results": [r.message for r in results]},
            )

        plan.status = "completed"
        success_messages = [f"• {t.tool}.{t.action}: {t.result}" for t in executed_tasks]
        summary_text = f"Successfully executed goal: '{plan.goal}' ({len(executed_tasks)} steps):\n" + "\n".join(success_messages)

        self._notify({
            "type": "plan_completed",
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "steps_completed": len(executed_tasks),
            "duration_ms": total_duration_ms,
        })

        return ToolResult(
            success=True,
            message=summary_text,
            data={"plan": plan.to_dict(), "results": [r.message for r in results]},
        )

    def _handle_rollback(self, executed_tasks: List[Task]) -> None:
        """Roll back executed tasks in reverse order if rollback action is defined."""
        if not executed_tasks:
            return

        logger.info("Initiating rollback for %d executed tasks...", len(executed_tasks))
        for task in reversed(executed_tasks):
            if task.rollback_action:
                try:
                    r_tool = task.rollback_action.get("tool", "")
                    r_action = task.rollback_action.get("action", "")
                    r_params = task.rollback_action.get("params", {})
                    logger.info("Executing rollback task [%s.%s] for step %s", r_tool, r_action, task.id)

                    r_intent = Intent(tool=r_tool, action=r_action, params=r_params)
                    route(r_intent)
                    task.status = "rolled_back"
                except Exception as e:
                    logger.error("Rollback failed for task %s: %s", task.id, e)


def execute_plan(plan: ExecutionPlan, observer_callback: Optional[Callable] = None) -> ToolResult:
    """Helper function to execute an ExecutionPlan."""
    executor = PlanExecutor(event_callback=observer_callback)
    return executor.execute(plan)
