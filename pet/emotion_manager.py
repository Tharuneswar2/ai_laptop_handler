"""
pet/emotion_manager.py — Emotion modifier layer.

Emotions modify visual appearance independently of the pet's state.
They adjust draw parameters (eye size, mouth curve, animation speed)
that the animation manager uses when rendering.
"""

import logging
from dataclasses import dataclass

from pet.event_handler import PetEmotion

logger = logging.getLogger(__name__)


@dataclass
class EmotionModifiers:
    """Visual modifiers applied by the current emotion."""
    eye_scale: float = 1.0          # multiply eye size
    pupil_offset_y: float = 0.0     # shift pupils up/down
    mouth_curve: float = 0.0        # positive = smile, negative = frown
    mouth_open: float = 0.0         # 0 = closed, 1 = fully open
    body_bounce: float = 0.0        # vertical bounce amplitude
    animation_speed: float = 1.0    # speed multiplier
    blush_opacity: float = 0.0      # cheek blush visibility (0-1)
    head_tilt: float = 0.0          # degrees of head tilt
    sparkle: bool = False           # show sparkle particles


# Pre-defined emotion modifier presets
EMOTION_PRESETS: dict[str, EmotionModifiers] = {
    PetEmotion.NEUTRAL: EmotionModifiers(),
    PetEmotion.HAPPY: EmotionModifiers(
        eye_scale=1.1, mouth_curve=0.5, blush_opacity=0.6,
        body_bounce=2.0, animation_speed=1.2,
    ),
    PetEmotion.CURIOUS: EmotionModifiers(
        eye_scale=1.2, pupil_offset_y=-2.0, head_tilt=10.0,
        mouth_curve=0.1,
    ),
    PetEmotion.CONFUSED: EmotionModifiers(
        eye_scale=0.9, pupil_offset_y=1.0, head_tilt=-8.0,
        mouth_curve=-0.2,
    ),
    PetEmotion.SLEEPY: EmotionModifiers(
        eye_scale=0.5, mouth_curve=0.0, animation_speed=0.5,
    ),
    PetEmotion.SURPRISED: EmotionModifiers(
        eye_scale=1.4, mouth_open=0.8, body_bounce=4.0,
    ),
    PetEmotion.EXCITED: EmotionModifiers(
        eye_scale=1.2, mouth_curve=0.6, mouth_open=0.3,
        body_bounce=5.0, animation_speed=1.5, sparkle=True,
        blush_opacity=0.4,
    ),
}


class EmotionManager:
    """Manages the pet's current emotion and its visual modifiers."""

    def __init__(self):
        self._emotion = PetEmotion.NEUTRAL
        self._modifiers = EMOTION_PRESETS[PetEmotion.NEUTRAL]

    @property
    def emotion(self) -> PetEmotion:
        return self._emotion

    @property
    def modifiers(self) -> EmotionModifiers:
        return self._modifiers

    def set_emotion(self, emotion: str) -> None:
        """Set the current emotion by name."""
        try:
            emo = PetEmotion(emotion)
        except ValueError:
            logger.warning("Unknown emotion '%s', using neutral.", emotion)
            emo = PetEmotion.NEUTRAL

        if emo != self._emotion:
            self._emotion = emo
            self._modifiers = EMOTION_PRESETS.get(emo, EmotionModifiers())
            logger.debug("Emotion changed to: %s", emo.value)

    def reset(self) -> None:
        """Reset emotion to neutral."""
        self.set_emotion(PetEmotion.NEUTRAL)
