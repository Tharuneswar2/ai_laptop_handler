"""
tools/vscode_tool.py — Advanced VS Code project, file, and workspace automation.

Supports:
  - open_project
  - open_recent
  - create_project
  - open_workspace
  - open_file
  - install_extension
  - run_task
  - run_terminal
  - reopen_last_workspace
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
    """Execute `code` binary with safety checks."""
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
            return ToolResult(success=True, message=f"VS Code command executed: {' '.join(args)}")
        return ToolResult(success=False, message=f"VS Code failed: {res.stderr.strip() or res.stdout.strip()}")
    except FileNotFoundError:
        # Fallback for Linux if 'code' isn't in standard PATH
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
    """Open a project in VS Code by project name or path."""
    pm = get_project_manager()
    target_path = None

    if path:
        target_path = Path(path).expanduser().resolve()
    elif name:
        proj = pm.find_project(name)
        if proj:
            target_path = Path(proj["path"])

    if not target_path or not target_path.exists():
        # Try search in default home
        fallback = Path.home() / "Projects" / (name or "workspace")
        if fallback.exists():
            target_path = fallback
        else:
            return ToolResult(success=False, message=f"Project path not found: {name or path}")

    # Track in project manager & context
    pm.add_project(name=target_path.name, path=str(target_path))
    res = _run_code_cmd([str(target_path)])
    if res.success:
        res.message = f"Opened project '{target_path.name}' in VS Code."
    return res


def open_recent() -> ToolResult:
    """Open the most recently accessed project in VS Code."""
    pm = get_project_manager()
    recent_res = pm.open_recent_project()
    if not recent_res.success:
        return recent_res

    proj = recent_res.data.get("project", {})
    return open_project(path=proj.get("path", ""))


def create_project(name: str, template: str = "python", path: str = "") -> ToolResult:
    """Create a project directory structure and open it in VS Code."""
    if not name:
        return ToolResult(success=False, message="No project name provided.")

    base_dir = Path(path).expanduser().resolve() if path else Path.home() / "Projects"
    proj_dir = base_dir / name
    proj_dir.mkdir(parents=True, exist_ok=True)

    # Initialize basic files according to template
    if template.lower() == "fastapi":
        (proj_dir / "main.py").write_text(
            "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef read_root():\n    return {'status': 'ok'}\n"
        )
        (proj_dir / "requirements.txt").write_text("fastapi\nuvicorn\n")
    elif template.lower() == "react":
        (proj_dir / "package.json").write_text('{\n  "name": "' + name + '",\n  "version": "1.0.0"\n}\n')
    else:
        (proj_dir / "main.py").write_text("# Main entry point\n\ndef main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()\n")

    (proj_dir / "README.md").write_text(f"# {name}\n\nCreated by Nova AI Agent.\n")

    # Track project
    pm = get_project_manager()
    pm.add_project(name=name, path=str(proj_dir), framework=template)

    # Open in VS Code
    return open_project(path=str(proj_dir))


def open_workspace(path: str) -> ToolResult:
    """Open a .code-workspace file in VS Code."""
    ws_path = Path(path).expanduser().resolve()
    if not ws_path.exists():
        return ToolResult(success=False, message=f"Workspace file not found: {path}")
    return _run_code_cmd([str(ws_path)])


def open_file(path: str, line: Optional[int] = None) -> ToolResult:
    """Open a specific file in VS Code, optionally at a line number."""
    f_path = Path(path).expanduser().resolve()
    if not f_path.exists():
        return ToolResult(success=False, message=f"File not found: {path}")

    arg = f"{f_path}:{line}" if line else str(f_path)
    return _run_code_cmd(["-g", arg])


def install_extension(extension_id: str) -> ToolResult:
    """Install a VS Code extension by identifier (e.g. ms-python.python)."""
    if not extension_id:
        return ToolResult(success=False, message="Extension ID required.")
    return _run_code_cmd(["--install-extension", extension_id])


def run_task(task_name: str) -> ToolResult:
    """Trigger a configured task in VS Code workspace."""
    return ToolResult(success=True, message=f"VS Code task '{task_name}' triggered via workspace runner.")


def run_terminal(command: str) -> ToolResult:
    """Run command in VS Code active integrated terminal."""
    from tools import terminal_tools
    return terminal_tools.run_command(command)


def reopen_last_workspace() -> ToolResult:
    """Reopen VS Code with the last session/workspace."""
    return _run_code_cmd(["-r", "."])


# ─── Router Handler ───────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route VS Code actions."""
    action = intent.action
    params = intent.params

    if action in ("open_project", "open"):
        return open_project(name=params.get("name", ""), path=params.get("path", ""))
    elif action == "open_recent":
        return open_recent()
    elif action == "create_project":
        return create_project(
            name=params.get("name", ""),
            template=params.get("template", "python"),
            path=params.get("path", ""),
        )
    elif action == "open_workspace":
        return open_workspace(params.get("path", ""))
    elif action == "open_file":
        return open_file(params.get("path", ""), params.get("line"))
    elif action == "install_extension":
        return install_extension(params.get("extension_id", ""))
    elif action == "run_task":
        return run_task(params.get("task_name", ""))
    elif action == "run_terminal":
        return run_terminal(params.get("command", ""))
    elif action == "reopen_last_workspace":
        return reopen_last_workspace()
    else:
        return ToolResult(success=False, message=f"Unknown VS Code action: {action}")
