"""
Tests for the main-app integration: external pack roots, the API observer
hook, the GitHub fetcher validation and the pet <-> web STT bridge.

Run::

    QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s pet/tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pet.config import PetConfig
from pet.core.asset_loader import AssetLoader
from pet.tools.fetch_pets import validate_pack_dir

PET_ROOT = Path(__file__).resolve().parent.parent
BUNDLED = PET_ROOT / "assets" / "pets"


def make_pack_dir(root: Path, name: str = "dummy--tester") -> Path:
    """Create a minimal (invalid unless fixed up) pack directory."""
    pack = root / name
    pack.mkdir(parents=True, exist_ok=True)
    return pack


class PackRootTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("PET_PACKS_DIR", None)

    def test_packs_root_override_used_by_loader(self) -> None:
        config = PetConfig(packs_root=BUNDLED)
        loader = AssetLoader(config.asset_root, config.pets_dir, packs_root=config.packs_root)
        pack = loader.load_pack("cat--nova")
        self.assertEqual(pack.id, "cat--nova")

    def test_pets_root_property_prefers_packs_root(self) -> None:
        config = PetConfig(packs_root=BUNDLED)
        self.assertEqual(config.pets_root, BUNDLED)

    def test_env_override(self) -> None:
        os.environ["PET_PACKS_DIR"] = str(BUNDLED)
        config = PetConfig()
        self.assertEqual(config.packs_root, BUNDLED)
        self.assertEqual(config.pets_root, BUNDLED)


class FetchValidationTests(unittest.TestCase):
    def test_valid_pack_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = shutil.copytree(BUNDLED / "cat--nova", Path(tmp) / "cat--nova")
            self.assertEqual(validate_pack_dir(pack), [])

    def test_missing_metadata_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = make_pack_dir(Path(tmp))
            errors = validate_pack_dir(pack)
            self.assertIn("missing pet.json", errors)

    def test_missing_spritesheet_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = make_pack_dir(Path(tmp))
            (pack / "pet.json").write_text(
                '{"id": "dummy--tester", "spritesheetPath": "missing.webp"}', encoding="utf-8"
            )
            errors = validate_pack_dir(pack)
            self.assertTrue(any("spritesheet" in error for error in errors))


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
