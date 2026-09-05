"""Automated Test Suite for the VESPER Voice Subsystem.

Tests WebRTC VAD framing and segmentation, WAV packaging, TTS fallback priority,
sentence chunking, and the voice microservice API.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from typing import AsyncGenerator
import pytest
from fastapi.testclient import TestClient

from backend.voice.app import app
from backend.voice.audio_utils import frame_pcm, pack_pcm_to_wav
from backend.voice.pipeline import VoicePipelineSession
from backend.voice.tts.base import BaseTTSProvider
from backend.voice.tts.manager import TTSManager
from backend.voice.vad import UtteranceSegmenter, VadEvent


def _generate_synthetic_tone_pcm(
    frequency: float = 440.0,
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> bytes:
    """Generates synthetic 16-bit mono sine wave PCM bytes."""
    total_samples = int(sample_rate * duration_s)
    raw = bytearray()
    for i in range(total_samples):
        t = i / sample_rate
        val = int(amplitude * 32767.0 * math.sin(2.0 * math.pi * frequency * t))
        val = max(-32768, min(32767, val))
        raw.extend(struct.pack("<h", val))
    return bytes(raw)


def test_audio_utils_framing():
    """Verifies that frame_pcm correctly slices bytes into standard 30ms frames."""
    sample_rate = 16000
    frame_ms = 30
    frame_size_bytes = int(sample_rate * (frame_ms / 1000.0) * 2)  # 960 bytes

    # Provide 3 full frames + trailing remainder
    dummy_pcm = b"\x00" * (frame_size_bytes * 3 + 120)
    frames = list(frame_pcm(dummy_pcm, sample_rate, frame_ms))

    assert len(frames) == 3
    for f in frames:
        assert len(f) == frame_size_bytes


def test_audio_utils_wav_packing():
    """Verifies that raw PCM bytes are packed into a valid WAV file structure."""
    sample_rate = 16000
    pcm = _generate_synthetic_tone_pcm(frequency=440.0, duration_s=0.5, sample_rate=sample_rate)

    wav_bytes = pack_pcm_to_wav(pcm, sample_rate=sample_rate, channels=1, sample_width=2)
    assert len(wav_bytes) > len(pcm)
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"

    # Read back using standard wave library
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == sample_rate
        frames = w.readframes(w.getnframes())
        assert len(frames) == len(pcm)


def test_webrtc_vad_silence_detection():
    """Verifies that WebRTC VAD classifies pure silence frames correctly."""
    segmenter = UtteranceSegmenter(sample_rate=16000, frame_duration_ms=30)
    silence_frame = b"\x00" * 960

    # 10 frames of silence should stay SILENCE
    for _ in range(10):
        event, audio = segmenter.process_frame(silence_frame)
        assert event == VadEvent.SILENCE
        assert audio is None


def test_tts_sentence_splitting():
    """Verifies that long multi-sentence responses are cleanly chunked for streaming."""
    text = (
        "Good evening, sir. All gateway sockets are currently healthy! "
        "Shall I initiate the desk HUD sequence?"
    )
    sentences = TTSManager.split_sentences(text)

    assert len(sentences) == 3
    assert sentences[0] == "Good evening, sir."
    assert sentences[1] == "All gateway sockets are currently healthy!"
    assert sentences[2] == "Shall I initiate the desk HUD sequence?"


class MockFailingProvider(BaseTTSProvider):
    @property
    def name(self) -> str:
        return "mock_failing"

    def is_available(self) -> bool:
        return True

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        raise RuntimeError("Simulated cloud failure")
        yield b""  # unreachable generator syntax


class MockWorkingProvider(BaseTTSProvider):
    @property
    def name(self) -> str:
        return "mock_working"

    def is_available(self) -> bool:
        return True

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        yield b"ID3_MOCK_MP3_CHUNK_" + text.encode("utf-8")


@pytest.mark.asyncio
async def test_tts_manager_fallback_order():
    """Verifies that when a primary provider fails, TTSManager seamlessly falls back."""
    failing = MockFailingProvider()
    working = MockWorkingProvider()

    manager = TTSManager(providers=[failing, working])
    chunks = []

    async for chunk in manager.stream_speech("Hello Mihir."):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0] == b"ID3_MOCK_MP3_CHUNK_Hello Mihir."


def test_voice_service_health_endpoint():
    """Tests the /health endpoint of the voice microservice."""
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "vesper-voice"
        assert "available_tts_providers" in data
        assert data["default_voice"] == "en-GB-Neural2-B"


@pytest.mark.asyncio
async def test_voice_pipeline_session_interruption():
    """Verifies that user interruption / barge-in cleanly aborts active speech."""
    working = MockWorkingProvider()
    manager = TTSManager(providers=[working])
    session = VoicePipelineSession(tts_manager=manager)

    collected = []
    # Begin streaming and interrupt mid-flight
    async for chunk in session.stream_response("First sentence. Second sentence."):
        collected.append(chunk)
        session.interrupt()

    # Interruption flag should be set and stream curtailed
    assert session._interrupted is True


@pytest.mark.asyncio
async def test_tts_manager_piper_priority():
    """Verifies that Piper TTS is the primary preferred provider and produces stream audio."""
    manager = TTSManager()
    active = manager.get_active_providers()
    assert len(active) > 0
    # Piper must be the first active provider
    assert active[0].name.startswith("piper")

    chunks = []
    async for chunk in manager.stream_speech("Good evening, sir."):
        chunks.append(chunk)
    assert len(chunks) > 0
    total_bytes = sum(len(c) for c in chunks)
    assert total_bytes > 1000


@pytest.mark.asyncio
async def test_piper_emotive_tags_and_dsp():
    """Verifies that Piper TTS applies Alan Sample 2 defaults (0.85 speed), parses emotive tags, and applies DSP."""
    from backend.voice.tts.piper_tts import PiperTTSProvider, apply_studio_dsp

    provider = PiperTTSProvider()
    assert provider.length_scale == 0.85
    assert provider.noise_scale == 0.65
    assert provider.noise_w_scale == 0.75

    # Test emotive tag extraction
    clean_text, params = provider._extract_emotive_config("[calm] Hello sir.")
    assert clean_text == "Hello sir."
    assert params["length_scale"] == 1.10
    assert params["noise_scale"] == 0.55

    clean_urgent, params_urgent = provider._extract_emotive_config("[urgent] System alert.")
    assert clean_urgent == "System alert."
    assert params_urgent["length_scale"] == 0.74

    # Test DSP filter on sample PCM
    raw_pcm = b"\x00\x10\x00\x20" * 200
    dsp_pcm = apply_studio_dsp(raw_pcm, sample_rate=22050)
    assert len(dsp_pcm) == len(raw_pcm)

    # Test synthesis with tag
    chunks = []
    async for c in provider.synthesize_stream("[calm] System test."):
        chunks.append(c)
    assert len(chunks) > 0
    assert sum(len(c) for c in chunks) > 500


def test_speech_normalizer_iso_datetime_and_time():
    """Verifies that SpeechNormalizer converts ISO timestamps and timezone offsets into natural spoken English."""
    from backend.voice.tts.normalizer import SpeechNormalizer

    raw = (
        "Your next scheduled event is 'Meeting with hemanshu sir regarding NDA Points' "
        "at 2026-09-05T16:15:00+05:30. You have 5 pending tasks on your agenda."
    )
    spoken = SpeechNormalizer.normalize_for_speech(raw)

    assert "+05:30" not in spoken
    assert "2026-09-05" not in spoken
    assert "16:15:00" not in spoken
    assert "4:15 PM" in spoken
    assert "at at" not in spoken


