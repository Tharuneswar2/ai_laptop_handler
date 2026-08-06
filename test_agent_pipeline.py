"""
test_agent_pipeline.py — Comprehensive Verification Suite for AI Desktop Agent Upgrade.

Tests:
  1. Multi-step Goal Decomposition & Execution Plan Generation
  2. Sequential Plan Executor
  3. Project Database Manager & Framework Scanner
  4. Context Reference Resolver ("it", "last PDF", "my backend", "run it again")
  5. VS Code Tool Integration
  6. Developer Workflow Tools (Git, Python, Virtualenvs)
  7. Desktop State Tracker
  8. Safety Gating and Dangerous Action Confirmation
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from brain.intent_parser import Intent, parse_intent, requires_confirmation
from brain.memory import Memory
from desktop.desktop_manager import get_desktop_state, focus_app
from planner.executor import execute_plan
from planner.planner import create_plan
from planner.task import ExecutionPlan, Task
from projects.project_manager import get_project_manager
from router.tool_router import route, ToolResult
from tools import vscode_tool, developer_tool, extended_tools, file_tools


class TestAIDesktopAgent(unittest.TestCase):

    def setUp(self):
        self.memory = Memory()

    def test_1_goal_planner(self):
        """Test multi-step goal plan generation from templates."""
        plan1 = create_plan("Start working")
        self.assertIsInstance(plan1, ExecutionPlan)
        self.assertFalse(plan1.is_empty)
        self.assertGreaterEqual(len(plan1.tasks), 3)
        self.assertEqual(plan1.tasks[0].tool, "project")

        plan2 = create_plan("Setup FastAPI project")
        self.assertIsInstance(plan2, ExecutionPlan)
        self.assertGreaterEqual(len(plan2.tasks), 4)

        plan3 = create_plan("Open VS Code and create a folder called Internship")
        self.assertIsInstance(plan3, ExecutionPlan)
        self.assertEqual(plan3.tasks[0].action, "create_folder")
        self.assertEqual(plan3.tasks[1].tool, "vscode")

    def test_2_plan_executor(self):
        """Test executing an ExecutionPlan sequentially."""
        plan = ExecutionPlan(
            goal="Test execution sequence",
            tasks=[
                Task(tool="system", action="ram", params={}),
                Task(tool="system", action="cpu", params={}),
            ]
        )
        res = execute_plan(plan)
        self.assertTrue(res.success)
        self.assertIn("Successfully executed goal", res.message)

    def test_3_project_manager(self):
        """Test project creation, framework detection, and scanning."""
        pm = get_project_manager()
        # Add current project
        res_add = pm.add_project(name="ai_laptop_handler", path=str(Path.cwd()), tags="ai, backend")
        self.assertTrue(res_add.success)

        # Find project
        found = pm.find_project("ai_laptop_handler")
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "ai_laptop_handler")
        self.assertIn(found["framework"], ("Python", "FastAPI"))

    def test_4_context_reference_resolver(self):
        """Test anaphoric pronoun resolution in Memory."""
        mem = Memory()
        mem.update_context("last_app", "chrome")
        mem.update_context("last_project", "ai_laptop_handler")
        mem.update_context("last_command", "python3 main.py --text")

        res_open_it = mem.resolve_reference("open it")
        self.assertEqual(res_open_it, "open ai_laptop_handler")

        res_close_it = mem.resolve_reference("close it")
        self.assertEqual(res_close_it, "close chrome")

        res_run_again = mem.resolve_reference("run it again")
        self.assertEqual(res_run_again, "python3 main.py --text")

        res_backend = mem.resolve_reference("open my backend")
        self.assertEqual(res_backend, "open project backend")

    def test_5_vscode_tool(self):
        """Test VS Code tool routing."""
        intent = Intent(tool="vscode", action="open_recent", params={})
        res = route(intent)
        self.assertIsInstance(res, ToolResult)

    def test_6_developer_tool(self):
        """Test developer tool git status and venv checking."""
        intent_git = Intent(tool="developer", action="git_status", params={"path": str(Path.cwd())})
        res_git = route(intent_git)
        self.assertIsInstance(res_git, ToolResult)

        intent_venv = Intent(tool="developer", action="activate_venv", params={"path": str(Path.cwd())})
        res_venv = route(intent_venv)
        self.assertIsInstance(res_venv, ToolResult)

    def test_7_desktop_state_manager(self):
        """Test desktop window focus & app tracking."""
        state = get_desktop_state()
        state.record_app_launch("chrome")
        self.assertEqual(state.focused_app, "chrome")
        self.assertIn("chrome", state.opened_apps)

        intent = Intent(tool="desktop", action="focus_app", params={"app_name": "chrome"})
        res = route(intent)
        self.assertTrue(res.success)

    def test_8_safety_gating(self):
        """Test confirmation check for dangerous operations."""
        intent_del = Intent(tool="file", action="delete", params={"path": "/tmp/test.txt"})
        self.assertTrue(requires_confirmation(intent_del))

        intent_safe = Intent(tool="system", action="ram", params={})
        self.assertFalse(requires_confirmation(intent_safe))


if __name__ == "__main__":
    unittest.main()
