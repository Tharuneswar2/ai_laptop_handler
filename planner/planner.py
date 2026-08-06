"""
planner/planner.py — Enhanced Goal Decomposition & Compound Command Planner.

Integrates Goal Reasoner, Project Manager fuzzy lookups, destination app selection
(vscode, explorer, terminal), and multi-clause compound command splitting (e.g. "open chrome and search fastapi on youtube").
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from planner.reasoner import Goal, GoalReasoner, GoalType
from planner.task import ExecutionPlan, Task
from projects.project_manager import get_project_manager

logger = logging.getLogger(__name__)


def _split_compound_command(text: str) -> List[str]:
    """
    Split text on compound clause separators ('and then', 'then', ', then', 'and').
    Avoids splitting single phrases like 'open vs code' or 'search python and java'.
    """
    raw = text.strip()
    # Check explicitly for strong multi-task separators
    separators = [r"\s+and\s+then\s+", r"\,\s+then\s+", r"\s+then\s+", r"\s+and\s+"]

    # Only split on 'and' if it connects distinct action verbs (open, search, create, run, check, find)
    action_verbs = r"(open|search|create|make|run|check|show|delete|find|start|stop|lock|switch|focus|close)"

    clauses = [raw]
    for sep in [r"\s+and\s+then\s+", r"\,\s+then\s+", r"\s+then\s+"]:
        new_clauses = []
        for c in clauses:
            parts = re.split(sep, c, flags=re.IGNORECASE)
            new_clauses.extend(p.strip() for p in parts if p.strip())
        clauses = new_clauses

    if len(clauses) == 1 and " and " in raw.lower():
        pattern = r"\s+and\s+(?=" + action_verbs + r"\b)"
        parts = re.split(pattern, raw, flags=re.IGNORECASE)
        if len(parts) > 1:
            clauses = [p.strip() for p in parts if p.strip()]

    return clauses


def _plan_single_goal(goal: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
    """Plan a single clause goal."""
    raw_text = goal.strip()
    reasoner = GoalReasoner()
    detected_goal = reasoner.detect_goal(raw_text)
    pm = get_project_manager()

    logger.info("Goal Reasoner detected type=%s, target='%s', app='%s'", detected_goal.type, detected_goal.target_project, detected_goal.target_app)

    # If reasoner returned SINGLE_ACTION, fallback to direct Intent parsing
    if detected_goal.type == GoalType.SINGLE_ACTION:
        from brain.intent_parser import Intent
        from brain.llm import get_provider
        provider = get_provider()
        json_str = provider.generate(raw_text)
        intent = Intent.from_json(json_str, raw_text)
        return ExecutionPlan(
            goal=raw_text,
            tasks=[Task(tool=intent.tool, action=intent.action, params=intent.params)]
        )

    # Destination app mapping for OPEN_PROJECT
    app_tool_map = {
        "explorer": ("app", "open_folder"),
        "terminal": ("app", "open_terminal"),
        "vscode": ("vscode", "open_project"),
    }
    target_tool, target_action = app_tool_map.get(detected_goal.target_app, ("vscode", "open_project"))

    # 1. GoalType: OPEN_PROJECT
    if detected_goal.type == GoalType.OPEN_PROJECT:
        target = detected_goal.target_project
        single, candidates = pm.find_project(target)

        if len(candidates) > 1 and not single:
            lines = [f"{i+1}. {p['name']} ({p['framework']}) → {p['path']}" for i, p in enumerate(candidates[:5])]
            prompt_msg = f"I found {len(candidates)} matching projects:\n" + "\n".join(lines) + "\nWhich one would you like to open?"
            return ExecutionPlan(
                goal=raw_text,
                tasks=[Task(tool="ai", action="chat", params={"text": prompt_msg})]
            )

        if single:
            return ExecutionPlan(
                goal=raw_text,
                tasks=[
                    Task(tool="project", action="find", params={"name": single["name"]}),
                    Task(tool=target_tool, action=target_action, params={"path": single["path"], "name": single["name"]}),
                ]
            )

        return ExecutionPlan(
            goal=raw_text,
            tasks=[
                Task(tool="project", action="find", params={"name": target}),
                Task(tool=target_tool, action=target_action, params={"name": target}),
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
                        Task(tool=target_tool, action=target_action, params={"path": single["path"]}),
                        Task(tool="developer", action="git_status", params={"path": single["path"]}),
                    ]
                )

        return ExecutionPlan(
            goal=raw_text,
            tasks=[
                Task(tool="project", action="open_recent", params={}),
                Task(tool=target_tool, action="open_recent" if target_tool == "vscode" else target_action, params={}),
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

    return ExecutionPlan(
        goal=raw_text,
        tasks=[Task(tool="ai", action="chat", params={"text": raw_text})]
    )


def create_plan(goal: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
    """
    Decompose user goal (or compound goals connected with 'and'/'then') into an ExecutionPlan.
    """
    if not goal or not goal.strip():
        return ExecutionPlan(goal=goal, tasks=[])

    raw_text = goal.strip()

    # Strip prefix 'hey nova, ' or 'nova, '
    cleaned_raw = re.sub(r"^(hey\s+nova,?\s*|nova,?\s*)", "", raw_text, flags=re.IGNORECASE).strip()

    clauses = _split_compound_command(cleaned_raw)

    if len(clauses) == 1:
        return _plan_single_goal(clauses[0], context)

    # Multi-clause compound command
    all_tasks = []
    for clause in clauses:
        sub_plan = _plan_single_goal(clause, context)
        all_tasks.extend(sub_plan.tasks)

    return ExecutionPlan(goal=raw_text, tasks=all_tasks)
