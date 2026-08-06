"""
tools/vscode_tool.py — Upgraded VS Code Automation Tool.

Executes `code <project_path>` directly to open project folders in VS Code.
Supports:
  - open_project(path)
  - open_recent()
  - open_workspace(path)
  - create_workspace(path)
  - reopen_last_workspace()
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from brain.intent_parser import Intent
from projects.project_manager import get_project_manager
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def _run_code_cmd(args: list, cwd: Optional[str] = None) -> ToolResult:
    """Execute `code` binary with target arguments."""
    executable = "code.cmd" if os.name == "nt" else "code"
    cmd = [executable] + args

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
        if res.returncode == 0:
            return ToolResult(success=True, message=f"VS Code opened target: {' '.join(args)}")
        return ToolResult(success=False, message=f"VS Code failed: {res.stderr.strip() or res.stdout.strip()}")
    except FileNotFoundError:
        # Fallback for Linux if 'code' isn't in PATH
        try:
            res = subprocess.run(
                ["/usr/bin/code"] + args,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=cwd,
            )
            if res.returncode == 0:
                return ToolResult(success=True, message=f"Opened VS Code: {' '.join(args)}")
        except Exception:
            pass
        return ToolResult(success=False, message="VS Code executable ('code') not found in PATH.")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to run VS Code: {e}")


def open_project(name: str = "", path: str = "") -> ToolResult:
    """
    Open a project directory directly in VS Code via `code <path>`.
    Planner Rule: Always validate project path before launching!
    """
    pm = get_project_manager()
    target_path = None

    if path:
        target_path = Path(path).expanduser().resolve()
    elif name:
        single, candidates = pm.find_project(name)
        if single:
            target_path = Path(single["path"])
        elif len(candidates) > 1:
            lines = [f"{i+1}. {p['name']} ({p['framework']}) → {p['path']}" for i, p in enumerate(candidates[:5])]
            msg = f"I found {len(candidates)} matching projects:\n" + "\n".join(lines) + "\nWhich one would you like to open?"
            return ToolResult(
                success=True,
                message=msg,
                data={"ambiguous": True, "candidates": candidates[:5]},
            )

    if not target_path or not target_path.exists():
        return ToolResult(success=False, message=f"Cannot open VS Code: project path not found for '{name or path}'.")

    # Update project last_opened timestamp and Memory context
    pm.touch_project(target_path.name)
    try:
        from brain.memory import Memory
        Memory().update_context("last_project", target_path.name)
        Memory().update_context("last_opened_project", str(target_path))
    except Exception:
        pass

    # Launch VS Code with project folder path!
    res = _run_code_cmd([str(target_path)])
    if res.success:
        res.message = f"Opened project '{target_path.name}' in VS Code (`code {target_path}`)."
    return res


def open_recent() -> ToolResult:
    """Open the most recently accessed project in VS Code."""
    pm = get_project_manager()
    recent_res = pm.open_recent_project()
    if not recent_res.success:
        return recent_res

    proj = recent_res.data.get("project", {})
    return open_project(path=proj.get("path", ""))


def create_workspace(name: str = "workspace", path: str = "") -> ToolResult:
    """Create a new .code-workspace file and open it."""
    base_dir = Path(path).expanduser().resolve() if path else Path.home() / "Projects"
    base_dir.mkdir(parents=True, exist_ok=True)
    ws_file = base_dir / f"{name}.code-workspace"

    content = '{\n  "folders": [\n    {\n      "path": "."\n    }\n  ]\n}\n'
    ws_file.write_text(content, encoding="utf-8")

    return _run_code_cmd([str(ws_file)])


def open_workspace(path: str) -> ToolResult:
    """Open a .code-workspace file in VS Code."""
    ws_path = Path(path).expanduser().resolve()
    if not ws_path.exists():
        return ToolResult(success=False, message=f"Workspace file not found: {path}")
    return _run_code_cmd([str(ws_path)])


def reopen_last_workspace() -> ToolResult:
    """Reopen VS Code with the last active workspace/session."""
    pm = get_project_manager()
    recent_res = pm.open_recent_project()
    if recent_res.success:
        proj = recent_res.data.get("project", {})
        return open_project(path=proj.get("path", ""))
    return _run_code_cmd(["-r", "."])


# ─── Router Handler ───────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route VS Code actions."""
    action = intent.action
    params = intent.params
    name = params.get("name", "") or params.get("project_name", "")
    path = params.get("path", "") or params.get("project_path", "")

    if action in ("open_project", "open"):
        return open_project(name=name, path=path)
    elif action in ("open_recent", "open_latest_project"):
        return open_recent()
    elif action in ("open_workspace", "create_workspace"):
        if action == "create_workspace":
            return create_workspace(name=name or "workspace", path=path)
        return open_workspace(path=path)
    elif action == "reopen_last_workspace":
        return reopen_last_workspace()
    else:
        # Default fallback: open project if path/name present, else open recent
        if name or path:
            return open_project(name=name, path=path)
        return open_recent()
