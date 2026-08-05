"""
Unit tests for the pet engine core (no Qt window needed).

Run::

    venv/bin/python -m unittest discover -s pet/tests -v
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pet.core.event_bus import EventBus, PetEvent
from pet.core.state_machine import ONE_SHOT_STATES, PetState, PetStateMachine
from pet.core.emotion_manager import EmotionManager, PetEmotion
from pet.core.asset_loader import AssetLoader, PetPackError, DEFAULT_STATE_TO_ANIMATION
from pet.core.fallback_pet import build_fallback_atlas, build_fallback_pack

PET_ROOT = Path(__file__).resolve().parent.parent


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fsm = PetStateMachine()

    def test_initial_state(self) -> None:
        self.assertEqual(self.fsm.state, PetState.IDLE)

    def test_event_driven_chain(self) -> None:
        self.fsm.transition(PetState.LISTENING)
        self.fsm.transition(PetState.THINKING)
        self.fsm.transition(PetState.WORKING)
        self.fsm.transition(PetState.SPEAKING)
        self.fsm.transition(PetState.IDLE)
        self.assertEqual(self.fsm.state, PetState.IDLE)

    def test_priority_interrupt(self) -> None:
        self.fsm.transition(PetState.WORKING)
        # ERROR is higher priority -> allowed.
        self.assertTrue(self.fsm.transition(PetState.ERROR))
        self.assertEqual(self.fsm.state, PetState.ERROR)

    def test_low_priority_rejected(self) -> None:
        self.fsm.transition(PetState.SLEEPING)
        # HAPPY is lower priority than SLEEPING -> rejected.
        self.assertFalse(self.fsm.transition(PetState.HAPPY))
        self.assertEqual(self.fsm.state, PetState.SLEEPING)
        # forced change bypasses the rule.
        self.assertTrue(self.fsm.transition(PetState.HAPPY, force=True))

    def test_forced_state_change(self) -> None:
        self.fsm.transition(PetState.WORKING)
        self.assertTrue(self.fsm.transition(PetState.HAPPY, force=True))
        self.assertEqual(self.fsm.state, PetState.HAPPY)

    def test_one_shot_reverts(self) -> None:
        self.assertIn(PetState.HAPPY, ONE_SHOT_STATES)
        self.fsm.transition(PetState.HAPPY)
        self.fsm.on_animation_finished()
        self.assertEqual(self.fsm.state, PetState.IDLE)

    def test_state_timeout(self) -> None:
        self.fsm.transition(PetState.WORKING)
        self.fsm._entered_at = time.monotonic() - self.fsm.options.state_timeout - 1
        self.fsm.tick(1.0)
        self.assertEqual(self.fsm.state, PetState.IDLE)

    def test_listeners_notified(self) -> None:
        seen: list[tuple[PetState, PetState]] = []
        self.fsm.add_listener(lambda prev, cur: seen.append((prev, cur)))
        self.fsm.transition(PetState.LISTENING)
        self.assertEqual(seen, [(PetState.IDLE, PetState.LISTENING)])

    def test_reset(self) -> None:
        self.fsm.transition(PetState.WORKING)
        self.fsm.reset()
        self.assertEqual(self.fsm.state, PetState.IDLE)


class EventBusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus()

    def test_publish_delivers_payload(self) -> None:
        received: list = []
        self.bus.subscribe(PetEvent.PET_SAY, lambda e, p: received.append(p))
        self.bus.publish(PetEvent.PET_SAY, {"text": "hi"})
        self.assertEqual(received, [{"text": "hi"}])

    def test_wildcard_subscriber(self) -> None:
        events: list[PetEvent] = []
        self.bus.subscribe(PetEvent.PET_IDLE, lambda e, p: None, wildcard=True)
        self.bus.subscribe(PetEvent.PET_NOTIFY, lambda e, p: events.append(e))
        self.bus.publish(PetEvent.PET_NOTIFY, None)
        self.assertEqual(events, [PetEvent.PET_NOTIFY])

    def test_unsubscribe(self) -> None:
        received: list = []
        off = self.bus.subscribe(PetEvent.PET_IDLE, lambda e, p: received.append(p))
        off()
        self.bus.publish(PetEvent.PET_IDLE, 1)
        self.assertEqual(received, [])

    def test_bad_subscriber_does_not_break_others(self) -> None:
        received: list = []

        def bad(_e, _p):
            raise RuntimeError("boom")

        self.bus.subscribe(PetEvent.PET_IDLE, bad)
        self.bus.subscribe(PetEvent.PET_IDLE, lambda e, p: received.append(p))
        self.bus.publish(PetEvent.PET_IDLE, None)
        self.assertEqual(len(received), 1)


class EmotionTests(unittest.TestCase):
    def test_parse(self) -> None:
        mgr = EmotionManager()
        self.assertEqual(mgr.parse("happy"), PetEmotion.HAPPY)
        self.assertEqual(mgr.parse("HAPPY"), PetEmotion.HAPPY)
        self.assertEqual(mgr.parse("bogus"), PetEmotion.NEUTRAL)

    def test_change_emits_event(self) -> None:
        mgr = EmotionManager()
        seen: list = []
        mgr.add_listener(lambda prev, cur: seen.append(cur))
        mgr.set(PetEmotion.EXCITED)
        mgr.set(PetEmotion.EXCITED)  # no change -> no event
        self.assertEqual(seen, [PetEmotion.EXCITED])

    def test_presets(self) -> None:
        self.assertGreater(EmotionManager().preset.speed_multiplier, 0.0)


class AssetLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = AssetLoader(PET_ROOT / "assets")

    def test_discover_finds_bundled_packs(self) -> None:
        packs = self.loader.discover()
        self.assertIn("robot--nova", packs)
        self.assertIn("cat--nova", packs)
        self.assertIn("fox--nova", packs)
        self.assertIn("panda--nova", packs)

    def test_load_pack_slices_all_rows(self) -> None:
        pack = self.loader.load_pack("robot--nova")
        self.assertEqual(pack.id, "robot--nova")
        self.assertEqual(pack.display_name, "Nova Bot")
        expected = {
            "idle": 6, "running-right": 8, "running-left": 8, "waving": 4,
            "jumping": 5, "failed": 8, "waiting": 6, "running": 6, "review": 6,
        }
        self.assertEqual({k: len(v) for k, v in pack.frames.items()}, expected)
        frame = pack.frames["idle"][0]
        self.assertEqual(frame.size, (192, 208))

    def test_state_mapping(self) -> None:
        pack = self.loader.load_pack("cat--nova")
        self.assertEqual(pack.animation_for(PetState.IDLE), "idle")
        self.assertEqual(pack.animation_for(PetState.LISTENING), "waiting")
        self.assertEqual(pack.animation_for(PetState.ERROR), "failed")
        self.assertEqual(pack.animation_for(PetState.SPEAKING), "waving")

    def test_missing_pack_raises(self) -> None:
        with self.assertRaises(PetPackError):
            self.loader.load_pack("no-such-pet--nobody")

    def test_load_by_path(self) -> None:
        path = PET_ROOT / "assets" / "pets" / "panda--nova"
        pack = self.loader.load_pack(path)
        self.assertEqual(pack.id, "panda--nova")

    def test_load_by_bare_slug(self) -> None:
        # `pet.load_pet("robot")` must resolve robot--nova via pet_slug.
        pack = self.loader.load_pack("robot")
        self.assertEqual(pack.id, "robot--nova")

    def test_state_override(self) -> None:
        # The loader honours pet.json "states" overrides.
        loader = AssetLoader(PET_ROOT / "assets")
        pack = loader.load_pack("robot--nova")
        self.assertEqual(pack.states[PetState.WORKING], "running")


class FallbackTests(unittest.TestCase):
    def test_atlas_is_full_size(self) -> None:
        atlas = build_fallback_atlas()
        self.assertEqual(atlas.size, (1536, 1872))

    def test_pack_has_all_animations(self) -> None:
        pack = build_fallback_pack()
        self.assertEqual(pack.id, "fallback--builtin")
        self.assertIn("idle", pack.frames)
        self.assertIn("failed", pack.frames)
        self.assertEqual(pack.animation_for(PetState.IDLE), "idle")

    def test_state_map_covers_all_states(self) -> None:
        pack = build_fallback_pack()
        self.assertEqual(
            set(pack.states.keys()), set(DEFAULT_STATE_TO_ANIMATION.keys())
        )


if __name__ == "__main__":
    unittest.main()
