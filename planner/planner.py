"""
planner/planner.py — Goal decomposition and plan generator.

Transforms high-level user goals into structured ExecutionPlans composed of atomic Tasks.
Uses rule-based goal templates for fast execution of common workflows, with LLM fallback
for complex or unscripted user goals.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from planner.task import ExecutionPlan, Task

logger = logging.getLogger(__name__)


# ─── System Prompt for Dynamic Goal Planning ─────────────────────────

PLANNER_SYSTEM_PROMPT = """You are the AI Planner for Nova, an intelligent AI Desktop Agent.
Your job is to break down high-level user goals into a sequence of safe, structured atomic tool tasks.

Available Tools & Actions:
- project: {"action": "find"|"open_recent"|"create"|"list", "params": {"name": str, ...}}
- vscode: {"action": "open_project"|"open_file"|"create_project"|"open_workspace"|"run_terminal"|"install_extension", "params": {...}}
- developer: {"action": "git_status"|"git_commit"|"git_push"|"git_pull"|"create_venv"|"activate_venv"|"pip_install"|"run_python"|"docker_ps"|"docker_logs"|"docker_compose_up", "params": {...}}
- terminal: {"action": "run", "params": {"command": str}}
- file: {"action": "create_folder"|"create_file"|"move"|"rename"|"search"|"clean_downloads"|"archive_downloads"|"open_latest", "params": {...}}
- browser: {"action": "open_url"|"google_search"|"youtube_search"|"open_doc"|"watch_tutorial", "params": {...}}
- app: {"action": "open"|"close"|"list", "params": {"app_name": str}}
- system: {"action": "cpu"|"ram"|"disk"|"battery"|"screenshot", "params": {}}
- desktop: {"action": "focus_app"|"restore_session"|"minimize"|"maximize", "params": {...}}

Rules:
1. Return ONLY a JSON list of task objects. No explanation text, markdown, or commentary.
2. Order tasks logically so prerequisites execute first.
3. Every task must specify valid "tool", "action", and "params".

