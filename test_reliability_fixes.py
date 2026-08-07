"""Regression tests for routing and AI-storage safety boundaries."""

import unittest
from pathlib import Path

import config
from brain.intent_parser import Intent, parse_intent
from projects.project_manager import get_project_manager
from tools import file_tools
from tools.app_tools import _find_installed_app, _normalize_app_name
from tools.terminal_tools import run_command


class ReliabilityFixTests(unittest.TestCase):
    def test_direct_desktop_commands_bypass_planning(self):
        cases = {
            "open settings": ("app", "open", "settings"),
            "open downloads folder": ("app", "open_folder", None),
            "show running apps": ("app", "list", None),
            "what are the present running apps": ("app", "list", None),
            "close VS Code": ("app", "close", "vs code"),
            "open chrome": ("app", "open", "chrome"),
        }
        for command, (tool, action, app_name) in cases.items():
            with self.subTest(command=command):
                intent = parse_intent(command)
                self.assertIsInstance(intent, Intent)
                self.assertEqual((intent.tool, intent.action), (tool, action))
                if app_name:
                    self.assertEqual(intent.params["app_name"], app_name)

    def test_spoken_app_aliases_resolve_to_known_processes(self):
        self.assertEqual(_normalize_app_name("the BS4 vs code"), "vs code")
        self.assertEqual(_normalize_app_name("the anti gravity"), "anti gravity")

    def test_file_creation_defaults_to_ai_storage(self):
        target_name = "reliability_test_folder"
        target = config.AI_STORAGE_DIR / target_name
        if target.exists():
            file_tools.delete_file(target_name)
        result = file_tools.create_folder(target_name)
        self.assertTrue(result.success, result.message)
        self.assertTrue(target.is_dir())
        self.assertTrue(file_tools.delete_file(target_name).success)

    def test_external_writes_and_deletes_are_denied(self):
        outside = str(Path.home() / "outside_ai_storage_test")
        self.assertFalse(file_tools.create_folder(outside).success)
        self.assertFalse(file_tools.delete_file(outside).success)

    def test_terminal_rejects_application_launches(self):
        result = run_command("open vs code")
        self.assertFalse(result.success)
        self.assertEqual(result.data["reason"], "app_action_misrouted")

    def test_installed_apps_list_intent(self):
        intent = parse_intent("show me the list of applications installed in the PC")
        self.assertEqual(intent.tool, "app")
        self.assertEqual(intent.action, "list_installed")

    def test_project_creation_intent(self):
        intent = parse_intent("created project name called Satish")
        self.assertEqual(intent.tool, "project")
        self.assertEqual(intent.action, "create")
        self.assertEqual(intent.params["name"], "satish")

    def test_project_create_registers_and_is_removable(self):
        pm = get_project_manager()
        res = pm.create_project("reliability_proj_test")
        self.assertTrue(res.success, res.message)
        target = config.PROJECTS_ROOT / "reliability_proj_test"
        self.assertTrue(target.is_dir())
        self.assertTrue(pm.remove_project("reliability_proj_test").success)
        target.rmdir()

    @unittest.skipIf(not config.IS_WINDOWS, "Windows only")
    def test_unknown_app_resolves_to_installed_application(self):
        # "anti gravity" is not in APP_MAPPINGS but IS installed via Start Menu
        found = _find_installed_app("anti gravity")
        self.assertTrue(found, "Expected an installed shortcut for 'anti gravity'")
        self.assertTrue(found.lower().endswith(".lnk") or found.lower().endswith(".exe"))

    def test_conversation_engine_opens_app(self):
        from conversation.conversation import get_conversation_engine
        engine = get_conversation_engine()
        engine.reset()
        response, result = engine.process("open chrome")
        self.assertIn("Sir", response)
        self.assertTrue(result.success)

    def test_conversation_engine_asks_clarification(self):
        from conversation.conversation import get_conversation_engine
        engine = get_conversation_engine()
        engine.reset()
        response, result = engine.process("search")
        self.assertIn("search for", response.lower())

    def test_conversation_engine_blocks_unknown_speaker(self):
        from conversation.conversation import get_conversation_engine
        engine = get_conversation_engine()
        engine.reset()
        engine.safety.creator_verified = False
        response, result = engine.process("open chrome", speaker_id="unknown")
        self.assertIn("creator", response.lower())

    def test_conversation_engine_screenshot(self):
        from conversation.conversation import get_conversation_engine
        engine = get_conversation_engine()
        engine.reset()
        response, result = engine.process("take a screenshot")
        self.assertIn("Sir", response)
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
