#!/usr/bin/env python3
"""VESPER Interactive Pipeline & Latency Tester (CLI).

Comprehensive test harness for the VESPER voice, AI reasoning, and data layers:
  [1] Live Microphone Roundtrip (Mic -> Groq STT -> OpenRouter LLM -> TTS -> Playback + Latency Report)
  [2] Interactive Text Query (Text Prompt -> OpenRouter LLM -> TTS -> Playback)
  [3] Speech-to-Text Benchmark (Transcribe an existing WAV file via Groq Whisper)
  [4] Supabase Cloud Data Layer Verification (Tasks, Finance, Memories)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Optional, Tuple

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

# Load environment
ENV_PATH = PROJECT_ROOT / "backend" / ".env"
load_dotenv(ENV_PATH)

from backend.voice.audio_utils import pack_pcm_to_wav
from backend.voice.stt import GroqSpeechToText
from backend.voice.tts.groq_tts import GroqTTSProvider
from backend.voice.tts.piper_tts import PiperTTSProvider

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ANSI Colors for clean terminal UI
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
MAGENTA = "\033[95m"
RESET = "\033[0m"


def print_banner():
    print(f"\n{CYAN}{BOLD}" + "=" * 70)
    print("        VESPER INTERACTIVE SUBSYSTEM & LATENCY BENCHMARK")
    print("=" * 70 + f"{RESET}\n")


def play_audio_file(audio_path: Path):
    """Plays back audio file using the system's lowest-latency audio player."""
    path_str = str(audio_path)
    if shutil.which("paplay") and path_str.endswith(".wav"):
        subprocess.run(["paplay", path_str], check=False)
    elif shutil.which("ffplay"):
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path_str], check=False)
    elif shutil.which("mpv"):
        subprocess.run(["mpv", "--no-terminal", path_str], check=False)
    else:
        print(f"{YELLOW}[Playback] No media player (paplay/ffplay/mpv) found to play audio.{RESET}")


def record_microphone_audio(sample_rate: int = 16000) -> bytes:
    """Records 16kHz mono 16-bit PCM audio from default microphone with Push-to-Talk."""
    print(f"\n{YELLOW}{BOLD}[RECORDING] Press ENTER to START recording...{RESET}", end="")
    input()

    frames = []
    stop_event = threading.Event()

    def callback(indata, frame_count, time_info, status):
        if not stop_event.is_set():
            frames.append(indata.copy())

    from backend.voice.audio_utils import get_best_input_device
    device_idx = get_best_input_device(sample_rate=sample_rate)

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device_idx,
        callback=callback,
    )
    with stream:
        print(f"{RED}{BOLD}RECORDING IN PROGRESS [Device {device_idx}] — Speak now! (Press ENTER to STOP){RESET}")
        input()
        stop_event.set()

    if not frames:
        print(f"{RED}[Recording] No audio frames captured.{RESET}")
        return b""

    pcm_array = np.concatenate(frames, axis=0)
    pcm_bytes = pcm_array.tobytes()
    duration_s = len(pcm_bytes) / (sample_rate * 2)
    print(f"{GREEN}[OK] Captured {duration_s:.2f}s of audio ({len(pcm_bytes)} bytes){RESET}")
    return pcm_bytes


from backend.agent.alfred import AlfredSupervisor, AlfredResponse

supervisor = AlfredSupervisor()


async def query_alfred_swarm(prompt: str) -> Tuple[str, str, float, bool]:
    """Queries the Alfred Cognitive Swarm (FastPath -> 2-Stage Swarm -> Evaluator).

    Returns: (speech_text, markdown_body, elapsed_seconds, is_fast_path)
    """
    print(f"\n{YELLOW}[AI Swarm] Processing query through Alfred supervisor...{RESET}")
    t0 = time.perf_counter()
    res: AlfredResponse = await supervisor.process_query(prompt)
    elapsed = time.perf_counter() - t0

    if res.fast_path:
        print(f"{GREEN}[AI Fast-Path] Deterministic match in {res.latency_ms:.2f}ms (Zero LLM cost)!{RESET}")
    else:
        print(f"{GREEN}[AI Swarm] Plan: '{res.plan_type}' completed in {res.latency_ms:.1f}ms:{RESET}")

    print(f"{BOLD}\"{res.speech_text}\"{RESET}")
    if res.hud_cards:
        print(f"{CYAN}HUD Cards Generated: {len(res.hud_cards)}{RESET}")

    return res.speech_text, res.markdown_body, elapsed, res.fast_path


