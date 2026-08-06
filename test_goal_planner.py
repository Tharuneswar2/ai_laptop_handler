"""
test_goal_planner.py — Verification suite for Goal Reasoning, Planner, Project Manager & VS Code integration.

Tests exact success criteria commands:
  1. Open AI Laptop Handler project in VS Code
  2. Open OCR project
  3. Continue backend
  4. Continue yesterday's work
  5. Open my latest project
  6. Open FastAPI backend
  7. Open portfolio project
  8. Ambiguity resolution when multiple projects match query
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from brain.intent_parser import parse_intent
from planner.executor import execute_plan
from planner.planner import create_plan
from planner.reasoner import GoalReasoner, GoalType
from planner.task import ExecutionPlan
from projects.project_manager import get_project_manager
from router.tool_router import ToolResult
from tools import vscode_tool


class TestGoalPlanner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pm = get_project_manager()
        cls.curr_dir = str(Path(__file__).parent.resolve())
        # Register current project under name and aliases
        cls.pm.register_project(
            name="ai_laptop_handler",
            path=cls.curr_dir,
            aliases="ai laptop handler, nova, assistant, voice handler, laptop handler",
            framework="FastAPI",
        )

    def test_1_goal_reasoner_detection(self):
        """Test GoalReasoner correctly identifies OPEN_PROJECT and CONTINUE_PROJECT."""
        reasoner = GoalReasoner()

        g1 = reasoner.detect_goal("Open AI Laptop Handler project in VS Code")
        self.assertEqual(g1.type, GoalType.OPEN_PROJECT)
        self.assertIn("ai laptop handler", g1.target_project.lower())

        g2 = reasoner.detect_goal("Continue backend")
        self.assertEqual(g2.type, GoalType.CONTINUE_PROJECT)

        g3 = reasoner.detect_goal("Open my latest project")
        self.assertEqual(g3.type, GoalType.CONTINUE_PROJECT)

    def test_2_planner_sequence(self):
        """Test Planner creates (find_project -> open_project code <path>) sequence."""
        plan = create_plan("Open AI Laptop Handler project in VS Code")
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(plan.tasks[0].tool, "project")
        self.assertEqual(plan.tasks[1].tool, "vscode")
        self.assertEqual(plan.tasks[1].action, "open_project")
        self.assertIn("ai_laptop_handler", str(plan.tasks[1].params.get("name", "")) + str(plan.tasks[1].params.get("path", "")))

    def test_3_project_manager_fuzzy(self):
        """Test fuzzy search and alias matching in ProjectManager."""
        single1, candidates1 = self.pm.find_project("ai laptop handler")
        self.assertIsNotNone(single1)
        self.assertEqual(single1["name"], "ai_laptop_handler")

        single2, candidates2 = self.pm.find_project("nova")
        self.assertIsNotNone(single2)
        self.assertEqual(single2["name"], "ai_laptop_handler")

        single3, candidates3 = self.pm.find_project("assistant")
        self.assertIsNotNone(single3)
        self.assertEqual(single3["name"], "ai_laptop_handler")

    def test_4_ambiguity_handling(self):
        """Test ambiguity handling when multiple projects match ambiguous query."""
        mock_dir1 = Path.home() / "Projects" / "ambiguous_alpha"
        mock_dir2 = Path.home() / "Projects" / "ambiguous_beta"
        mock_dir1.mkdir(parents=True, exist_ok=True)
        mock_dir2.mkdir(parents=True, exist_ok=True)

        self.pm.register_project("ambiguous_alpha", str(mock_dir1), aliases="ambiguous project")
        self.pm.register_project("ambiguous_beta", str(mock_dir2), aliases="ambiguous project")

        single, candidates = self.pm.find_project("ambiguous project")
        self.assertIsNone(single)  # Ambiguous! Multiple matches for "ambiguous project"
        self.assertGreaterEqual(len(candidates), 2)

        # Plan for ambiguous query should return disambiguation prompt
        plan = create_plan("Open ambiguous project")
        res = execute_plan(plan)
        self.assertIn("I found", res.message)
        self.assertIn("matching projects", res.message)

    def test_5_vscode_direct_path_execution(self):
        """Test VS Code tool open_project validates path and passes path parameter."""
        res = vscode_tool.open_project(path=self.curr_dir)
        self.assertTrue(res.success)
        self.assertIn("ai_laptop_handler", res.message)

    def test_6_success_criteria_parse_intent(self):
        """Test all 7 user success criteria commands through parse_intent()."""
        commands = [
            "Open AI Laptop Handler project",
            "Open OCR project",
            "Continue backend",
            "Continue yesterday's work",
            "Open my latest project",
            "Open FastAPI backend",
            "Open portfolio project",
        ]
        for cmd in commands:
            parsed = parse_intent(cmd)
            self.assertIsInstance(parsed, ExecutionPlan, f"Failed to parse '{cmd}' as ExecutionPlan")
            self.assertGreaterEqual(len(parsed.tasks), 1)


if __name__ == "__main__":
    unittest.main()
