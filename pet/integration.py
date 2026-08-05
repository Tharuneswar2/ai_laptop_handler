"""
pet/integration.py — Bridge between the assistant backend and the pet engine.

Runs the desktop pet (Qt event loop, main thread) together with the web
STT server (uvicorn in a background thread).  Transcripts and command
results stream from the API server into the pet via
:func:`api.server.add_command_observer`, so the pet reacts in real time:

    "Hey Nova, open chrome"
      └─ transcript ──> pet listening (wake detected: happy)
      └─ processing ──> pet thinking + speech bubble
      └─ result ──────> pet happy / error + speech bubble

Usage from the assistant entry point::

    from pet.integration import run_pet_mode
    run_pet_mode("cat")
"""

from __future__ import annotations

import logging
import threading

from .config import PetConfig

logger = logging.getLogger(__name__)


class PetWebBridge:
    """
    Pet + web STT combined runtime.

    The pet controller is created first (it builds the QApplication), the
    web server is started afterwards in a daemon thread, and the command
    observer keeps the pet in sync with the assistant pipeline.
    """

    def __init__(self, pet_slug: str | None = None, config: PetConfig | None = None) -> None:
        self.config = config or PetConfig()
        if pet_slug:
            self.config = self.config.with_defaults(default_pet=pet_slug)

        # PetController owns the QApplication; create it on the main thread.
        from .core.pet_controller import PetController

        self.pet = PetController(self.config)
        self._server_thread: threading.Thread | None = None
        self._server_error: str | None = None

    # ─── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the pet and the background web STT server."""
        self.pet.start()

        from api import server as api_server

        api_server.add_command_observer(self._on_event)

        def _serve() -> None:
            try:
                api_server.start_server()
            except Exception as exc:  # noqa: BLE001
                self._server_error = str(exc)
                logger.exception("Web STT server failed")
                # Keep the pet alive but say something about it.
                self.pet.set_state("error")
                self.pet.say(f"Web server failed: {exc}")

        self._server_thread = threading.Thread(
            target=_serve, name="web-stt-server", daemon=True
        )
        self._server_thread.start()

        self.pet.notify("Nova online — speak via your browser")
        self.pet.say(
            "Open http://127.0.0.1:8000 in your browser to talk to me.",
            duration=6.0,
        )

    def run(self) -> int:
        """Block in the Qt event loop (call :meth:`start` first)."""
        return self.pet.run()

    def stop(self) -> None:
        """Stop the pet (the server thread is a daemon and exits with us)."""
        self.pet.stop()

    # ─── Event mapping ─────────────────────────────────────────────────

    def _on_event(self, event: dict) -> None:
        """Map assistant pipeline events onto pet behaviour (thread-safe)."""
        event_type = event.get("type")
        if event_type == "transcript":
            self.pet.set_state("listening")
        elif event_type == "wake_detected":
            self.pet.wake()
            self.pet.set_emotion("happy")
            self.pet.say("Yes?", duration=2.0)
        elif event_type == "processing":
            self.pet.set_state("thinking")
            text = str(event.get("text", "")).strip()
            if text:
                self.pet.say(f'On it: "{text[:60]}"', duration=4.0)
        elif event_type == "result":
            message = str(event.get("message", ""))
            if event.get("success"):
                self.pet.set_state("happy")
                self.pet.say(message[:200], duration=5.0)
                self.pet.notify(message[:120])
            else:
                self.pet.set_state("error")
                self.pet.say(message[:200], duration=6.0)
        elif event_type == "error":
            self.pet.set_state("error")
            self.pet.say(str(event.get("message", "Something went wrong.")), duration=5.0)


def run_pet_mode(pet_slug: str | None = None, config: PetConfig | None = None) -> int:
    """
    Start the desktop pet together with the web STT backend.

    Args:
        pet_slug: Pet pack id or slug to display (default from config).
        config: Optional :class:`PetConfig` overrides.

    Returns:
        The Qt application exit code.
    """
    bridge = PetWebBridge(pet_slug, config)
    bridge.start()
    return bridge.run()


def run_pet_mode_with_server(pet_slug: str | None = None) -> PetWebBridge:
    """Convenience for tests: build + start the bridge without blocking."""
    bridge = PetWebBridge(pet_slug)
    bridge.start()
    return bridge


__all__ = ["PetWebBridge", "run_pet_mode", "run_pet_mode_with_server"]