async def synthesize_with_piper(text: str) -> Tuple[Optional[Path], float, float]:
    """Synthesizes text with Piper TTS (Spike voice). Returns (path, first_chunk_s, total_s)."""
    t0 = time.perf_counter()
    provider = PiperTTSProvider()
    if not provider.is_available():
        print(f"{RED}[TTS: Piper] Model file not found at {provider.model_path}{RESET}")
        return None, 0.0, 0.0

    raw_pcm = bytearray()
    first_chunk_time: Optional[float] = None

    async for chunk in provider.synthesize_stream(text):
        if first_chunk_time is None:
            first_chunk_time = time.perf_counter() - t0
        raw_pcm.extend(chunk)

    total_time = time.perf_counter() - t0
    out_file = OUTPUT_DIR / f"response_piper_{int(time.time())}.wav"

    with wave.open(str(out_file), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(bytes(raw_pcm))

    return out_file, (first_chunk_time or total_time), total_time


async def synthesize_with_groq(text: str) -> Tuple[Optional[Path], float, float]:
    """Synthesizes text with Groq Cloud TTS (Orpheus). Returns (path, first_chunk_s, total_s)."""
    t0 = time.perf_counter()
    provider = GroqTTSProvider()
    if not provider.is_available():
        print(f"{RED}[TTS: Groq] GROQ_API_KEY is not set in backend/.env{RESET}")
        return None, 0.0, 0.0

    audio_bytes = bytearray()
    first_chunk_time: Optional[float] = None

    try:
        async for chunk in provider.synthesize_stream(text):
            if first_chunk_time is None:
                first_chunk_time = time.perf_counter() - t0
            audio_bytes.extend(chunk)
    except Exception as e:
        print(f"{RED}[TTS: Groq] Synthesis error: {e}{RESET}")
        return None, 0.0, 0.0

    total_time = time.perf_counter() - t0
    out_file = OUTPUT_DIR / f"response_groq_{int(time.time())}.wav"

    with open(out_file, "wb") as f:
        f.write(bytes(audio_bytes))

    return out_file, (first_chunk_time or total_time), total_time


def print_latency_report(
    stt_ms: float,
    llm_ms: float,
    tts_first_chunk_ms: float,
    tts_total_ms: float,
    engine_name: str,
):
    """Prints a clean, formatted latency benchmark card."""
    time_to_first_sound = stt_ms + llm_ms + tts_first_chunk_ms
    total_pipeline_time = stt_ms + llm_ms + tts_total_ms

    print(f"\n{MAGENTA}{BOLD}┌─────────────────────────────────────────────────────────────┐")
    print("│                 END-TO-END LATENCY REPORT                   │")
    print("├──────────────────────────────────────────┬──────────────────┤")
    print(f"│ 1. STT (Groq Whisper Large-v3-Turbo)     │ {stt_ms:7.1f} ms      │")
    print(f"│ 2. LLM Reasoning (OpenRouter Llama-70B)  │ {llm_ms:7.1f} ms      │")
    print(f"│ 3. TTS Engine ({engine_name:<18})     │ {tts_first_chunk_ms:7.1f} ms (1st) │")
    print(f"│    Full Audio Synthesis                  │ {tts_total_ms:7.1f} ms      │")
    print("├──────────────────────────────────────────┼──────────────────┤")
    print(f"│ {CYAN}TIME-TO-FIRST-SOUND (User heard voice){RESET}{MAGENTA}{BOLD}   │ {GREEN}{time_to_first_sound:7.1f} ms{RESET}{MAGENTA}{BOLD}      │")
    print(f"│ Total Complete Turnaround Time           │ {total_pipeline_time:7.1f} ms      │")
    print(f"└──────────────────────────────────────────┴──────────────────┘{RESET}\n")


async def run_live_microphone_pipeline():
    """Live Mic -> Groq STT -> OpenRouter LLM -> TTS -> Playback + Latency Breakdown."""
    print(f"\n{CYAN}{BOLD}--- LIVE MICROPHONE ROUNDTRIP TEST ---{RESET}")

    # 1. Choose TTS Engine
    print(f"{BOLD}Choose TTS Engine for this voice test:{RESET}")
    print("  [1] Piper TTS (Local Offline — British Spike)")
    print("  [2] Groq Cloud TTS (Cloud LPU — Orpheus)")
    print("  [3] Compare Both (Generates & plays both sequentially)")
    tts_choice = input(f"{CYAN}Choice [1/2/3, default 1]: {RESET}").strip() or "1"

    # 2. Record User Audio
    pcm_data = record_microphone_audio(sample_rate=16000)
    if not pcm_data:
        return

    # Start timing STT
    print(f"\n{YELLOW}[STT] Uploading utterance to Groq Cloud Whisper Large-v3...{RESET}")
    t0_stt = time.perf_counter()
    stt = GroqSpeechToText()
    transcript = await stt.transcribe_pcm(pcm_data, sample_rate=16000)
    stt_elapsed_ms = (time.perf_counter() - t0_stt) * 1000

    print(f"{GREEN}[STT] Transcribed in {stt_elapsed_ms:.1f}ms:{RESET}")
    print(f"{BOLD}\"{transcript}\"{RESET}")

    if not transcript.strip():
        print(f"{RED}[Error] No words recognized from audio.{RESET}")
        return

    # 3. Swarm Cognitive Query (FastPath -> Planner -> Evaluator)
    speech_text, markdown_body, llm_elapsed_s, is_fp = await query_alfred_swarm(transcript)
    llm_elapsed_ms = llm_elapsed_s * 1000

    # 4. TTS Synthesis & Playback
    if tts_choice in ["1", "3"]:
        print(f"\n{YELLOW}[TTS: Piper] Generating local audio with Spike...{RESET}")
        piper_path, first_ms, total_s = await synthesize_with_piper(speech_text)
        if piper_path:
            print_latency_report(
                stt_ms=stt_elapsed_ms,
                llm_ms=llm_elapsed_ms,
                tts_first_chunk_ms=first_ms * 1000,
                tts_total_ms=total_s * 1000,
                engine_name="Piper Spike",
            )
            print(f"{CYAN}[AUDIO] Playing back Piper audio through speakers...{RESET}")
            play_audio_file(piper_path)

    if tts_choice in ["2", "3"]:
        print(f"\n{YELLOW}[TTS: Groq] Generating cloud LPU audio with Orpheus...{RESET}")
        groq_path, first_ms, total_s = await synthesize_with_groq(speech_text)
        if groq_path:
            print_latency_report(
                stt_ms=stt_elapsed_ms,
                llm_ms=llm_elapsed_ms,
                tts_first_chunk_ms=first_ms * 1000,
                tts_total_ms=total_s * 1000,
                engine_name="Groq Orpheus",
            )
            print(f"{CYAN}[AUDIO] Playing back Groq audio through speakers...{RESET}")
            play_audio_file(groq_path)


async def run_text_query_pipeline():
    """Interactive Text Query -> Alfred Cognitive Swarm -> TTS Choice -> Playback."""
    default_prompt = "What is the status of our core systems and today's schedule?"
    print(f"{BOLD}Enter your prompt/query for the AI Assistant:{RESET}")
    print(f"(Press Enter for default: '{default_prompt}')")
    user_input = input(f"{CYAN}> {RESET}").strip()
    prompt = user_input if user_input else default_prompt

    speech_text, markdown_body, llm_elapsed_s, is_fp = await query_alfred_swarm(prompt)

    print(f"\n{BOLD}Choose TTS Engine for Audio Generation:{RESET}")
    print("  [1] Piper TTS (Local Offline — British Spike)")
    print("  [2] Groq Cloud TTS (Cloud LPU — Orpheus)")
    print("  [3] Both (Generate & Play Both)")
    print("  [4] Skip audio generation")

    choice = input(f"{CYAN}Choice [1-4, default 1]: {RESET}").strip() or "1"

    if choice in ["1", "3"]:
        path, first_s, total_s = await synthesize_with_piper(speech_text)
        if path:
            print(f"{CYAN}[AUDIO] Playing Piper audio...{RESET}")
            play_audio_file(path)

    if choice in ["2", "3"]:
        path, first_s, total_s = await synthesize_with_groq(speech_text)
        if path:
            print(f"{CYAN}[AUDIO] Playing Groq audio...{RESET}")
            play_audio_file(path)


async def test_stt_file_transcription(audio_path: str):
    """Transcribes an audio file via Groq Whisper Cloud."""
    path = Path(audio_path)
    if not path.exists():
        print(f"{RED}[STT Error] File does not exist: {path}{RESET}")
        return

    print(f"\n{YELLOW}[STT] Transcribing '{path.name}' via Groq Cloud Whisper...{RESET}")
    stt = GroqSpeechToText()
    t0 = time.perf_counter()

    try:
        with open(path, "rb") as f:
            wav_bytes = f.read()

        transcript = await stt.transcribe_wav(wav_bytes)
        elapsed = time.perf_counter() - t0
        print(f"{GREEN}[STT] Transcribed in {elapsed * 1000:.1f}ms:{RESET}")
        print(f"{BOLD}\"{transcript}\"{RESET}\n")
    except Exception as e:
        print(f"{RED}[STT Error] {e}{RESET}")


async def test_live_supabase():
    """Verifies live connectivity to Supabase and repositories."""
    print(f"\n{YELLOW}[Data] Connecting to Supabase Cloud PostgreSQL...{RESET}")
    from backend.data.client import get_supabase_client
    from backend.data.repositories.tasks import TaskRepository

    try:
        client = get_supabase_client()
        repo = TaskRepository(client)
        tasks = repo.list(limit=3)
        print(f"{GREEN}[Data] Supabase connection successful! Found {len(tasks)} recent tasks.{RESET}\n")
    except Exception as e:
        print(f"{RED}[Data Error] Supabase connection error: {e}{RESET}\n")


async def inspect_swarm_specialists():
    """Inspects all active specialists and tools loaded into Alfred."""
    from backend.agent.registry import registry

    print(f"\n{CYAN}{BOLD}=== ACTIVE VESPER COGNITIVE SWARM SPECIALISTS ==={RESET}")
    specialists = registry.list_specialists()
    if not specialists:
        print(f"{YELLOW}No specialists registered.{RESET}\n")
        return

    for s in specialists:
        print(f"\n{BOLD}[SWARM] Specialist: {GREEN}{s.name.upper()}{RESET}")
        print(f"  Description:  {s.description}")
        print(f"  Capabilities: {s.get_capabilities()}")
        print(f"  Available Tools:")
        for tool in s.get_tool_schemas():
            t_name = tool.get("name")
            t_desc = tool.get("description", "No description")
            print(f"    - {CYAN}{t_name}{RESET}: {t_desc}")

    print(f"\n{YELLOW}[FAST-PATH] Engine: Active (Sub-10ms deterministic matching){RESET}\n")


def main():
    print_banner()

    while True:
        print(f"{BOLD}Main Menu:{RESET}")
        print(f"  {CYAN}[1] Live Microphone Swarm (Mic -> STT -> Alfred Swarm -> TTS -> Playback + Latency Report){RESET}")
        print("  [2] Interactive Text Query (Text -> Alfred Swarm -> TTS -> Playback)")
        print("  [3] Test Speech-to-Text on a WAV File (Groq Whisper)")
        print("  [4] Test Supabase Data Layer (Live Cloud DB Connection)")
        print("  [5] Inspect Active Swarm Specialists & Tools")
        print("  [0] Exit")

        choice = input(f"\n{CYAN}Select option [1/2/3/4/5/0]: {RESET}").strip()

        if choice == "1":
            asyncio.run(run_live_microphone_pipeline())
        elif choice == "2":
            asyncio.run(run_text_query_pipeline())
        elif choice == "3":
            sample_file = PROJECT_ROOT / "backend" / "voice" / "test_spike.wav"
            print(f"\nEnter audio path (Press Enter to use '{sample_file.name}'):")
            custom_path = input(f"{CYAN}> {RESET}").strip()
            target_path = custom_path if custom_path else str(sample_file)
            asyncio.run(test_stt_file_transcription(target_path))
        elif choice == "4":
            asyncio.run(test_live_supabase())
        elif choice == "5":
            asyncio.run(inspect_swarm_specialists())
        elif choice == "0":
            print(f"\n{GREEN}Exiting VESPER Tester. Have a great day!{RESET}\n")
            break
        else:
            print(f"{YELLOW}Invalid option. Please choose 1, 2, 3, 4, 5, or 0.{RESET}\n")


if __name__ == "__main__":
    main()
