#!/usr/bin/env python3
"""VESPER Voice & Emotion Test Generator.

Generates comparative audio samples across:
1. Alan model with emotional presets (calm, authoritative, whisper, urgent, cheerful, thoughtful)
2. SEMAINE model with emotional characters (Prudence, Spike, Obadiah, Poppy)
3. DSP Post-Processing Enhancement (Raw vs. Studio Enhanced)
"""

import io
import os
import sys
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import scipy.signal

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from piper import PiperVoice
from piper.config import SynthesisConfig

OUTPUT_DIR = PROJECT_ROOT / "output" / "voice_samples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = PROJECT_ROOT / "backend" / "voice" / "models" / "piper"
ALAN_MODEL = MODEL_DIR / "en_GB-alan-medium.onnx"
SEMAINE_MODEL = MODEL_DIR / "en_GB-semaine-medium.onnx"

SAMPLE_TEXT = (
    "Good day, sir. All background sentries are operational, and your schedule for today is clear. "
    "However, we have detected a slight unexpected anomaly in the local cluster."
)

EMOTIVE_CONFIGS = {
    "alan_01_baseline_default": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.0, noise_scale=0.667, noise_w_scale=0.8),
        "desc": "Standard Alan British Butler baseline (unmodified).",
    },
    "alan_02_calm_dignified": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.12, noise_scale=0.55, noise_w_scale=0.85, volume=1.0),
        "desc": "Paced, slow, dignified, composed butler tone.",
    },
    "alan_03_authoritative": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.04, noise_scale=0.48, noise_w_scale=0.72, volume=1.05),
        "desc": "Firm, crisp, decisive, executive briefing tone.",
    },
    "alan_04_whisper_subdued": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.15, noise_scale=0.28, noise_w_scale=0.60, volume=0.65),
        "desc": "Quiet, subdued, intimate, low pitch-variance tone for Zen Mode.",
    },
    "alan_05_cheerful_warm": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.94, noise_scale=0.88, noise_w_scale=1.05, volume=1.0),
        "desc": "Vibrant, warm, upbeat, expressive inflection.",
    },
    "alan_06_urgent_alert": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.86, noise_scale=0.80, noise_w_scale=0.68, volume=1.10),
        "desc": "Brisk, fast, alert pacing for notifications & warnings.",
    },
    "alan_07_thoughtful_research": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.18, noise_scale=0.62, noise_w_scale=1.20, volume=0.98),
        "desc": "Reflective, pausing between clauses, ideal for research summaries.",
    },
    "semaine_08_prudence": {
        "model": SEMAINE_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.0, noise_scale=0.667, noise_w_scale=0.8),
        "desc": "SEMAINE Character: Prudence (Pragmatic, sensible, even-tempered).",
    },
    "semaine_09_spike": {
        "model": SEMAINE_MODEL,
        "speaker_id": 1,
        "config": SynthesisConfig(length_scale=0.92, noise_scale=0.85, noise_w_scale=0.8),
        "desc": "SEMAINE Character: Spike (Energetic, intense, assertive).",
    },
    "semaine_10_obadiah": {
        "model": SEMAINE_MODEL,
        "speaker_id": 2,
        "config": SynthesisConfig(length_scale=1.15, noise_scale=0.45, noise_w_scale=0.7),
        "desc": "SEMAINE Character: Obadiah (Gloomy, low-energy, mournful).",
    },
    "semaine_11_poppy": {
        "model": SEMAINE_MODEL,
        "speaker_id": 3,
        "config": SynthesisConfig(length_scale=0.92, noise_scale=0.90, noise_w_scale=1.0),
        "desc": "SEMAINE Character: Poppy (Cheerful, optimistic, enthusiastic).",
    },
}

