"""
tools/developer_tool.py — Developer workflow automation (Git, Docker, Python, Virtual Environments).

Supports:
  - Git: git_status, git_commit, git_push, git_pull
  - Python / Virtualenvs: create_venv, activate_venv, pip_install, run_python
  - Docker: docker_ps, docker_logs, docker_compose_up
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def _run_subproc(cmd: list, cwd: Optional[str] = None, timeout: int = 15) -> ToolResult:
    """Safely execute developer command in subprocess."""
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or str(Path.home()),
        )
        output = res.stdout.strip()
        errors = res.stderr.strip()

        if res.returncode == 0:
            msg = output if output else f"Command '{' '.join(cmd)}' executed successfully."
            return ToolResult(success=True, message=msg, data={"output": output})
        return ToolResult(success=False, message=f"Command failed ({res.returncode}): {errors or output}")
    except Exception as e:
        return ToolResult(success=False, message=f"Execution error: {e}")


# ─── Git Operations ───────────────────────────────────────────────────

def git_status(path: str = "") -> ToolResult:
    """Run `git status` in current or specified project path."""
    target = str(Path(path).expanduser().resolve()) if path else str(Path.cwd())
    return _run_subproc(["git", "status", "-s"], cwd=target)


def git_commit(message: str = "Update", path: str = "") -> ToolResult:
    """Stage changes and commit with message."""
    target = str(Path(path).expanduser().resolve()) if path else str(Path.cwd())

    res_add = _run_subproc(["git", "add", "."], cwd=target)
    if not res_add.success:
        return res_add

    return _run_subproc(["git", "commit", "-m", message], cwd=target)


def git_push(branch: str = "", path: str = "") -> ToolResult:
    """Push local commits to git remote."""
    target = str(Path(path).expanduser().resolve()) if path else str(Path.cwd())
    cmd = ["git", "push"]
    if branch:
        cmd.extend(["origin", branch])
    return _run_subproc(cmd, cwd=target, timeout=30)


def git_pull(path: str = "") -> ToolResult:
    """Pull latest changes from git remote."""
    target = str(Path(path).expanduser().resolve()) if path else str(Path.cwd())
    return _run_subproc(["git", "pull"], cwd=target, timeout=30)


# ─── Python & Virtual Environment Operations ──────────────────────────

def create_venv(path: str = ".") -> ToolResult:
    """Create a virtual environment (venv) in target directory."""
    target_dir = Path(path).expanduser().resolve()
    venv_dir = target_dir / "venv"
    if venv_dir.exists():
        return ToolResult(success=True, message=f"Virtualenv already exists at {venv_dir}")

    return _run_subproc(["python3", "-m", "venv", str(venv_dir)], cwd=str(target_dir), timeout=30)


def activate_venv(path: str = ".") -> ToolResult:
    """Return instructions / env variables to activate venv."""
    target_dir = Path(path).expanduser().resolve()
    venv_bin = target_dir / "venv" / ("Scripts" if os.name == "nt" else "bin")
    if not venv_bin.exists():
        return ToolResult(success=False, message=f"No venv found at {target_dir}")

    act_script = venv_bin / ("activate.bat" if os.name == "nt" else "activate")
    return ToolResult(
        success=True,
        message=f"Virtual environment active at {venv_bin.parent}. To activate in shell: source {act_script}",
        data={"venv_path": str(venv_bin.parent)},
    )


def pip_install(packages: str, path: str = ".") -> ToolResult:
    """Install Python packages via pip."""
    if not packages:
        return ToolResult(success=False, message="No packages specified.")

    target_dir = Path(path).expanduser().resolve()
    python_bin = target_dir / "venv" / ("Scripts" if os.name == "nt" else "bin") / "python"
    if not python_bin.exists():
        python_bin = "python3"

    cmd = [str(python_bin), "-m", "pip", "install"] + packages.split()
    return _run_subproc(cmd, cwd=str(target_dir), timeout=60)


def run_python(script_path: str, args: str = "") -> ToolResult:
    """Run a python script."""
    s_path = Path(script_path).expanduser().resolve()
    if not s_path.exists():
        return ToolResult(success=False, message=f"Script not found: {script_path}")

    cmd = ["python3", str(s_path)]
    if args:
        cmd.extend(args.split())
    return _run_subproc(cmd, cwd=str(s_path.parent), timeout=30)


# ─── Docker Operations ────────────────────────────────────────────────

def docker_ps() -> ToolResult:
    """List running docker containers."""
    return _run_subproc(["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"])


def docker_logs(container_name: str) -> ToolResult:
    """Fetch logs for a docker container."""
    if not container_name:
        return ToolResult(success=False, message="Container name required.")
    return _run_subproc(["docker", "logs", "--tail", "50", container_name])


def docker_compose_up(path: str = ".") -> ToolResult:
    """Run docker-compose up -d in target project directory."""
    target_dir = str(Path(path).expanduser().resolve())
    return _run_subproc(["docker-compose", "up", "-d"], cwd=target_dir, timeout=60)


# ─── Router Handler ───────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route developer tool actions."""
    action = intent.action
    params = intent.params
    path = params.get("path", "")

    if action == "git_status":
        return git_status(path)
    elif action == "git_commit":
        return git_commit(params.get("message", "Auto-commit"), path)
    elif action == "git_push":
        return git_push(params.get("branch", ""), path)
    elif action == "git_pull":
        return git_pull(path)
    elif action == "create_venv":
        return create_venv(path)
    elif action == "activate_venv":
        return activate_venv(path)
    elif action == "pip_install":
        return pip_install(params.get("packages", "") or params.get("package", ""), path)
    elif action == "run_python":
        return run_python(params.get("script", "") or params.get("script_path", ""), params.get("args", ""))
    elif action == "docker_ps":
        return docker_ps()
    elif action == "docker_logs":
        return docker_logs(params.get("container", "") or params.get("name", ""))
    elif action == "docker_compose_up":
        return docker_compose_up(path)
    else:
        return ToolResult(success=False, message=f"Unknown developer action: {action}")
