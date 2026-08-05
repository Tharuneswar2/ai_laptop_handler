# Nova Desktop Pet Engine 🐱✨

A modular, lightweight, event-driven Desktop Pet Engine built with **PySide6**. It acts as the visual face for the AI Voice Assistant, displaying emotions, state animations, and speech bubbles without holding any AI logic.

---

## 🚀 Features

- **Procedural Vector Drawing**: Cute, animated round companion rendered via `QPainter` with 60 FPS frame-timing, breathing, eye-blinking, loading indicators, Zzz sleeping particles, and glow effects.
- **GIF/Sprite Asset Fallback**: Automatically loads `.gif` animations from `pet/assets/<state>/` if asset files exist.
- **Zero AI Dependency**: Decoupled state machine driven by simple API calls or Qt Signals.
- **Transparent Desktop Overlay**: Window is frameless, transparent (`Qt.WA_TranslucentBackground`), always on top, hidden from taskbar (`Qt.Tool`), and DPI-aware.
- **Interactive Dragging**: Drag the pet across multiple monitors; position persists to disk automatically upon release.
- **Floating Speech Bubbles**: Typing character-by-character animation, auto-sizing, word wrapping, drop shadow, and smooth fade-in/fade-out.
- **Emotions & Modifiers**: Independent emotion layer (`happy`, `curious`, `confused`, `sleepy`, `surprised`, `excited`) that adjusts eye size, mouth curves, bounce amplitude, and head tilt.

---

## 📁 Directory Structure

```
pet/
├── __init__.py           # Package exports (PetController, PetEventBus, PetState)
├── config.py             # Dataclass configurations & tunable visual parameters
├── pet_window.py         # Transparent PySide6 QWidget with QPainter rendering
├── pet_controller.py     # Public API Controller
├── animation_manager.py  # Animation loop & procedural render parameter calculator
├── speech_bubble.py      # Floating speech bubble with typewriter animation
├── event_handler.py      # Qt Signal EventBus and PetState/PetEmotion enums
├── emotion_manager.py    # Emotion presets & modifier calculations
├── drag_manager.py       # Mouse drag tracking, screen clamping & position persistence
├── main.py               # Standalone runner & automated demo sequence
└── assets/               # Optional GIF override directories per state
    ├── idle/
    ├── listening/
    ├── thinking/
    ├── speaking/
    ├── happy/
    ├── sad/
    ├── sleeping/
    ├── excited/
    ├── error/
    └── working/
```

---

## 🛠️ Public API Usage

```python
from pet.pet_controller import PetController

# 1. Initialize Controller
pet = PetController()
pet.start()

# 2. Control Pet State
pet.set_state("listening")   # idle | listening | thinking | working | speaking | happy | sad | sleeping | excited | error
pet.set_emotion("excited")   # neutral | happy | curious | confused | sleepy | surprised | excited

# 3. Speech Bubbles & Notifications
pet.say("Opening Google Chrome... 💻", duration_sec=3.0)
pet.show_notification("Battery status: 95% remaining 🔋")

# 4. Movement & Visibility
pet.move_to(500, 500)
pet.sleep()
pet.wake()
pet.hide()
pet.show()
```

---

## 📡 Event Bus Integration (Backend Decoupling)

If your backend runs in a separate thread or process, emit events using `PetEventBus`:

```python
from pet.event_handler import PetEventBus

bus = PetEventBus()
bus.state_changed.emit("thinking")
bus.say_text.emit("Searching the web...")
```

---

## 🏃 Running Standalone & Demo Mode

```bash
# Run standalone (stays idle on desktop, draggable)
python -m pet.main

# Run automated demo sequence (cycles through states & speech bubbles)
python -m pet.main --demo

# Launch directly in specific state
python -m pet.main --state listening
```
