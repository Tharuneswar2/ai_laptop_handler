"""
planner/planner.py — Goal decomposition and ExecutionPlan generator.

Integrates Goal Reasoner, Project Manager fuzzy lookups, and planner rules.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from planner.reasoner import Goal, GoalReasoner, GoalType
from planner.task import ExecutionPlan, Task
from projects.project_manager import get_project_manager

logger = logging.getLogger(__name__)


def create_plan(goal: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
    """
    Decompose user goal into an ExecutionPlan following Planner Rules.

    Planner Rule:
    Never launch VS Code first!
    Sequence MUST ALWAYS be: Find Project -> Validate Project -> Open Project (code <path>).
    """
    if not goal or not goal.strip():
        return ExecutionPlan(goal=goal, tasks=[])

    raw_text = goal.strip()
    reasoner = GoalReasoner()
    detected_goal = reasoner.detect_goal(raw_text)
    pm = get_project_manager()

    logger.info("Goal Reasoner detected type=%s, target='%s'", detected_goal.type, detected_goal.target_project)

    # 1. GoalType: OPEN_PROJECT
    if detected_goal.type == GoalType.OPEN_PROJECT:
        target = detected_goal.target_project
        single, candidates = pm.find_project(target)

        if len(candidates) > 1 and not single:
            # Ambiguity handling — ask user for clarification
            lines = [f"{i+1}. {p['name']} ({p['framework']}) → {p['path']}" for i, p in enumerate(candidates[:5])]
            prompt_msg = f"I found {len(candidates)} matching projects:\n" + "\n".join(lines) + "\nWhich one would you like to open?"
            return ExecutionPlan(
                goal=raw_text,
                tasks=[
                    Task(tool="ai", action="chat", params={"text": prompt_msg})
                ]
            )

        if single:
            return ExecutionPlan(
                goal=raw_text,
                tasks=[
                    Task(tool="project", action="find", params={"name": single["name"]}),
                    Task(tool="vscode", action="open_project", params={"path": single["path"], "name": single["name"]}),
                ]
            )

        # Candidate fallback search
        return ExecutionPlan(
            goal=raw_text,
            tasks=[
                Task(tool="project", action="find", params={"name": target}),
                Task(tool="vscode", action="open_project", params={"name": target}),
            ]
        )

    # 2. GoalType: CONTINUE_PROJECT
    if detected_goal.type == GoalType.CONTINUE_PROJECT:
        target = detected_goal.target_project
        if target:
            single, candidates = pm.find_project(target)
            if single:
                return ExecutionPlan(
                    goal=raw_text,
                    tasks=[
                        Task(tool="project", action="find", params={"name": single["name"]}),
                        Task(tool="vscode", action="open_project", params={"path": single["path"]}),
                        Task(tool="developer", action="git_status", params={"path": single["path"]}),
                    ]
                )

        # Open most recent project
        return ExecutionPlan(
            goal=raw_text,
            tasks=[
                Task(tool="project", action="open_recent", params={}),
                Task(tool="vscode", action="open_recent", params={}),
                Task(tool="developer", action="git_status", params={}),
            ]
        )

    # 3. GoalType: DEVELOPER_WORKSPACE
    if detected_goal.type == GoalType.DEVELOPER_WORKSPACE:
        return ExecutionPlan(
            goal=raw_text,
            tasks=[
                Task(tool="project", action="open_recent", params={}),
                Task(tool="vscode", action="open_recent", params={}),
                Task(tool="developer", action="git_status", params={}),
                Task(tool="system", action="ram", params={}),
            ]
        )

    # Fallback to single task execution
    return ExecutionPlan(
        goal=raw_text,
        tasks=[Task(tool="ai", action="chat", params={"text": raw_text})]
    )