Example Input: "Start working on backend"
Example Output:
[
  {"tool": "project", "action": "find", "params": {"name": "backend"}},
  {"tool": "vscode", "action": "open_project", "params": {"name": "backend"}},
  {"tool": "developer", "action": "activate_venv", "params": {"path": "backend"}},
  {"tool": "terminal", "action": "run", "params": {"command": "uvicorn main:app --reload"}}
]
"""


# ─── Template Goal Generators ─────────────────────────────────────────

def _build_template_plan(goal: str, normalized_text: str) -> Optional[ExecutionPlan]:
    """
    Check if normalized text matches known developer/system goal templates.
    Returns an ExecutionPlan if matched, or None to fall through to LLM.
    """
    text = normalized_text.lower().strip()

    # 1. Goal: "Start working" / "Prepare for coding" / "Start coding"
    if re.search(r"\b(start working|prepare for coding|start coding|coding mode)\b", text):
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="project", action="open_recent", params={}),
                Task(tool="vscode", action="reopen_last_workspace", params={}),
                Task(tool="developer", action="git_status", params={}),
                Task(tool="system", action="ram", params={}),
            ]
        )

    # 2. Goal: "Continue my project" / "Continue yesterday's work" / "Continue project"
    if re.search(r"\b(continue (my |yesterday's )?work|continue (my |the )?project|continue working)\b", text):
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="project", action="open_recent", params={}),
                Task(tool="vscode", action="open_recent", params={}),
                Task(tool="developer", action="git_status", params={}),
            ]
        )

    # 3. Goal: "Setup FastAPI project" / "Create FastAPI project"
    m_fastapi = re.search(r"\b(setup|create|build|init)\s+(fastapi\s+project|fastapi\s+backend)\b", text)
    if m_fastapi:
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="file", action="create_folder", params={"path": "~/Projects/fastapi_backend"}),
                Task(tool="developer", action="create_venv", params={"path": "~/Projects/fastapi_backend"}),
                Task(tool="vscode", action="open_project", params={"path": "~/Projects/fastapi_backend"}),
                Task(tool="file", action="create_file", params={"path": "~/Projects/fastapi_backend/main.py"}),
                Task(tool="developer", action="pip_install", params={"packages": "fastapi uvicorn", "path": "~/Projects/fastapi_backend"}),
            ]
        )

    # 4. Goal: "Prepare Python environment" / "Setup python env"
    m_python_env = re.search(r"\b(prepare|setup|create)\s+python\s+(environment|env|venv)\b", text)
    if m_python_env:
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="developer", action="create_venv", params={"path": "."}),
                Task(tool="developer", action="activate_venv", params={"path": "."}),
                Task(tool="terminal", action="run", params={"command": "python --version"}),
            ]
        )

    # 5. Goal: "Run backend" / "Start backend"
    if re.search(r"\b(start|run|launch)\s+(my\s+)?backend\b", text):
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="project", action="find", params={"name": "backend"}),
                Task(tool="vscode", action="open_project", params={"name": "backend"}),
                Task(tool="developer", action="activate_venv", params={"path": "backend"}),
                Task(tool="terminal", action="run", params={"command": "uvicorn main:app --reload"}),
            ]
        )

    # 6. Goal: "Deploy backend" / "Push latest changes"
    if re.search(r"\b(push (latest )?changes|deploy (the )?backend|deploy project)\b", text):
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="developer", action="git_status", params={}),
                Task(tool="developer", action="git_commit", params={"message": "Auto-commit: deployment updates"}),
                Task(tool="developer", action="git_push", params={}),
            ]
        )

    # 7. Goal: "Build Docker image" / "Docker compose up"
    if re.search(r"\b(build docker image|run docker|docker compose up)\b", text):
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="developer", action="docker_ps", params={}),
                Task(tool="developer", action="docker_compose_up", params={}),
            ]
        )

    # 8. Goal: "Clean Downloads folder" / "Archive Downloads"
    if re.search(r"\b(clean downloads( folder)?|archive downloads)\b", text):
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="file", action="clean_downloads", params={}),
                Task(tool="file", action="archive_downloads", params={}),
            ]
        )

    # 9. Goal: "Open VS Code and create a folder called X"
    m_vscode_folder = re.search(r"\bopen (?:vs code|vscode)\s+(?:and|then)\s+create\s+(?:a\s+)?folder\s+(?:called|named)\s+([a-zA-Z0-9_-]+)\b", text)
    if m_vscode_folder:
        folder_name = m_vscode_folder.group(1).strip()
        target_path = f"~/Projects/{folder_name}"
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="file", action="create_folder", params={"path": target_path}),
                Task(tool="vscode", action="open_project", params={"path": target_path}),
            ]
        )

    # 10. Goal: "Open FastAPI documentation" / "Open Python docs"
    m_doc = re.search(r"\bopen\s+([a-zA-Z0-9_. -]+)\s+(documentation|docs|official docs)\b", text)
    if m_doc:
        doc_name = m_doc.group(1).strip()
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="browser", action="open_doc", params={"topic": doc_name}),
            ]
        )

    # 11. Goal: "Watch X tutorial"
    m_tut = re.search(r"\bwatch\s+([a-zA-Z0-9_. -]+)\s+tutorial\b", text)
    if m_tut:
        topic = m_tut.group(1).strip()
        return ExecutionPlan(
            goal=goal,
            tasks=[
                Task(tool="browser", action="watch_tutorial", params={"topic": topic}),
            ]
        )

    return None


# ─── LLM Planner ──────────────────────────────────────────────────────

def create_plan(goal: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
    """
    Decompose a user goal into an ExecutionPlan.

    Args:
        goal: Raw user request (e.g. "Start working on OCR project").
        context: Optional dictionary of current context/memory references.

    Returns:
        ExecutionPlan with tasks ready for execution.
    """
    if not goal or not goal.strip():
        return ExecutionPlan(goal=goal, tasks=[])

    raw_text = goal.strip()

    # 1. Try template goals first (fast, deterministic)
    template_plan = _build_template_plan(goal, raw_text)
    if template_plan:
        logger.info("Generated plan from template for goal '%s': %d tasks", goal, len(template_plan.tasks))
        return template_plan

    # 2. Use LLM provider for complex / novel goal planning
    try:
        from brain.llm import get_provider
        provider = get_provider()

        prompt = f"{PLANNER_SYSTEM_PROMPT}\nUser Goal: \"{raw_text}\"\nContext: {json.dumps(context or {})}\nResponse JSON:"
        raw_json = provider.generate(prompt)

        # Parse LLM JSON output
        cleaned = raw_json.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        task_dicts = json.loads(cleaned)
        if isinstance(task_dicts, list) and len(task_dicts) > 0:
            tasks = []
            for item in task_dicts:
                if isinstance(item, dict) and "tool" in item and "action" in item:
                    tasks.append(Task.from_dict(item))
            if tasks:
                logger.info("Generated dynamic LLM plan for goal '%s': %d tasks", goal, len(tasks))
                return ExecutionPlan(goal=goal, tasks=tasks, raw_response=raw_json)

    except Exception as e:
        logger.warning("LLM goal planning failed/skipped (%s). Creating fallback single task.", e)

    # 3. Fallback: single task execution plan
    return ExecutionPlan(
        goal=goal,
        tasks=[Task(tool="ai", action="chat", params={"text": raw_text})]
    )
