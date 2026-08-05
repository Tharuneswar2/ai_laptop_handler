"""
pet/core/emotion_manager.py — Emotion layer independent from the state machine.

Emotions never replace the state machine; they only tweak how the current
animation *feels*: playback speed, bob amplitude and small overlay effects
(hearts, sparkles, question marks, ...) rendered on top of the sprite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class PetEmotion(str, Enum):
    """Emotions the pet can express on top of its current state."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    CURIOUS = "curious"
    CONFUSED = "confused"
    SLEEPY = "sleepy"
    SURPRISED = "surprised"
    EXCITED = "excited"

    @property
    def label(self) -> str:
        return self.value


@dataclass(frozen=True)
class EmotionPreset:
    """Rendering modifiers applied by an emotion."""

    speed_multiplier: float = 1.0
    """Multiplies the animation fps (e.g. 1.4 = livelier)."""

    bob_amplitude: float = 0.0
    """Extra vertical bob added to the sprite, in logical pixels."""

    overlay: str = ""
    """Small text/emoji shown above the pet (e.g. ``"♥"``, ``"?"``, ``"!"``)."""

    tint: tuple[int, int, int] | None = None
    """Optional RGB tint blended over the sprite, or None for no tint."""

    tail_wag: bool = False
    """Reserved hint used by future pet packs with separate tails."""


EMOTION_PRESETS: dict[PetEmotion, EmotionPreset] = {
    PetEmotion.NEUTRAL: EmotionPreset(speed_multiplier=1.0, bob_amplitude=0.0, overlay=""),
    PetEmotion.HAPPY: EmotionPreset(
        speed_multiplier=1.2, bob_amplitude=1.5, overlay="♥", tint=(255, 214, 224)
    ),
    PetEmotion.CURIOUS: EmotionPreset(
        speed_multiplier=1.0, bob_amplitude=0.0, overlay="?"
    ),
    PetEmotion.CONFUSED: EmotionPreset(
        speed_multiplier=0.9, bob_amplitude=-1.0, overlay="❓", tint=(180, 200, 255)
    ),
    PetEmotion.SLEEPY: EmotionPreset(
        speed_multiplier=0.6, bob_amplitude=0.5, overlay="💤"
    ),
    PetEmotion.SURPRISED: EmotionPreset(
        speed_multiplier=1.3, bob_amplitude=2.0, overlay="!"
    ),
    PetEmotion.EXCITED: EmotionPreset(
        speed_multiplier=1.5, bob_amplitude=2.5, overlay="✨"
    ),
}

EmotionListener = Callable[[PetEmotion, PetEmotion], None]  # (previous, current)


class EmotionManager:
    """
    Holds the current emotion and resolves it to rendering modifiers.

    The emotion is independent from :class:`~pet.core.state_machine.PetState`;
    a happy pet can still be in the WORKING state, it just bobs a bit more.
    """

    def __init__(self) -> None:
        self._emotion = PetEmotion.NEUTRAL
        self._listeners: list[EmotionListener] = []

    @property
    def emotion(self) -> PetEmotion:
        """The current emotion."""
        return self._emotion

    @property
    def preset(self) -> EmotionPreset:
        """Resolved rendering modifiers for the current emotion."""
        return EMOTION_PRESETS[self._emotion]

    def set(self, emotion: PetEmotion) -> None:
        """Set the current emotion; NO-OP if unchanged."""
        if emotion == self._emotion:
            return
        previous = self._emotion
        self._emotion = emotion
        logger.debug("Emotion: %s -> %s", previous.value, emotion.value)
        for listener in list(self._listeners):
            try:
                listener(previous, emotion)
            except Exception:  # noqa: BLE001
                logger.exception("Emotion listener failed")

    def reset(self) -> None:
        """Return to NEUTRAL."""
        self.set(PetEmotion.NEUTRAL)

    def add_listener(self, listener: EmotionListener) -> Callable[[], None]:
        """Register ``listener(previous, current)``; returns an unsubscribe fn."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    def parse(self, value: str | PetEmotion | None) -> PetEmotion:
        """Coerce a string/enum into a valid emotion (NEUTRAL on unknown)."""
        if isinstance(value, PetEmotion):
            return value
        if isinstance(value, str):
            try:
                return PetEmotion(value.lower())
            except ValueError:
                return PetEmotion.NEUTRAL
        return PetEmotion.NEUTRAL


__all__ = ["PetEmotion", "EmotionManager", "EmotionPreset", "EMOTION_PRESETS"]
