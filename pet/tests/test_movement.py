"""
Tests for the movement controller and arbitrary-animation playback.

Run::

    QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s pet/tests -v
"""

from __future__ import annotations

import os
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from pet.core.asset_loader import AssetLoader
from pet.core.emotion_manager import EmotionManager
from pet.core.animation_engine import AnimationEngine
from pet.core.movement import MovementController
from pet.core.state_machine import PetState

PET_ROOT = Path(__file__).resolve().parent.parent


class _FakeWindow:
    """Minimal stand-in for PetWindow used by the movement controller."""

    def __init__(self, x: int = 300, y: int = 500) -> None:
        self._pos = QPoint(x, y)
        self.width = lambda: 192  # noqa: E731
        self.height = lambda: 208  # noqa: E731
        self._visible = True

        class _Drag:
            @property
            def is_dragging(self) -> bool:
                return False

        self.drag = _Drag()

    def pos(self) -> QPoint:
        return QPoint(self._pos)

    def move_pet(self, position: QPoint) -> None:
        self._pos = QPoint(position)

    def isVisible(self) -> bool:  # noqa: N802
        return self._visible


class AnimationPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.loader = AssetLoader(PET_ROOT / "assets")
        cls.emotions = EmotionManager()
        cls.engine = AnimationEngine(cls.emotions)
        cls.engine.set_pack(cls.loader.load_pack("robot--nova"))

    def test_play_animation_switches_row_but_keeps_state(self) -> None:
        self.engine.set_state(PetState.IDLE)
        ok = self.engine.play_animation("running-left")
        self.assertTrue(ok)
        self.assertEqual(self.engine.animation, "running-left")
        self.assertEqual(self.engine._state, PetState.IDLE)

    def test_restore_returns_to_state_animation(self) -> None:
        self.engine.set_state(PetState.IDLE)
        self.engine.play_animation("running-right")
        self.engine.restore_state_animation()
        self.assertEqual(self.engine.animation, "idle")

    def test_play_missing_row_returns_false(self) -> None:
        self.assertFalse(self.engine.play_animation("no-such-row"))


class MovementControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        loader = AssetLoader(PET_ROOT / "assets")
        emotions = EmotionManager()
        self.engine = AnimationEngine(emotions)
        self.engine.set_pack(loader.load_pack("robot--nova"))
        self.window = _FakeWindow(x=300, y=500)
        self.mover = MovementController(
            self.engine,
            self.window,
            interval_ms=40,
            step_px=10,
            min_pause=1,
            max_pause=1,
            min_distance=100,
            max_distance=100,
            rng=random.Random(42),
        )

    def test_walk_moves_window_and_uses_run_animation(self) -> None:
        start_x = self.window.pos().x()
        self.mover.tick_second()  # countdown 1 -> 0
        self.assertTrue(self.mover.is_moving)
        self.assertIn(self.engine.animation, ("running-left", "running-right"))
        steps = 0
        while self.mover.is_moving and steps < 50:
            self.mover._step()
            steps += 1
        self.assertFalse(self.mover.is_moving)
        self.assertEqual(self.engine.animation, "idle")
        self.assertNotEqual(self.window.pos().x(), start_x)

    def test_state_change_stops_walk(self) -> None:
        self.mover.tick_second()
        self.assertTrue(self.mover.is_moving)
        self.mover.on_state_changed(PetState.LISTENING)
        self.assertFalse(self.mover.is_moving)
        self.assertEqual(self.engine.animation, "idle")

    def test_no_walk_when_disabled(self) -> None:
        self.mover.set_enabled(False)
        self.mover.tick_second()
        self.assertFalse(self.mover.is_moving)
        self.assertEqual(self.window.pos().x(), 300)

    def test_no_walk_when_not_idle(self) -> None:
        self.mover.on_state_changed(PetState.SLEEPING)
        self.mover.tick_second()
        self.assertFalse(self.mover.is_moving)


if __name__ == "__main__":
    unittest.main()
