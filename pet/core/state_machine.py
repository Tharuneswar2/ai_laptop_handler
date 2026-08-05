"""
pet/core/state_machine.py — Finite state machine for the pet.

States are driven by semantic events from the assistant backend:

    IDLE --wake word--> LISTENING --command--> THINKING --execute--> WORKING
        --result--> SPEAKING --done--> IDLE
    any --failure--> ERROR --ack--> IDLE
    IDLE --inactivity--> SLEEPING --wake--> IDLE

The machine is pure Python (no Qt), so it can be unit-tested headlessly.
The controller feeds it time via :meth:`PetStateMachine.tick`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class PetState(str, Enum):
    """The visual states the pet can be in."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    WORKING = "working"
    SPEAKING = "speaking"
    HAPPY = "happy"
    SLEEPING = "sleeping"
    ERROR = "error"

    @property
    def label(self) -> str:
        """Human friendly label, e.g. ``PetState.IDLE.label == "idle"``."""
        return self.value


# Lower value = lower priority.  A state can interrupt another state only
# when it has equal or higher priority, unless the request is forced.
STATE_PRIORITY: dict[PetState, int] = {
    PetState.IDLE: 0,
    PetState.HAPPY: 1,
    PetState.LISTENING: 2,
    PetState.THINKING: 3,
    PetState.WORKING: 4,
    PetState.SPEAKING: 5,
    PetState.SLEEPING: 6,
    PetState.ERROR: 7,
}

# States that play once and automatically return to the fallback state.
ONE_SHOT_STATES: frozenset[PetState] = frozenset({PetState.HAPPY})

# Transitions that are always allowed between states (event-driven).
ALLOWED_TRANSITIONS: dict[PetState, frozenset[PetState]] = {
    PetState.IDLE: frozenset(
        {
            PetState.LISTENING,
            PetState.THINKING,
            PetState.WORKING,
            PetState.SPEAKING,
            PetState.HAPPY,
            PetState.SLEEPING,
            PetState.ERROR,
        }
    ),
    PetState.LISTENING: frozenset(
        {
            PetState.IDLE,
            PetState.THINKING,
            PetState.WORKING,
            PetState.SPEAKING,
            PetState.HAPPY,
            PetState.ERROR,
        }
    ),
    PetState.THINKING: frozenset(
        {PetState.IDLE, PetState.WORKING, PetState.SPEAKING, PetState.HAPPY, PetState.ERROR}
    ),
    PetState.WORKING: frozenset(
        {PetState.IDLE, PetState.SPEAKING, PetState.HAPPY, PetState.ERROR}
    ),
    PetState.SPEAKING: frozenset({PetState.IDLE, PetState.HAPPY, PetState.ERROR}),
    PetState.HAPPY: frozenset({PetState.IDLE, PetState.ERROR}),
    PetState.SLEEPING: frozenset({PetState.IDLE, PetState.ERROR}),
    PetState.ERROR: frozenset({PetState.IDLE}),
}

StateListener = Callable[[PetState, PetState], None]  # (previous, current)


@dataclass
class StateMachineOptions:
    """Tunables for the FSM."""

    state_timeout: float = 90.0
    """Max seconds a non-IDLE state may stay active before being released."""

    fallback_state: PetState = PetState.IDLE
    """State to return to after timeouts / one-shot animations."""


class PetStateMachine:
    """
    Event-driven state machine with priorities, interrupts and timeouts.

    Usage::

        fsm = PetStateMachine()
        fsm.transition(PetState.LISTENING)
        fsm.force(PetState.HAPPY)          # ignore rules (one-shot)
        fsm.tick(0.1)                       # advance time (auto timeouts)
        fsm.on_animation_finished()         # one-shot states revert
    """

    def __init__(self, options: StateMachineOptions | None = None) -> None:
        self.options = options or StateMachineOptions()
        self._state = PetState.IDLE
        self._entered_at = time.monotonic()
        self._listeners: list[StateListener] = []
        self._history: list[PetState] = []

    # ─── State accessors ───────────────────────────────────────────────

    @property
    def state(self) -> PetState:
        """The currently active state."""
        return self._state

    @property
    def elapsed(self) -> float:
        """Seconds spent in the current state."""
        return time.monotonic() - self._entered_at

    # ─── Transitions ───────────────────────────────────────────────────

    def transition(self, target: PetState, *, force: bool = False) -> bool:
        """
        Request a state change.

        Args:
            target: The desired state.
            force: Bypass transition rules and priority checks.  Used for
                interrupts from the backend (e.g. an error while working).

        Returns:
            True when the state actually changed.
        """
        if target == self._state:
            return False
        if not force and not self._can_transition(target):
            logger.debug("Rejected %s while in %s", target.value, self._state.value)
            return False
        self._change(target)
        return True

    def interrupt(self, target: PetState) -> bool:
        """Force an interrupt: always allowed, respecting one-shot cleanup."""
        return self.transition(target, force=True)

    def tick(self, seconds: float) -> None:
        """
        Advance the machine's clock.

        Currently only used to enforce ``state_timeout`` so a state the
        backend forgot to release does not stick forever.
        """
        if self._state is PetState.IDLE:
            return
        if self.elapsed >= self.options.state_timeout:
            logger.warning("State %s timed out after %.0fs", self._state.value, self.elapsed)
            self._change(self.options.fallback_state)

    def on_animation_finished(self) -> None:
        """
        Called by the animation engine when a one-shot animation completes.

        One-shot states (HAPPY) return to the fallback state automatically.
        """
        if self._state in ONE_SHOT_STATES:
            previous = self._pop_history() or self.options.fallback_state
            self._change(previous)

    def reset(self) -> None:
        """Hard reset to IDLE (used when changing pets)."""
        if self._state is not PetState.IDLE:
            self._change(PetState.IDLE)
        self._history.clear()

    # ─── Listeners ─────────────────────────────────────────────────────

    def add_listener(self, listener: StateListener) -> Callable[[], None]:
        """Register ``listener(previous, current)`` and return an unsubscribe fn."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    # ─── Internals ─────────────────────────────────────────────────────

    def _can_transition(self, target: PetState) -> bool:
        """Rule + priority check for a non-forced transition."""
        if self._state in ALLOWED_TRANSITIONS and target in ALLOWED_TRANSITIONS[self._state]:
            return True
        # Equal/higher priority states may always take over (interrupts).
        return STATE_PRIORITY[target] >= STATE_PRIORITY[self._state]

    def _change(self, target: PetState) -> None:
        previous = self._state
        if previous is not target:
            if previous in ONE_SHOT_STATES:
                self._history.append(previous)
            self._state = target
            self._entered_at = time.monotonic()
            logger.debug("State: %s -> %s", previous.value, target.value)
            for listener in list(self._listeners):
                try:
                    listener(previous, target)
                except Exception:  # noqa: BLE001
                    logger.exception("State listener failed")

    def _pop_history(self) -> PetState | None:
        return self._history.pop() if self._history else None


__all__ = ["PetState", "PetStateMachine", "StateMachineOptions"]
