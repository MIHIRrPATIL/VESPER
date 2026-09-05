#!/usr/bin/env python3
"""VESPER High-Quality & Fast Voice Synthesis Generator.

Generates comparative audio samples for:
1. Alan at faster, crisper pacing (length_scale = 0.85, 0.78, 0.72)
2. High-Quality Tier Voices (en_GB-cori-high, en_US-ryan-high)
3. SEMAINE at faster brisk pacing
"""

import os
import sys
import time
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from piper import PiperVoice
from piper.config import SynthesisConfig

from scripts.generate_voice_samples import apply_studio_dsp, save_wav, SAMPLE_TEXT, OUTPUT_DIR

MODEL_DIR = PROJECT_ROOT / "backend" / "voice" / "models" / "piper"
ALAN_MODEL = MODEL_DIR / "en_GB-alan-medium.onnx"
SEMAINE_MODEL = MODEL_DIR / "en_GB-semaine-medium.onnx"
CORI_HIGH = MODEL_DIR / "en_GB-cori-high.onnx"
RYAN_HIGH = MODEL_DIR / "en_US-ryan-high.onnx"

NEW_PRESETS = {
    "alan_fast_085": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.85, noise_scale=0.65, noise_w_scale=0.75, volume=1.05),
        "desc": "Alan (Brisk & Crisp Butler) - length_scale=0.85 (1.18x speed)",
    },
    "alan_snappy_078": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.78, noise_scale=0.65, noise_w_scale=0.70, volume=1.08),
        "desc": "Alan (Snappy Modern Assistant) - length_scale=0.78 (1.28x speed)",
    },
    "alan_rapid_072": {
        "model": ALAN_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.72, noise_scale=0.65, noise_w_scale=0.65, volume=1.10),
        "desc": "Alan (Rapid Briefing Pacing) - length_scale=0.72 (1.39x speed)",
    },
    "cori_high_standard": {
        "model": CORI_HIGH,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.0, noise_scale=0.667, noise_w_scale=0.8),
        "desc": "Cori High-Tier (Studio British Female) - Standard speed (1.0)",
    },
    "cori_high_crisp": {
        "model": CORI_HIGH,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.88, noise_scale=0.65, noise_w_scale=0.75, volume=1.05),
        "desc": "Cori High-Tier (Studio British Female) - Crisp speed (0.88)",
    },
    "ryan_high_standard": {
        "model": RYAN_HIGH,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=1.0, noise_scale=0.667, noise_w_scale=0.8),
        "desc": "Ryan High-Tier (Studio Deep US Male) - Standard speed (1.0)",
    },
    "ryan_high_crisp": {
        "model": RYAN_HIGH,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.86, noise_scale=0.65, noise_w_scale=0.75, volume=1.05),
        "desc": "Ryan High-Tier (Studio Deep US Male) - Crisp speed (0.86)",
    },
    "semaine_prudence_fast": {
        "model": SEMAINE_MODEL,
        "speaker_id": 0,
        "config": SynthesisConfig(length_scale=0.85, noise_scale=0.65, noise_w_scale=0.75),
        "desc": "SEMAINE: Prudence (Pragmatic & Swift) - length_scale=0.85",
    },
}

def main():
    print("================================================================================")
    print("       VESPER HIGH-QUALITY & FAST PACING VOICE GENERATOR")
    print("================================================================================")
    loaded_voices = {}

    for key, spec in NEW_PRESETS.items():
        model_path = spec["model"]
        if not model_path.exists():
            print(f"Skipping {key}: model not found at {model_path}")
            continue

        if str(model_path) not in loaded_voices:
            print(f"Loading {model_path.name}...")
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

        raw_out = OUTPUT_DIR / f"{key}_raw.wav"
        save_wav(raw_out, raw_pcm, sample_rate=sample_rate)

        dsp_pcm = apply_studio_dsp(raw_pcm, sample_rate=sample_rate)
        dsp_out = OUTPUT_DIR / f"{key}_dsp_mastered.wav"
        save_wav(dsp_out, dsp_pcm, sample_rate=sample_rate)

        print(f"Generated [{key}]:")
        print(f"  • {spec['desc']}")
        print(f"  • Gen Time: {gen_time_ms:.1f}ms | Audio: {dur:.2f}s | RTF: {rtf:.3f}")
        print(f"  • Files: {raw_out.name} & {dsp_out.name}\n")

    print("High-quality & Fast voice generation complete!")

if __name__ == "__main__":
    main()
