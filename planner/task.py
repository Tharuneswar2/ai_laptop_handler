"""
planner/task.py — Task and ExecutionPlan dataclasses for goal decomposition.

Defines the structure of decomposed tasks and multi-step execution plans.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Task:
    """Represents a single atomic step within an ExecutionPlan."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tool: str = ""                  # e.g., "project", "vscode", "terminal", "file"
    action: str = ""                # e.g., "find", "open_project", "activate_venv", "run"
    params: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # IDs of tasks that must finish first
    status: str = "pending"         # "pending", "running", "completed", "failed", "rolled_back"
    result: Optional[str] = None
    rollback_action: Optional[Dict[str, Any]] = None       # Optional undo step if task fails

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dict representation."""
        return {
            "id": self.id,
            "tool": self.tool,
            "action": self.action,
            "params": self.params,
            "dependencies": self.dependencies,
            "status": self.status,
            "result": self.result,
            "rollback_action": self.rollback_action,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create Task from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            tool=data.get("tool", ""),
            action=data.get("action", ""),
            params=data.get("params", {}),
            dependencies=data.get("dependencies", []),
            status=data.get("status", "pending"),
            result=data.get("result"),
            rollback_action=data.get("rollback_action"),
        )


@dataclass
class ExecutionPlan:
    """Represents a sequence of Tasks designed to fulfill a high-level user goal."""
    goal: str = ""
    tasks: List[Task] = field(default_factory=list)
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: str = "pending"         # "pending", "in_progress", "completed", "failed", "partially_completed"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    current_step_index: int = 0
    raw_response: str = ""

    @property
    def is_empty(self) -> bool:
        """Check if plan contains no tasks."""
        return len(self.tasks) == 0

    @property
    def total_tasks(self) -> int:
        """Return count of tasks."""
        return len(self.tasks)

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dict representation."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "current_step_index": self.current_step_index,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def __str__(self) -> str:
        tasks_str = "\n".join(f"  {i+1}. [{t.tool}.{t.action}] {t.params}" for i, t in enumerate(self.tasks))
        return f"ExecutionPlan(goal='{self.goal}', tasks={len(self.tasks)}):\n{tasks_str}"
