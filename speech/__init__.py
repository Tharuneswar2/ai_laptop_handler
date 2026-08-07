"""
speech/__init__.py — Speech provider package.

Provides pluggable speech-to-text providers:
  - browser: Web Speech API via browser (default)
  - amazon: Amazon Transcribe Streaming (server-side, --aws flag)
"""

from speech.provider import SpeechProvider, TranscriptEvent, TranscriptKind, get_provider

__all__ = ["SpeechProvider", "TranscriptEvent", "TranscriptKind", "get_provider"]
