"""
Tests for the main-app integration: the API observer hook and the
pet <-> web STT bridge.

Run::

    QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s pet/tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pet.config import PetConfig

PET_ROOT = Path(__file__).resolve().parent.parent
BUNDLED = PET_ROOT / "assets" / "pets"


class ApiObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        from api.server import _observers, add_command_observer

        self._observers = _observers
        self.received: list[dict] = []
        add_command_observer(self.received.append)

    def tearDown(self) -> None:
        self._observers.remove(self.received.append)

    def test_rest_command_emits_processing_and_result(self) -> None:
        from api.server import CommandRequest, run_command

        run_command(CommandRequest(text="check battery"))
        types = [event.get("type") for event in self.received]
        self.assertIn("processing", types)
        self.assertIn("result", types)
        result = next(event for event in self.received if event.get("type") == "result")
        self.assertIn("success", result)
        self.assertIn("message", result)

    def test_bad_observer_does_not_break_pipeline(self) -> None:
        from api.server import _emit

        def bad(event):  # noqa: ANN001
            raise RuntimeError("boom")

        _emit({"type": "x", "text": ""})  # must not raise


class PetWebBridgeTests(unittest.TestCase):
    """Event mapping (pet controller offscreen, no server started)."""

    def setUp(self) -> None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from pet.integration import PetWebBridge

        config = PetConfig(position_path=Path(tempfile.mkdtemp()) / "pos.json")
        self.bridge = PetWebBridge("cat", config)
        self.bridge.pet.start()

    def tearDown(self) -> None:
        self.bridge.pet.quit()

    def test_transcript_sets_listening(self) -> None:
        self.bridge._on_event({"type": "transcript", "text": "hello"})
        self.assertEqual(self.bridge.pet.state_machine.state.value, "listening")

    def test_processing_sets_thinking(self) -> None:
        self.bridge._on_event({"type": "processing", "text": "open chrome"})
        self.assertEqual(self.bridge.pet.state_machine.state.value, "thinking")

    def test_success_result_goes_happy(self) -> None:
        self.bridge._on_event({"type": "result", "success": True, "message": "Done!"})
        self.assertEqual(self.bridge.pet.state_machine.state.value, "happy")

    def test_failure_result_goes_error(self) -> None:
        self.bridge._on_event({"type": "result", "success": False, "message": "Failed."})
        self.assertEqual(self.bridge.pet.state_machine.state.value, "error")

    def test_error_event_sets_error_state(self) -> None:
        self.bridge._on_event({"type": "error", "message": "boom"})
        self.assertEqual(self.bridge.pet.state_machine.state.value, "error")


if __name__ == "__main__":
    unittest.main()
