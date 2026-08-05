"""
pet/core/event_bus.py — Decoupled pub/sub event system.

The assistant backend never touches the pet UI directly.  It publishes
semantic events (``PetEvent.PET_LISTENING``, ``PetEvent.PET_SAY``, ...) on the
event bus, and the pet engine subscribes.  Any component — the controller, a
notification logger, or an analytics module — can also subscribe, so the
backend and the pet stay loosely coupled.

Threading: :meth:`EventBus.publish` is thread-safe.  If a Qt ``QCoreApplication``
exists, events are marshalled onto the Qt main thread before delivery so
subscribers may safely touch widgets from any backend thread.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Registered synchronously by the engine on first use; set by PetController.
_QTHREAD_HOOK: Callable[[Callable[[], None]], None] | None = None


def set_thread_hook(hook: Callable[[Callable[[], None]], None]) -> None:
    """
    Install a callable that runs a thunk on the GUI thread.

    ``hook(fn)`` must guarantee that ``fn`` eventually runs on the Qt main
    thread (e.g. ``QMetaObject.invokeMethod`` via a QObject proxy).  This is
    used to deliver events from arbitrary backend threads safely.
    """
    global _QTHREAD_HOOK
    _QTHREAD_HOOK = hook


class PetEvent(str, Enum):
    """Semantic events the assistant backend can publish."""

    PET_IDLE = "PET_IDLE"
    PET_LISTENING = "PET_LISTENING"
    PET_THINKING = "PET_THINKING"
    PET_WORKING = "PET_WORKING"
    PET_SPEAKING = "PET_SPEAKING"
    PET_HAPPY = "PET_HAPPY"
    PET_ERROR = "PET_ERROR"
    PET_SLEEP = "PET_SLEEP"
    PET_WAKE = "PET_WAKE"
    PET_NOTIFY = "PET_NOTIFY"
    PET_SAY = "PET_SAY"
    PET_CHANGE_PET = "PET_CHANGE_PET"
    PET_EMOTION = "PET_EMOTION"
    PET_HIDE = "PET_HIDE"
    PET_SHOW = "PET_SHOW"
    PET_DRAG_END = "PET_DRAG_END"


Subscriber = Callable[[PetEvent, Any], None]


class EventBus:
    """
    A small synchronous, thread-safe pub/sub event bus.

    Usage::

        bus = EventBus()
        bus.subscribe(PetEvent.PET_SAY, on_say)
        bus.publish(PetEvent.PET_SAY, {"text": "Hello!"})
    """

    def __init__(self) -> None:
        self._subscribers: dict[PetEvent, list[Subscriber]] = defaultdict(list)
        self._wildcards: list[Subscriber] = []
        self._lock = threading.RLock()

    # ─── Subscription ──────────────────────────────────────────────────

    def subscribe(
        self,
        event: PetEvent,
        callback: Subscriber,
        *,
        wildcard: bool = False,
    ) -> Callable[[], None]:
        """
        Subscribe ``callback`` to ``event``.

        Args:
            event: The event to listen for.
            callback: ``callback(event, payload)`` called on publication.
            wildcard: If True, the callback receives every event.

        Returns:
            An unsubscribe callable.
        """
        with self._lock:
            if wildcard:
                self._wildcards.append(callback)
            else:
                self._subscribers[event].append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if wildcard:
                    self._wildcards.remove(callback)
                else:
                    try:
                        self._subscribers[event].remove(callback)
                    except ValueError:
                        pass

        return unsubscribe

    def unsubscribe_all(self) -> None:
        """Remove every subscriber (used mainly in tests/teardown)."""
        with self._lock:
            self._subscribers.clear()
            self._wildcards.clear()

    # ─── Publishing ────────────────────────────────────────────────────

    def publish(self, event: PetEvent, payload: Any = None) -> None:
        """
        Publish ``event`` with an optional ``payload``.

        May be called from any thread; delivery is marshalled onto the Qt
        main thread when a thread hook is installed.
        """
        if _QTHREAD_HOOK is not None and threading.current_thread().name != "MainThread":
            _QTHREAD_HOOK(lambda: self._deliver(event, payload))
            return
        self._deliver(event, payload)

    def _deliver(self, event: PetEvent, payload: Any) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(event, ()))
            wildcards = list(self._wildcards)
        for callback in subscribers + wildcards:
            try:
                callback(event, payload)
            except Exception:  # noqa: BLE001 — a bad subscriber must not break others
                logger.exception("Subscriber for %s raised an error", event)


__all__ = ["EventBus", "PetEvent", "set_thread_hook"]
