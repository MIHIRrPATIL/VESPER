"""VESPER Real-time Audio, WebRTC VAD, STT, and Multi-Provider TTS Subsystem."""

from backend.voice.audio_utils import frame_pcm, pack_pcm_to_wav
from backend.voice.pipeline import VoicePipelineSession
from backend.voice.stt import GroqSpeechToText
from backend.voice.tts import BaseTTSProvider, TTSManager
from backend.voice.vad import UtteranceSegmenter, VadEvent

__all__ = [
    "frame_pcm",
    "pack_pcm_to_wav",
    "UtteranceSegmenter",
    "VadEvent",
    "GroqSpeechToText",
    "BaseTTSProvider",
    "TTSManager",
    "VoicePipelineSession",
]
