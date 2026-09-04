"""VESPER Audio Utilities.

Handles PCM frame slicing (10/20/30ms for WebRTC VAD), in-memory WAV container
generation for Groq Whisper STT, and Base64 WebSocket audio transport serialization.
"""

from __future__ import annotations

import base64
import io
import struct
import wave
from typing import Generator, List, Tuple


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


def combine_wav_streams(wav_bytes: bytes) -> bytes:
    """Combines multiple concatenated WAV files into a single valid WAV stream.

    When TTSManager synthesizes sentence-by-sentence with a WAV-producing provider
    (e.g. Groq Orpheus), the stream chunks can contain multiple RIFF headers concatenated together.
    This helper extracts their PCM frames and packages them under a single unified WAV header.
    """
    riff_indices: List[int] = []
    idx = 0
    while True:
        pos = wav_bytes.find(b"RIFF", idx)
        if pos == -1:
            break
        if pos + 12 <= len(wav_bytes) and wav_bytes[pos + 8 : pos + 12] == b"WAVE":
            riff_indices.append(pos)
        idx = pos + 4

    if len(riff_indices) <= 1:
        return wav_bytes

    pcm_frames: List[bytes] = []
    sample_rate = 24000
    channels = 1
    sample_width = 2

    for i, start_pos in enumerate(riff_indices):
        end_pos = riff_indices[i + 1] if i + 1 < len(riff_indices) else len(wav_bytes)
        chunk_slice = wav_bytes[start_pos:end_pos]
        try:
            with wave.open(io.BytesIO(chunk_slice), "rb") as w:
                sample_rate = w.getframerate()
                channels = w.getnchannels()
                sample_width = w.getsampwidth()
                pcm_frames.append(w.readframes(w.getnframes()))
        except Exception:
            pass

    if pcm_frames:
        all_pcm = b"".join(pcm_frames)
        return pack_pcm_to_wav(all_pcm, sample_rate=sample_rate, channels=channels, sample_width=sample_width)
    return wav_bytes


def prepare_audio_for_playback(chunks: List[bytes], default_pcm_rate: int = 22050) -> Tuple[bytes, str]:
    """Inspects TTS audio stream chunks, fixes stream formatting, and determines file extension.

    1. If MP3 (starts with ID3 or MPEG frame sync 0xFF 0xFB/F3/F2), returns (bytes, '.mp3').
    2. If WAV (starts with RIFF....WAVE), fixes multiple concatenated RIFF headers and returns (bytes, '.wav').
    3. If Ogg (starts with OggS), returns (bytes, '.ogg').
    4. If raw PCM (Piper TTS), wraps into a valid WAV container and returns (bytes, '.wav').
    """
    if not chunks:
        return b"", ".wav"

    raw = b"".join(chunks)
    if not raw:
        return b"", ".wav"

    # Check for MP3: ID3 container tag or MPEG frame sync header
    if raw.startswith(b"ID3") or (len(raw) >= 4 and raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0):
        return raw, ".mp3"

    # Check for Ogg Vorbis / Opus container
    if raw.startswith(b"OggS"):
        return raw, ".ogg"

    # Check for WAV container
    if raw.startswith(b"RIFF") and len(raw) >= 12 and raw[8:12] == b"WAVE":
        cleaned = combine_wav_streams(raw)
        return cleaned, ".wav"

    # Fallback: Treat as raw 16-bit PCM (e.g. from local Piper ONNX) and wrap in WAV header
    wav_bytes = pack_pcm_to_wav(raw, sample_rate=default_pcm_rate, channels=1, sample_width=2)
    return wav_bytes, ".wav"


def encode_base64_audio(audio_bytes: bytes) -> str:
    """Encodes binary audio bytes into an ASCII Base64 string."""
    return base64.b64encode(audio_bytes).decode("ascii")


def decode_base64_audio(base64_str: str) -> bytes:
    """Decodes a Base64 string into binary audio bytes."""
    return base64.b64decode(base64_str)


def get_best_input_device(sample_rate: int = 16000) -> int | None:
    """Discovers the optimal microphone capture device index safely.

    On modern Linux distributions (Arch, Fedora, Ubuntu) running PipeWire,
    querying/probing via check_input_settings can trigger instability in
    libspa-audioconvert. Instead, we match the device index by name.
    """
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception:
        return None

    # 1. Prefer explicit PipeWire or PulseAudio bridge
    for idx, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            name = str(d.get("name", "")).lower()
            if "pipewire" in name or "pulse" in name:
                return idx

    # 2. Prefer hardware digital microphone / USB mic
    for idx, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            name = str(d.get("name", "")).lower()
            if any(k in name for k in ["digital mic", "microphone", "mic", "respeaker", "usb"]):
                return idx

    return None


