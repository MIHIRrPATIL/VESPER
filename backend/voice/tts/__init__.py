"""VESPER Multi-Provider Text-to-Speech Engine."""

from backend.voice.tts.azure_tts import AzureTTSProvider
from backend.voice.tts.base import BaseTTSProvider
from backend.voice.tts.elevenlabs_tts import ElevenLabsTTSProvider
from backend.voice.tts.google_tts import GoogleTTSProvider
from backend.voice.tts.groq_tts import GroqTTSProvider
from backend.voice.tts.manager import TTSManager
from backend.voice.tts.piper_tts import PiperTTSProvider

__all__ = [
    "BaseTTSProvider",
    "GroqTTSProvider",
    "GoogleTTSProvider",
    "AzureTTSProvider",
    "PiperTTSProvider",
    "ElevenLabsTTSProvider",
    "TTSManager",
]
