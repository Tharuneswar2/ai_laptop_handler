"""
speech/vad.py — Voice Activity Detection.

Filters out silence, keyboard clicks, fan noise, and other non-speech audio.
Only passes audio segments containing speech to the speech provider.
"""

import logging
import struct
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VADConfig:
    """Voice Activity Detection configuration."""
    sample_rate: int = 16000
    energy_threshold: float = 0.01        # Minimum RMS energy to consider as speech
    speech_frames_threshold: int = 3       # Consecutive speech frames to trigger start
    silence_frames_threshold: int = 15     # Consecutive silence frames to trigger end
    frame_duration_ms: int = 30            # Duration of each analysis frame


class EnergyVAD:
    """
    Simple energy-based Voice Activity Detection.

    Uses RMS energy to detect speech vs silence.
    Good enough for filtering out quiet background noise and keyboard clicks.
    """

    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self._speech_count = 0
        self._silence_count = 0
        self._is_speaking = False

    def reset(self) -> None:
        """Reset VAD state."""
        self._speech_count = 0
        self._silence_count = 0
        self._is_speaking = False

    def calculate_rms(self, chunk: bytes) -> float:
        """Calculate RMS energy of an audio chunk."""
        if not chunk:
            return 0.0

        samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
        if not samples:
            return 0.0

        sum_squares = sum(s * s for s in samples)
        rms = (sum_squares / len(samples)) ** 0.5
        return rms / 32768.0

    def process(self, chunk: bytes) -> bool:
        """
        Process an audio chunk and return True if speech is detected.

        Args:
            chunk: Raw 16-bit PCM audio chunk.

        Returns:
            True if speech is currently active, False otherwise.
        """
        rms = self.calculate_rms(chunk)
        is_speech = rms > self.config.energy_threshold

        if is_speech:
            self._speech_count += 1
            self._silence_count = 0

            if not self._is_speaking and self._speech_count >= self.config.speech_frames_threshold:
                self._is_speaking = True
                logger.debug("Speech started (RMS: %.4f)", rms)
        else:
            self._silence_count += 1
            self._speech_count = 0

            if self._is_speaking and self._silence_count >= self.config.silence_frames_threshold:
                self._is_speaking = False
                logger.debug("Speech ended (RMS: %.4f)", rms)

        return self._is_speaking

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking


class SileroVAD:
    """
    Silero VAD wrapper for higher-quality voice activity detection.

    Falls back to energy-based VAD if Silero is not installed.
    """

    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self._model = None
        self._energy_vad = EnergyVAD(config)
        self._use_silero = False

    def _load_silero(self):
        """Try to load Silero VAD model."""
        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True,
            )
            self._model = model
            self._use_silero = True
            logger.info("Silero VAD loaded successfully.")
        except Exception as e:
            logger.warning("Silero VAD not available, using energy-based VAD: %s", e)
            self._use_silero = False

    def process(self, chunk: bytes) -> bool:
        """Process audio chunk, return True if speech detected."""
        if self._use_silero:
            return self._process_silero(chunk)
        return self._energy_vad.process(chunk)

    def _process_silero(self, chunk: bytes) -> bool:
        """Process using Silero VAD."""
        try:
            import torch
            import numpy as np

            # Convert bytes to float tensor
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
            tensor = torch.from_numpy(samples)

            # Get speech probability
            prob = self._model(tensor, self.config.sample_rate).item()
            return prob > 0.5
        except Exception:
            # Fallback to energy-based
            return self._energy_vad.process(chunk)

    def reset(self) -> None:
        """Reset VAD state."""
        self._energy_vad.reset()
        if self._model:
            try:
                self._model.reset_states()
            except Exception:
                pass


def create_vad(use_silero: bool = False, config: Optional[VADConfig] = None) -> EnergyVAD | SileroVAD:
    """
    Create a VAD instance.

    Args:
        use_silero: If True, try to use Silero VAD (requires torch).
        config: VAD configuration.

    Returns:
        VAD instance.
    """
    if use_silero:
        return SileroVAD(config)
    return EnergyVAD(config)
