#!/usr/bin/env python3
"""Interactive Voice Audition CLI for VESPER.

Allows listening to generated voice presets and comparing Raw vs. DSP-mastered audio.
Usage:
    python scripts/play_samples.py [preset_number] [--raw]
"""

import os
import subprocess
import sys
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "output" / "voice_samples"

PRESETS = [
    # ── Alan British Butler (Pacing & Emotive Variations) ──────────────────────
    ("alan_01_baseline_default", "Alan Baseline (Standard speed 1.0 - slow drawl)"),
    ("alan_fast_085", "Alan Brisk & Crisp (1.18x speed, length_scale=0.85)"),
    ("alan_snappy_078", "Alan Snappy Modern (1.28x speed, length_scale=0.78)"),
    ("alan_rapid_072", "Alan Rapid Briefing (1.39x speed, length_scale=0.72)"),
    ("alan_02_calm_dignified", "Alan Calm Dignified (length_scale=1.12)"),
    ("alan_03_authoritative", "Alan Authoritative Formal (length_scale=1.04)"),
    ("alan_04_whisper_subdued", "Alan Whisper Subdued (Zen Mode)"),
    ("alan_05_cheerful_warm", "Alan Cheerful Warm"),
    ("alan_06_urgent_alert", "Alan Urgent Notification"),
    ("alan_07_thoughtful_research", "Alan Thoughtful Research Cadence"),

    # ── High-Quality Studio Tier Models (Higher Fidelity) ──────────────────────
    ("cori_high_standard", "Cori High-Tier (Studio British Female - Standard 1.0)"),
    ("cori_high_crisp", "Cori High-Tier (Studio British Female - Crisp 0.88)"),
    ("ryan_high_standard", "Ryan High-Tier (Studio Deep US Male - Standard 1.0)"),
    ("ryan_high_crisp", "Ryan High-Tier (Studio Deep US Male - Crisp 0.86)"),

    # ── SEMAINE Emotional Characters ───────────────────────────────────────────
    ("semaine_08_prudence", "SEMAINE: Prudence (Pragmatic & Sensible - Standard 1.0)"),
    ("semaine_prudence_fast", "SEMAINE: Prudence (Pragmatic & Swift - Brisk 0.85)"),
    ("semaine_09_spike", "SEMAINE: Spike (Aggressive, high-energy, intense)"),
    ("semaine_10_obadiah", "SEMAINE: Obadiah (Gloomy, low-energy, mournful)"),
    ("semaine_11_poppy", "SEMAINE: Poppy (Bubbly, cheerful, outgoing)"),
]

def play_file(filepath: Path):
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return
    print(f">> Playing: {filepath.name}...")
    for cmd in ["paplay", "pw-play", "aplay"]:
        if subprocess.run(["which", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
            subprocess.run([cmd, str(filepath)])
            return
    # Fallback to ffplay
    subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(filepath)])

def main():
    use_raw = "--raw" in sys.argv
    suffix = "raw" if use_raw else "dsp_mastered"

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0].isdigit():
        idx = int(args[0]) - 1
        if 0 <= idx < len(PRESETS):
            key, name = PRESETS[idx]
            target = SAMPLE_DIR / f"{key}_{suffix}.wav"
            print(f"\nAuditioning Preset #{idx+1}: {name} [{suffix.upper()}]")
            play_file(target)
            return

    print("================================================================================")
    print("                    VESPER VOICE SAMPLES AUDITION MENU")
    print("================================================================================")
    print(f"Mode: {'[RAW]' if use_raw else '[DSP MASTERED (High Clarity)]'} (pass --raw to toggle)\n")
    for i, (key, desc) in enumerate(PRESETS, 1):
        print(f"  [{i:2d}] {desc}")
    print("\nRun: python scripts/play_samples.py <number> [--raw]")
    print("Example: python scripts/play_samples.py 2")
    print("================================================================================")

if __name__ == "__main__":
    main()
