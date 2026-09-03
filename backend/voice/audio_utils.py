"""VESPER Audio Utilities.

Handles PCM frame slicing (10/20/30ms for WebRTC VAD), in-memory WAV container
generation for Groq Whisper STT, and Base64 WebSocket audio transport serialization.
"""

from __future__ import annotations

import base64
import io
import struct
import wave
from typing import Generator, List


def frame_pcm(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    frame_duration_ms: int = 30,
) -> Generator[bytes, None, None]:
    """Slices raw 16-bit PCM bytes into uniform frames for VAD processing.

    WebRTC VAD only accepts 10ms, 20ms, or 30ms frames.
    For 16kHz 16-bit mono:
      - 10ms = 160 samples = 320 bytes
      - 20ms = 320 samples = 640 bytes
      - 30ms = 480 samples = 960 bytes
    """
    bytes_per_sample = 2  # 16-bit = 2 bytes
    samples_per_frame = int(sample_rate * (frame_duration_ms / 1000.0))
    frame_size = samples_per_frame * bytes_per_sample

    offset = 0
    while offset + frame_size <= len(pcm_bytes):
        yield pcm_bytes[offset : offset + frame_size]
        offset += frame_size


def pack_pcm_to_wav(
    pcm_data: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wraps raw 16-bit PCM byte stream into a valid in-memory WAV container."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_io.getvalue()


def encode_base64_audio(audio_bytes: bytes) -> str:
    """Encodes binary audio bytes into an ASCII Base64 string."""
    return base64.b64encode(audio_bytes).decode("ascii")


def decode_base64_audio(base64_str: str) -> bytes:
    """Decodes a Base64 string into binary audio bytes."""
    return base64.b64decode(base64_str)
