"""
tools/terminal_tools.py — Safe terminal command execution.

Only allows a strict allowlist of commands. Blocks all dangerous operations
including rm, sudo, pipes, redirects, and arbitrary shell execution.
"""

import logging
import os
import re
import subprocess

import config
from brain.intent_parser import Intent
from router.tool_router import ToolResult

logger = logging.getLogger(__name__)


def _is_command_allowed(command: str) -> bool:
    """
    Check if a command is in the allowlist and not blocked.

    Args:
        command: The command string to check.

    Returns:
        True if the command is safe to run.
    """
    cmd = command.strip()

    # Block dangerous patterns
    for pattern in config.BLOCKED_PATTERNS:
        if pattern in cmd:
            logger.warning("Blocked dangerous pattern '%s' in command: %s", pattern, cmd)
            return False

    # Block shell operators
    if any(op in cmd for op in ["|", ";", "&&", "||", ">", "<", "`", "$("]):
        logger.warning("Blocked shell operator in command: %s", cmd)
        return False

    # Check against allowlist (exact match or prefix match)
    for allowed in config.ALLOWED_TERMINAL_COMMANDS:
        if cmd == allowed or cmd.startswith(allowed + " "):
            return True

    # Also allow if just the base command is in the allowlist
    base_cmd = cmd.split()[0] if cmd.split() else ""
    simple_allowed = {c.split()[0] for c in config.ALLOWED_TERMINAL_COMMANDS}
    if base_cmd in simple_allowed and base_cmd not in ("git",):
        # For single-word commands like ls, pwd, df, du — allow with arguments
        return True

    return False


def _translate_windows_command(command: str) -> str:
    """Translate common POSIX commands to Windows cmd equivalents."""
    if not command.strip():
        return command

    mapping = {
        "ls": "dir",
        "pwd": "cd",
        "clear": "cls",
        "cat ": "type ",
        "mv ": "move ",
        "cp ": "copy ",
    }
    translated = command
    for src, dst in mapping.items():
        if translated == src.strip() or translated.startswith(src):
            translated = dst + translated[len(src):]
            break
    return translated


def run_command(command: str) -> ToolResult:
    """
    Execute an allowed terminal command and return its output.

    Args:
        command: The command to run (must be in the allowlist).

    Returns:
        ToolResult with stdout or error message.
    """
    if not command:
        return ToolResult(success=False, message="No command provided.")

    if os.name == "nt":
        command = _translate_windows_command(command)

    if not _is_command_allowed(command):
        return ToolResult(
            success=False,
            message=f"Command not allowed: '{command}'. Only safe commands are permitted.",
            data={"allowed": sorted(config.ALLOWED_TERMINAL_COMMANDS)},
        )

    try:
        if os.name == "nt":
            # Windows shell builtins (dir, ver, cls) require cmd.exe
            result = subprocess.run(
                ["cmd", "/c", command],
                capture_output=True,
                text=True,
                timeout=config.TERMINAL_TIMEOUT,
                cwd=str(config.PROJECT_ROOT),
            )
        else:
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=config.TERMINAL_TIMEOUT,
                cwd=str(config.PROJECT_ROOT),
            )

        output = result.stdout.strip()
        errors = result.stderr.strip()

        if result.returncode == 0:
            display = output if output else "(no output)"
            logger.info("Command '%s' succeeded: %s", command, display[:100])
            return ToolResult(success=True, message=f"$ {command}\n{display}")
        else:
            msg = errors if errors else f"Command exited with code {result.returncode}"
            return ToolResult(success=False, message=f"$ {command}\nError: {msg}")

    except subprocess.TimeoutExpired:
        return ToolResult(success=False, message=f"Command timed out after {config.TERMINAL_TIMEOUT}s: {command}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to run command: {e}")


def list_allowed_commands() -> ToolResult:
    """List all commands that are allowed to be executed."""
    cmds = sorted(config.ALLOWED_TERMINAL_COMMANDS)
    cmd_list = "\n".join(f"  • {c}" for c in cmds)
    return ToolResult(
        success=True,
        message=f"Allowed commands:\n{cmd_list}",
        data={"commands": cmds},
    )


# ─── Handler ──────────────────────────────────────────────────────────

def handle(intent: Intent) -> ToolResult:
    """Route terminal tool actions."""
    action = intent.action
    params = intent.params

    if action == "run":
        return run_command(params.get("command", ""))
    elif action == "list_allowed":
        return list_allowed_commands()
    else:
        return ToolResult(success=False, message=f"Unknown terminal action: {action}")
