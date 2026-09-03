"""VESPER Low-Power Continuous Wake Word Detection Subsystem.

Provides:
- WebRTC VAD pre-gating for near-zero idle CPU consumption (<0.5% CPU during silence).
- Continuous background listening thread with self-trigger prevention during TTS playback.
- Support for "Hey Alfred" and "Alfred" wake phrases.
"""

from backend.voice.wakeword.detector import WakeWordDetector, WakeWordEvent
from backend.voice.wakeword.listener import WakeWordListener

__all__ = [
    "WakeWordDetector",
    "WakeWordEvent",
    "WakeWordListener",
]
