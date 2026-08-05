# Nova Desktop Pet Engine 🐾

A modular, asset-driven desktop companion for the **AI Laptop Voice Handler**
(Nova). The pet displays cute animated sprites, reacts to the assistant's
state, shows speech bubbles and notifications, and can be dragged anywhere on
the desktop.

The pet section is **completely independent** of the AI brain — no LLM,
speech, routing or tool code lives here. The backend only publishes events or
calls the public controller API.

## ✨ Features

- **Codex-style pet packs** — loads any pack following the
  [awesome-codex-pet](https://github.com/legeling/awesome-codex-pet) format
  (`submission.json`, `pet.json`, `spritesheet.webp`) without code changes.
- **Transparent desktop widget** — frameless, always on top, hidden from the
  taskbar, draggable across monitors, position remembered between runs,
  DPI-aware.
- **Event-driven state machine** — idle / listening / thinking / working /
  speaking / happy / sleeping / error, with priorities, interrupts, forced
  changes, one-shot animations and timeouts.
- **Emotion layer** — happy, curious, confused, sleepy, surprised, excited,
  neutral; modifies feel (speed, bob, tint, overlays) without replacing state.
- **Speech bubbles** — rounded, shadowed, auto-sizing, word wrapping,
  typewriter effect, emoji support, fade in/out.
- **Toast notifications** — brief system messages that disappear automatically.
- **Built-in fallback pet** — procedurally drawn pet used when no pack exists.
- **Thread-safe API** — the backend can drive the pet from any thread.

## 📁 Structure

```
pet/
├── __init__.py              # public exports
├── main.py                  # CLI: python -m pet [--pet ...] [--demo]
├── config.py                # PetConfig dataclass + JSON overrides
├── core/
│   ├── pet_controller.py    # PUBLIC API (backend integration point)
│   ├── event_bus.py         # pub/sub + thread marshalling
│   ├── state_machine.py     # FSM (pure Python)
│   ├── emotion_manager.py   # emotion layer
│   ├── asset_loader.py      # pet.json parser + Codex atlas slicing
│   ├── fallback_pet.py      # built-in procedural pet
│   ├── animation_engine.py  # playback, per-state fps, one-shot, caching
│   └── renderer.py          # sprite painting + cross-fade + overlays
├── ui/
│   ├── pet_window.py        # transparent always-on-top window
│   ├── speech_bubble.py     # floating speech bubble
│   └── notification_widget.py
├── input/
│   └── drag_manager.py      # dragging, clamping, position persistence
├── assets/pets/             # installed pet packs (Codex format)
│   ├── robot--nova/
│   ├── cat--nova/
│   ├── fox--nova/
│   └── panda--nova/
├── examples/
│   ├── demo_controller.py           # API demo
│   └── assistant_integration.py     # backend integration example
├── tools/
│   └── generate_pet_sheets.py       # regenerate bundled packs
└── tests/
    └── test_core.py
```

## 🚀 Quick start

```bash
# install dependencies (project venv)
venv/bin/pip install -r requirements.txt

# list installed pet packs
venv/bin/python -m pet --list

# run the default pet with the automated demo
venv/bin/python -m pet --demo

# pick another pet / scale
venv/bin/python -m pet --pet cat --scale 1.5

# headless smoke test of the engine
venv/bin/python -m unittest discover -s pet/tests -v
```

## 🎮 Public API

```python
from pet import PetController

pet = PetController()       # or PetController(PetConfig())
pet.start()

pet.load_pet("robot--nova")   # load a pack
pet.change_pet("cat--nova")   # switch pack at runtime
pet.set_state("listening")    # idle|listening|thinking|working|speaking|happy|sleeping|error
pet.set_emotion("happy")      # neutral|happy|curious|confused|sleepy|surprised|excited
pet.say("Opening VS Code")    # speech bubble
pet.notify("Download finished")  # toast notification
pet.hide() / pet.show()
pet.sleep() / pet.wake()
pet.move_to(x, y)
pet.set_scale(1.5)
pet.list_pets()               # installed packs
```

Every method is **thread-safe**: calls from backend threads (FastAPI workers,
the voice loop, ...) are marshalled onto the Qt GUI thread automatically.
See `pet/examples/assistant_integration.py` for a full example.

## 🧩 Pet pack format (Codex compatible)

A pet pack is a folder named `<pet-slug>--<author-slug>/`:

```
pet/assets/pets/firefly--lingxiaotian/
├── submission.json          # curation metadata (author, license, tags)
├── pet.json                 # runtime metadata (required)
└── spritesheet.webp         # v1 atlas 1536x1872 (required)
```

`pet.json`:

```json
{
  "id": "firefly--lingxiaotian",
  "displayName": "Firefly",
  "description": "A cute companion.",
  "spritesheetPath": "spritesheet.webp",
  "spriteVersionNumber": 1
}
```

Atlas layout (v1, per the awesome-codex-pet validation tools) — 8 columns ×
9 rows, frame 192×208:

| Row | Animation      | Frames | Pet state        |
|-----|----------------|--------|------------------|
| 0   | idle           | 6      | idle / sleeping  |
| 1   | running-right  | 8      | (unused)         |
| 2   | running-left   | 8      | (unused)         |
| 3   | waving         | 4      | speaking         |
| 4   | jumping        | 5      | happy            |
| 5   | failed         | 8      | error            |
| 6   | waiting        | 6      | listening        |
| 7   | running        | 6      | working          |
| 8   | review         | 6      | thinking         |

Unused columns must stay transparent (the community validator enforces this).
v2 atlases (11 rows) are also accepted. Optionally, `pet.json` may add a
`"states"` object to remap states to other rows — unknown keys are ignored by
Codex and honoured by this engine.

**Installing a pack:** drop the folder under `pet/assets/pets/` (or set
`asset_root` in config). Packs installed by the codexpet.top one-command
installer land in `~/.codex/pets/<pet-id>/` — point `PetConfig.asset_root` at
`~/.codex` to use them directly.

## 🔔 Event system

The backend can stay fully decoupled by publishing semantic events on
`pet.event_bus` (thread-safe):

```python
from pet import PetEvent

pet.event_bus.publish(PetEvent.PET_WORKING, {"task": "open_app"})
pet.event_bus.publish(PetEvent.PET_SAY, {"text": "Opening VS Code"})
pet.event_bus.publish(PetEvent.PET_CHANGE_PET, {"id": "cat--nova"})
```

Events: `PET_IDLE`, `PET_LISTENING`, `PET_THINKING`, `PET_WORKING`,
`PET_SPEAKING`, `PET_HAPPY`, `PET_ERROR`, `PET_SLEEP`, `PET_WAKE`,
`PET_NOTIFY`, `PET_SAY`, `PET_CHANGE_PET`, `PET_EMOTION`, `PET_HIDE`,
`PET_SHOW`, `PET_DRAG_END`. The engine also publishes every state change on
the bus, so other components can observe the pet.

## ⚙️ Configuration

`pet/config.py` → `PetConfig` dataclass: default pet, asset root, pet size,
scale, fps, always-on-top, opacity, theme, bubble/notification durations,
default position and position persistence path. JSON overrides can be loaded
with `load_config()` (see the `PET_CONFIG_FILE` env var or `--config`).

## 🛠 Bundled pets

The four bundled packs (`robot`, `cat`, `fox`, `panda`) are generated by
`pet/tools/generate_pet_sheets.py` and validated against the same rules as
the awesome-codex-pet repo. Regenerate with:

```bash
venv/bin/python -m pet.tools.generate_pet_sheets --validate
```

If every pack is missing, the engine falls back to a procedurally drawn pet
(`core/fallback_pet.py`) — a safety net, not a hardcoded dependency.

## 🔌 Integration with the Nova backend

```python
# anywhere in the backend (FastAPI route, voice loop, tool router...)
from pet import PetController

pet = PetController()       # create once, in the Qt thread
pet.start()

# in your pipeline:
pet.set_state("listening")          # wake word detected
pet.set_state("thinking")           # command received
pet.set_state("working")            # tool executing
pet.set_state("speaking")           # result ready
pet.say(result.message)
pet.set_state("idle")               # response complete
```

The pet engine owns its own Qt event loop: run `pet.run()` in the main thread
or embed it in an existing PySide6 application with `pet.start()`.

## ✅ Acceptance checklist

- [x] transparent always-on-top desktop widget
- [x] Codex pet packs load from an assets folder (no code changes)
- [x] state changes driven by external events
- [x] speech bubbles + notifications
- [x] dragging with position persistence
- [x] no AI logic inside the pet section
- [x] modular, thread-safe API for the assistant backend
