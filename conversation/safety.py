"""
conversation/safety.py — Creator-first safety checks for the conversational layer.

Ensures only the verified creator can execute sensitive tasks.
Unknown speakers are blocked from sensitive operations.
"""

import logging
import re
from typing import Optional

from conversation.schemas import (
    CreatorIntent,
    IntentType,
    SafetyLevel,
    INTENT_SAFETY,
)

logger = logging.getLogger(__name__)


class SafetyGate:
    """
    Creator-first safety gate.

    In single-user mode (default), the creator is always verified.
    For multi-user scenarios, unknown speakers are blocked from
    sensitive tasks and asked for creator confirmation.
    """

    def __init__(self):
        self._creator_verified: bool = True
        self._creator_name: str = "Sir"
        self._known_speakers: set = set()

    @property
    def creator_verified(self) -> bool:
        return self._creator_verified

    @creator_verified.setter
    def creator_verified(self, value: bool) -> None:
        self._creator_verified = value

    @property
    def creator_name(self) -> str:
        return self._creator_name

    def verify_creator(self, speaker_id: Optional[str] = None) -> bool:
        """
        Check if the current speaker is the verified creator.
        In single-user mode, always returns True.
        """
        # Single-user mode: always verified
        if speaker_id is None:
            self._creator_verified = True
            return True

        # Multi-user mode: check against known speakers
        if speaker_id in self._known_speakers:
            self._creator_verified = True
            return True

        self._creator_verified = False
        logger.warning("Unknown speaker '%s' detected.", speaker_id)
        return False

    def register_creator(self, speaker_id: str) -> None:
        """Register a speaker as the verified creator."""
        self._known_speakers.add(speaker_id)
        self._creator_name = "Sir"
        logger.info("Creator registered: %s", speaker_id)

    def check_intent_safety(self, intent: CreatorIntent) -> tuple[bool, str]:
        """
        Check if an intent is safe to execute.

        Returns:
            (allowed, reason) tuple.
        """
        # Creator is always allowed
        if self._creator_verified:
            return True, "Creator verified"

        level = intent.safety_level

        if level == SafetyLevel.BLOCKED:
            logger.warning("[Safety] Blocked intent '%s' from unverified speaker.", intent.intent_type.value)
            return False, "This action requires creator authorization."

        if level == SafetyLevel.SENSITIVE:
            logger.warning("[Safety] Sensitive intent '%s' from unverified speaker.", intent.intent_type.value)
            return False, "I can only do that for the creator, Sir."

        if level == SafetyLevel.MODERATE:
            # Moderate actions allowed but logged
            return True, "Action allowed with logging."

        # Safe actions always allowed
        return True, "Safe action allowed."

    def get_unknown_speaker_response(self) -> str:
        """Get the standard response for unknown speakers."""
        return "I can only respond to the creator, Sir."


def classify_safety(intent_type: IntentType) -> SafetyLevel:
    """Look up the safety level for an intent type."""
    return INTENT_SAFETY.get(intent_type, SafetyLevel.SAFE)