def apply_studio_dsp(audio_int16_bytes: bytes, sample_rate: int = 22050) -> bytes:
    """Applies a 3-stage mastering DSP filter for warmth and clarity:
    1. 80Hz Butterworth High-Pass Filter (removes sub-bass mud).
    2. 3.2kHz Peaking Presence Boost (+2.5 dB for consonant clarity).
    3. Soft-knee compression and peak normalization to -1.0 dBFS.
    """
    samples = np.frombuffer(audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if len(samples) == 0:
        return audio_int16_bytes

    # 1. High-Pass Filter at 80 Hz (2nd order)
    sos_hp = scipy.signal.butter(2, 80, btype="highpass", fs=sample_rate, output="sos")
    filtered = scipy.signal.sosfilt(sos_hp, samples)

    # 2. Presence EQ Peaking Filter at 3.2 kHz (+2.5 dB boost)
    # Simple IIR peaking biquad
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

    # 3. Soft-Knee Saturation & Normalization (Analog Warmth)
    # Tanh curve creates gentle soft-clipping instead of harsh digital wrapping
    warmed = np.tanh(boosted * 1.15)
    max_val = np.max(np.abs(warmed))
    if max_val > 0:
        # Normalize to 0.89 (-1 dBFS)
        warmed = (warmed / max_val) * 0.89

    out_int16 = (warmed * 32767.0).astype(np.int16)
    return out_int16.tobytes()

def save_wav(file_path: Path, pcm_bytes: bytes, sample_rate: int = 22050):
    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

def main():
    print("================================================================================")
    print("           VESPER VOICE & EMOTION SYNTHESIS LAB (TEST GENERATOR)")
    print("================================================================================")
    print(f"Test Phrase:\n\"{SAMPLE_TEXT}\"\n")
    print(f"Output Directory: {OUTPUT_DIR}\n")

    loaded_voices = {}

    results = []

    for key, spec in EMOTIVE_CONFIGS.items():
        model_path = spec["model"]
        if not model_path.exists():
            print(f"Skipping {key}: model not found at {model_path}")
            continue

        if str(model_path) not in loaded_voices:
            print(f"Loading model into memory: {model_path.name}...")
            loaded_voices[str(model_path)] = PiperVoice.load(str(model_path))

        voice = loaded_voices[str(model_path)]
        cfg = spec["config"]
        cfg.speaker_id = spec["speaker_id"]

        t0 = time.perf_counter()
        raw_chunks = []
        for chunk in voice.synthesize(SAMPLE_TEXT, syn_config=cfg):
            if chunk and chunk.audio_int16_bytes:
                raw_chunks.append(chunk.audio_int16_bytes)
        t1 = time.perf_counter()

        raw_pcm = b"".join(raw_chunks)
        sample_rate = getattr(getattr(voice, "config", None), "sample_rate", 22050)
        dur = len(raw_pcm) / (sample_rate * 2)
        gen_time_ms = (t1 - t0) * 1000
        rtf = (t1 - t0) / dur if dur > 0 else 0

        # Save standard raw WAV
        raw_out = OUTPUT_DIR / f"{key}_raw.wav"
        save_wav(raw_out, raw_pcm, sample_rate=sample_rate)

        # Apply DSP Studio Mastering
        dsp_pcm = apply_studio_dsp(raw_pcm, sample_rate=sample_rate)
        dsp_out = OUTPUT_DIR / f"{key}_dsp_mastered.wav"
        save_wav(dsp_out, dsp_pcm, sample_rate=sample_rate)

        print(f"Generated [{key}]:")
        print(f"  • Description: {spec['desc']}")
        print(f"  • Gen Time: {gen_time_ms:.1f}ms | Audio: {dur:.2f}s | RTF: {rtf:.3f}")
        print(f"  • Files: {raw_out.name} & {dsp_out.name}\n")

        results.append({
            "key": key,
            "desc": spec["desc"],
            "raw_file": str(raw_out),
            "dsp_file": str(dsp_out),
            "gen_time_ms": gen_time_ms,
            "audio_dur_s": dur,
            "rtf": rtf,
        })

    print("================================================================================")
    print("All 11 voice presets generated with raw and DSP-mastered audio files!")
    print(f"Samples saved to: {OUTPUT_DIR}")
    print("================================================================================")

if __name__ == "__main__":
    main()
