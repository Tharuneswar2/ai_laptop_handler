"""
test_sample_commands.py — Comprehensive test suite verifying all 80+ sample commands.

Ensures proper classification into Intent vs ExecutionPlan, negative guards,
and compound plan splitting across all categories.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from brain.intent_parser import parse_intent
from planner.planner import create_plan
from planner.task import ExecutionPlan
from projects.project_manager import get_project_manager


class TestAllSampleCommands(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pm = get_project_manager()
        cls.curr_dir = str(Path(__file__).parent.resolve())
        cls.pm.register_project(
            name="ai_laptop_handler",
            path=cls.curr_dir,
            aliases="ai laptop handler, nova, assistant, voice handler",
            framework="FastAPI",
        )

    def test_project_and_vscode_commands(self):
        """Test Developer / Project / VS Code Workflow commands."""
        cmds = [
            "Hey Nova, open my AI Laptop Handler project in VS Code.",
            "Hey Nova, open my backend.",
            "Hey Nova, open the OCR project.",
            "Hey Nova, open the last project.",
            "Hey Nova, open the latest project.",
            "Hey Nova, continue yesterday’s work.",
            "Hey Nova, start working.",
            "Hey Nova, open the portfolio project.",
        ]
        for cmd in cmds:
            res = parse_intent(cmd)
            self.assertIsInstance(res, ExecutionPlan, f"Failed for '{cmd}'")

    def test_file_commands(self):
        """Test File & Folder operations."""
        cmds = [
            ("Hey Nova, create a folder called Internship.", "file"),
            ("Hey Nova, create a new folder in Downloads called MCA.", "file"),
            ("Hey Nova, create a file called notes.txt.", "file"),
            ("Hey Nova, rename notes.txt to exam-notes.txt.", "file"),
            ("Hey Nova, move exam-notes.txt to Documents.", "file"),
            ("Hey Nova, search for my resume.", "file"),
            ("Hey Nova, find the newest PDF.", "file"),
            ("Hey Nova, open the newest PDF.", "file"),
            ("Hey Nova, clean Downloads folder.", "file"),
            ("Hey Nova, archive the screenshots folder.", "file"),
            ("Hey Nova, delete the test folder.", "file"),
            ("Hey Nova, copy this file to Documents.", "file"),
            ("Hey Nova, unzip the project archive.", "file"),
            ("Hey Nova, find duplicate images.", "file"),
        ]
        for cmd, expected_tool in cmds:
            res = parse_intent(cmd)
            tool = res.tasks[0].tool if isinstance(res, ExecutionPlan) else res.tool
            self.assertEqual(tool, expected_tool, f"Failed for '{cmd}' (got {tool})")

    def test_browser_commands(self):
        """Test Browser operations and YouTube searches."""
        cmds = [
            ("Hey Nova, open Chrome.", "app"),
            ("Hey Nova, open Firefox.", "app"),
            ("Hey Nova, search FastAPI tutorial.", "browser"),
            ("Hey Nova, search FastAPI tutorial on YouTube.", "browser"),
            ("Hey Nova, open GitHub.", "browser"),
            ("Hey Nova, open Google.", "browser"),
            ("Hey Nova, search Python project ideas.", "browser"),
            ("Hey Nova, search latest Python release.", "browser"),
            ("Hey Nova, open FastAPI documentation.", "browser"),
            ("Hey Nova, open the first result for Python asyncio.", "browser"),
            ("Hey Nova, bookmark this page.", "browser"),
            ("Hey Nova, close this tab.", "browser"),
        ]
        for cmd, expected_tool in cmds:
            res = parse_intent(cmd)
            tool = res.tasks[0].tool if isinstance(res, ExecutionPlan) else res.tool
            self.assertEqual(tool, expected_tool, f"Failed for '{cmd}' (got {tool})")

    def test_system_commands(self):
        """Test System info and desktop control commands."""
        cmds = [
            ("Hey Nova, check battery status.", "system"),
            ("Hey Nova, show RAM usage.", "system"),
            ("Hey Nova, check CPU usage.", "system"),
            ("Hey Nova, show disk usage.", "system"),
            ("Hey Nova, how much disk space is left?", "system"),
            ("Hey Nova, take a screenshot.", "system"),
            ("Hey Nova, lock the screen.", "system"),
            ("Hey Nova, set volume to 50.", "system"),
            ("Hey Nova, increase brightness.", "system"),
            ("Hey Nova, decrease brightness.", "system"),
            ("Hey Nova, show running processes.", "app"),
        ]
        for cmd, expected_tool in cmds:
            res = parse_intent(cmd)
            tool = res.tasks[0].tool if isinstance(res, ExecutionPlan) else res.tool
            self.assertEqual(tool, expected_tool, f"Failed for '{cmd}' (got {tool})")

    def test_terminal_developer_commands(self):
        """Test Terminal and Developer tools commands."""
        cmds = [
            ("Hey Nova, open terminal and run python --version.", "terminal"),
            ("Hey Nova, run git status.", "developer"),
            ("Hey Nova, show git log.", "developer"),
            ("Hey Nova, run ls.", "terminal"),
            ("Hey Nova, run pwd.", "terminal"),
            ("Hey Nova, run df.", "terminal"),
            ("Hey Nova, run du.", "terminal"),
            ("Hey Nova, run whoami.", "terminal"),
            ("Hey Nova, run uptime.", "terminal"),
            ("Hey Nova, install dependencies for this project.", "developer"),
            ("Hey Nova, create a virtual environment.", "developer"),
            ("Hey Nova, activate the virtual environment.", "developer"),
            ("Hey Nova, run the backend server.", "developer"),
            ("Hey Nova, pull the latest changes.", "developer"),
            ("Hey Nova, commit the changes.", "developer"),
            ("Hey Nova, push to GitHub.", "developer"),
        ]
        for cmd, expected_tool in cmds:
            res = parse_intent(cmd)
            tool = res.tasks[0].tool if isinstance(res, ExecutionPlan) else res.tool
            self.assertEqual(tool, expected_tool, f"Failed for '{cmd}' (got {tool})")

    def test_compound_multi_intent_commands(self):
        """Test multi-intent compound commands splitting into ExecutionPlan tasks."""
        compound_cmds = [
            ("Hey Nova, open my backend and run it.", 2),
            ("Hey Nova, open VS Code and create a folder called Internship.", 2),
            ("Hey Nova, open Chrome and search FastAPI tutorial on YouTube.", 2),
            ("Hey Nova, start working and open the last project workspace.", 4),
            ("Hey Nova, check system info and then open my project.", 3),
        ]
        for cmd, min_tasks in compound_cmds:
            res = parse_intent(cmd)
            self.assertIsInstance(res, ExecutionPlan, f"Failed compound split for '{cmd}'")
            self.assertGreaterEqual(len(res.tasks), min_tasks, f"Insufficient tasks for '{cmd}' (got {len(res.tasks)})")


if __name__ == "__main__":
    unittest.main()
