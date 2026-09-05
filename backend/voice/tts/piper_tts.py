"""VESPER Offline / Embedded Local Primary TTS Provider (Piper TTS).

High-speed, zero-cost neural speech engine running locally on ONNX runtime.
Default voice: Alan Brisk & Crisp (Sample 2: length_scale=0.85, 1.18x speed).
Supports multi-voice switching (Alan, Cori High, Ryan High, Semaine),
dynamic emotive tag parsing ([calm], [urgent], [whisper]), and 3-stage studio DSP mastering.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from backend.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("vesper.voice.tts.piper")

# Standard local model search paths
DEFAULT_PIPER_DIR = Path(__file__).resolve().parent.parent / "models" / "piper"

# Voice aliases mapping friendly names to (model_path, speaker_id)
VOICE_ALIASES: dict[str, tuple[Path, int]] = {
    "alan": (DEFAULT_PIPER_DIR / "en_GB-alan-medium.onnx", 0),
    "cori": (DEFAULT_PIPER_DIR / "en_GB-cori-high.onnx", 0),
    "cori_high": (DEFAULT_PIPER_DIR / "en_GB-cori-high.onnx", 0),
    "ryan": (DEFAULT_PIPER_DIR / "en_US-ryan-high.onnx", 0),
    "ryan_high": (DEFAULT_PIPER_DIR / "en_US-ryan-high.onnx", 0),
    "semaine": (DEFAULT_PIPER_DIR / "en_GB-semaine-medium.onnx", 0),
    "prudence": (DEFAULT_PIPER_DIR / "en_GB-semaine-medium.onnx", 0),
    "spike": (DEFAULT_PIPER_DIR / "en_GB-semaine-medium.onnx", 1),
    "obadiah": (DEFAULT_PIPER_DIR / "en_GB-semaine-medium.onnx", 2),
    "poppy": (DEFAULT_PIPER_DIR / "en_GB-semaine-medium.onnx", 3),
}

# Baseline tuning: Alan Sample 2 (Brisk & Crisp Butler, 1.18x speed)
DEFAULT_LENGTH_SCALE = 0.85
DEFAULT_NOISE_SCALE = 0.65
DEFAULT_NOISE_W_SCALE = 0.75
DEFAULT_VOLUME = 1.05

# Dynamic emotive tag acoustic modulation presets
EMOTIVE_PRESETS: dict[str, dict[str, float]] = {
    "calm": {"length_scale": 1.10, "noise_scale": 0.55, "noise_w_scale": 0.85, "volume": 1.00},
    "dignified": {"length_scale": 1.12, "noise_scale": 0.52, "noise_w_scale": 0.85, "volume": 1.00},
    "authoritative": {"length_scale": 0.82, "noise_scale": 0.48, "noise_w_scale": 0.70, "volume": 1.08},
    "formal": {"length_scale": 0.84, "noise_scale": 0.50, "noise_w_scale": 0.72, "volume": 1.05},
    "whisper": {"length_scale": 1.10, "noise_scale": 0.28, "noise_w_scale": 0.60, "volume": 0.65},
    "quiet": {"length_scale": 1.10, "noise_scale": 0.28, "noise_w_scale": 0.60, "volume": 0.65},
    "cheerful": {"length_scale": 0.80, "noise_scale": 0.88, "noise_w_scale": 1.05, "volume": 1.02},
    "warm": {"length_scale": 0.84, "noise_scale": 0.85, "noise_w_scale": 1.00, "volume": 1.00},
    "urgent": {"length_scale": 0.74, "noise_scale": 0.80, "noise_w_scale": 0.68, "volume": 1.12},
    "alert": {"length_scale": 0.74, "noise_scale": 0.80, "noise_w_scale": 0.68, "volume": 1.12},
    "thoughtful": {"length_scale": 0.96, "noise_scale": 0.62, "noise_w_scale": 1.15, "volume": 0.98},
    "fast": {"length_scale": 0.72, "noise_scale": 0.65, "noise_w_scale": 0.65, "volume": 1.10},
}


def apply_studio_dsp(audio_int16_bytes: bytes, sample_rate: int = 22050) -> bytes:
    """Applies a 3-stage mastering DSP filter for broadcast warmth and clarity:
    1. 80Hz Butterworth High-Pass Filter (removes sub-bass mud).
    2. 3.2kHz Peaking Presence Boost (+2.5 dB for consonant clarity).
    3. Soft-knee compression and peak normalization to -1.0 dBFS.
    """
    try:
        import numpy as np
        import scipy.signal

        samples = np.frombuffer(audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if len(samples) < 16:
            return audio_int16_bytes

        # 1. High-Pass Filter at 80 Hz (2nd order)
        sos_hp = scipy.signal.butter(2, 80, btype="highpass", fs=sample_rate, output="sos")
        filtered = scipy.signal.sosfilt(sos_hp, samples)

        # 2. Presence EQ Peaking Filter at 3.2 kHz (+2.5 dB boost)
        f0 = 3200.0
        gain_db = 2.5
        q = 1.0
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * f0 / sample_rate
        alpha = np.sin(w0) / (2.0 * q)
        b0 = 1.0 + alpha * A
        b1 = -2.0 * np.cos(w0)
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * np.cos(w0)
        a2 = 1.0 - alpha / A

        b = np.array([b0, b1, b2]) / a0
        a = np.array([a0, a1, a2]) / a0
        boosted = scipy.signal.lfilter(b, a, filtered)

        # 3. Soft-Knee Saturation & Normalization
        warmed = np.tanh(boosted * 1.15)
        max_val = np.max(np.abs(warmed))
        if max_val > 0:
            warmed = (warmed / max_val) * 0.89

        out_int16 = (warmed * 32767.0).astype(np.int16)
        return out_int16.tobytes()
    except Exception as e:
        logger.debug(f"[TTS.Piper] DSP mastering skipped: {e}")
        return audio_int16_bytes


class PiperTTSProvider(BaseTTSProvider):
    """Local Piper ONNX TTS provider with native Python SDK streaming."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w_scale: Optional[float] = None,
        volume: Optional[float] = None,
        piper_binary: Optional[str] = None,
        enable_dsp: Optional[bool] = None,
    ) -> None:
        # Resolve voice alias or model path
        voice_env = os.getenv("PIPER_VOICE", "alan").lower().strip()
        alias_info = VOICE_ALIASES.get(voice_env)

        if model_path:
            chosen_path = model_path
        elif os.getenv("PIPER_MODEL_PATH"):
            chosen_path = os.getenv("PIPER_MODEL_PATH")
        elif alias_info and alias_info[0].exists():
            chosen_path = str(alias_info[0])
        else:
            alan_path = DEFAULT_PIPER_DIR / "en_GB-alan-medium.onnx"
            chosen_path = str(alan_path if alan_path.exists() else (DEFAULT_PIPER_DIR / "en_GB-semaine-medium.onnx"))

        self.model_path = chosen_path

        if speaker_id is not None:
            self.speaker_id = speaker_id
        elif os.getenv("PIPER_SPEAKER_ID"):
            self.speaker_id = int(os.getenv("PIPER_SPEAKER_ID"))
        elif alias_info:
            self.speaker_id = alias_info[1]
        else:
            self.speaker_id = 0

        # Sample 2 default pacing & acoustics (length_scale=0.85)
        self.length_scale = float(os.getenv("PIPER_LENGTH_SCALE", str(length_scale if length_scale is not None else DEFAULT_LENGTH_SCALE)))
        self.noise_scale = float(os.getenv("PIPER_NOISE_SCALE", str(noise_scale if noise_scale is not None else DEFAULT_NOISE_SCALE)))
        self.noise_w_scale = float(os.getenv("PIPER_NOISE_W_SCALE", str(noise_w_scale if noise_w_scale is not None else DEFAULT_NOISE_W_SCALE)))
        self.volume = float(os.getenv("PIPER_VOLUME", str(volume if volume is not None else DEFAULT_VOLUME)))

        self.enable_dsp = enable_dsp if enable_dsp is not None else (os.getenv("PIPER_ENABLE_DSP", "true").lower() in ("true", "1", "yes"))
        self.piper_binary = piper_binary or shutil.which("piper") or "piper"
        self._voice_instance: Any = None

    @property
    def name(self) -> str:
        return "piper_local_tts"

    def is_available(self) -> bool:
        """Available if the model ONNX file exists on disk, or piper binary exists."""
        return os.path.exists(self.model_path) or bool(shutil.which(self.piper_binary))

    def _get_voice(self) -> Any:
        """Loads and caches the PiperVoice ONNX instance."""
        if self._voice_instance is None:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Piper ONNX model not found at: {self.model_path}")

            from piper import PiperVoice

            config_path = f"{self.model_path}.json"
            if not os.path.exists(config_path):
                config_path = None

            self._voice_instance = PiperVoice.load(
                self.model_path,
                config_path=config_path,
            )
            logger.info(
                f"[TTS.Piper] Loaded Piper voice model: {Path(self.model_path).name} "
                f"(Speaker: {self.speaker_id}, Length Scale: {self.length_scale}, DSP: {self.enable_dsp})"
            )
        return self._voice_instance

    def _extract_emotive_config(self, text: str) -> tuple[str, dict[str, float]]:
        """Detects bracketed emotion tags like [calm] or [urgent], strips them, and resolves config."""
        clean_text = text.strip()
        match = re.match(r"^\[([a-zA-Z0-9_,\s-]+)\]\s*", clean_text)
        if not match:
            return clean_text, {
                "length_scale": self.length_scale,
                "noise_scale": self.noise_scale,
                "noise_w_scale": self.noise_w_scale,
                "volume": self.volume,
            }

        tag_content = match.group(1).lower()
        clean_text = clean_text[len(match.group(0)):].strip()

        # Check tokens inside tag (e.g. "calm, articulate" -> check "calm")
        tokens = [t.strip() for t in re.split(r"[,_]+", tag_content) if t.strip()]
        resolved = {
            "length_scale": self.length_scale,
            "noise_scale": self.noise_scale,
            "noise_w_scale": self.noise_w_scale,
            "volume": self.volume,
        }

        for token in tokens:
            if token in EMOTIVE_PRESETS:
                resolved.update(EMOTIVE_PRESETS[token])
                logger.debug(f"[TTS.Piper] Detected emotion tag '[{token}]' -> modulating acoustics to {resolved}")
                break

        return clean_text, resolved

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text.strip():
            return

        if not self.is_available():
            raise RuntimeError(
                "Piper TTS is not available on this host. "
                "Ensure Piper model is downloaded or `piper` executable is in PATH."
            )

        clean_text, acoustic_params = self._extract_emotive_config(text)
        if not clean_text:
            return

        # 1. Prefer Native Python SDK
        try:
            from piper.config import SynthesisConfig

            voice = self._get_voice()
            cfg = SynthesisConfig(
                speaker_id=self.speaker_id,
                length_scale=acoustic_params["length_scale"],
                noise_scale=acoustic_params["noise_scale"],
                noise_w_scale=acoustic_params["noise_w_scale"],
                volume=acoustic_params["volume"],
            )

            sample_rate = getattr(getattr(voice, "config", None), "sample_rate", 22050)
            # 200ms human breath/pause between sentences
            inter_sentence_silence = b"\x00" * int(sample_rate * 2 * 0.20)

            has_audio = False
            for chunk in voice.synthesize(clean_text, syn_config=cfg):
                if chunk and chunk.audio_int16_bytes:
                    has_audio = True
                    audio_data = chunk.audio_int16_bytes
                    if self.enable_dsp:
                        audio_data = apply_studio_dsp(audio_data, sample_rate=sample_rate)
                    yield audio_data
                    await asyncio.sleep(0)  # Yield execution back to event loop

            if has_audio:
                yield inter_sentence_silence
            return
        except ImportError:
            logger.debug("[TTS.Piper] Native piper package not installed, falling back to CLI subprocess.")
        except Exception as e:
            logger.warning(f"[TTS.Piper] Native SDK synthesis failed ({e}), falling back to CLI subprocess.")

        # 2. CLI Subprocess Fallback
        cmd = [
            self.piper_binary,
            "--output-raw",
            "--length-scale", str(acoustic_params["length_scale"]),
            "--noise-scale", str(acoustic_params["noise_scale"]),
            "--noise-w", str(acoustic_params["noise_w_scale"]),
        ]
        if self.model_path:
            cmd.extend(["--model", self.model_path, "--speaker", str(self.speaker_id)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate(input=clean_text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"Piper execution failed: {stderr.decode('utf-8', errors='ignore')}")

        raw_out = stdout
        if self.enable_dsp:
            raw_out = apply_studio_dsp(raw_out, sample_rate=22050)

        chunk_size = 4096
        for i in range(0, len(raw_out), chunk_size):
            yield raw_out[i : i + chunk_size]
            await asyncio.sleep(0)

        # Trailing sentence pause
        yield b"\x00" * int(22050 * 2 * 0.20)

