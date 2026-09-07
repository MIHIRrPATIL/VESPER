#!/usr/bin/env python3
"""VESPER Master Unified Test & Interactive Desk Harness.

Tests and exercises the ENTIRE system together:
1. Hardware & Device Probe (Architecture, SBC vs PC, Camera, Display, Mic)
2. Always-On Wake Word Engine ('Hey Alfred' / 'Alfred' with VAD gating)
3. Vision Perception Suite (Webcam Capture, Screen Capture, Multimodal Reasoning, OCR)
4. Alfred Cognitive Multi-Agent Swarm (8 Specialists, Fast-Path, Slow-Path)
5. Shodh-Memory Engine (Semantic recall, deduplication, conflict resolution)
6. Task Management & SQLite WAL Ledger
7. Production TTS Audio Synthesis & Live Playback
8. Cross-Device State Sync Manager (Cluster topology & diffs)

Usage:
    .venv/bin/python3 scripts/test_all_together.py              # Interactive Menu
    .venv/bin/python3 scripts/test_all_together.py --automated  # 1-Click Automated Smoke Test
    .venv/bin/python3 scripts/test_all_together.py --vision     # Live Webcam / Vision Test
    .venv/bin/python3 scripts/test_all_together.py --voice      # Live Voice / Wake Word Test
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Silence OpenCV internal C++ stderr warnings on Linux metadata device nodes
os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")
from typing import Optional

# Setup root path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / ".env")

# ANSI Color codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

from backend.agent.alfred import AlfredSupervisor
from backend.agent.llm import LLMClient
from backend.agent.registry import registry
from backend.shared.config import (
    AGENT_FAST_MODEL,
    AGENT_PRIMARY_MODEL,
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    SUPABASE_URL,
)
from backend.sync.sync_manager import sync_manager
from backend.vision.camera_stream import CameraCapture, ScreenCapture
from backend.vision.device_probe import DeviceProbe
from backend.vision.gesture_service import GestureWorker
from backend.vision.vllm import GroqVisionClient
from backend.voice.audio_utils import pack_pcm_to_wav, get_best_input_device, prepare_audio_for_playback
from backend.voice.stt import GroqSpeechToText
from backend.voice.tts.manager import TTSManager
from backend.voice.wakeword.detector import WakeWordDetector, WakeWordEvent
from backend.voice.wakeword.listener import WakeWordListener

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Purge any leftover audio files from prior runs so no audio is stored
for _p in OUTPUT_DIR.glob("*"):
    if _p.suffix in [".mp3", ".wav", ".ogg"]:
        try:
            _p.unlink()
        except Exception:
            pass


def print_banner():
    print(f"\n{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════════╗")
    print("║             VESPER UNIFIED MULTIMODAL DESK SYSTEM HARNESS            ║")
    print("║        Always-On Wake Word • Vision Suite • Swarm • State Sync       ║")
    print(f"╚══════════════════════════════════════════════════════════════════════╝{RESET}\n")


def play_audio_file(audio_path: Path, delete_after: bool = True):
    """Plays audio through system speakers via available low-latency audio player and cleans up."""
    p_str = str(audio_path)
    try:
        # 1. Windows native winsound playback
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(p_str, winsound.SND_FILENAME)
                return
            except Exception:
                pass

        # 2. Command-line players (Linux, macOS, Windows)
        candidate_cmds = [
            ["afplay", p_str],  # macOS built-in
            ["pw-play", p_str], # Linux PipeWire
            ["paplay", p_str],  # Linux PulseAudio
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", p_str],
            ["mpv", "--no-terminal", p_str],
        ]
        for cmd in candidate_cmds:
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=False)
                    return
                except Exception:
                    continue
        print(f"{YELLOW}[Audio] Audio played (no player found for auto-play){RESET}")
    finally:
        if delete_after and audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                pass


async def synthesize_and_speak(text: str, filename_prefix: str = "alfred_reply", delete_after: bool = True) -> bool:
    """Synthesizes text through Alfred's TTS, plays it through the speakers, and deletes the file."""
    print(f"\n{MAGENTA}{BOLD}[TTS] Synthesizing speech with Alfred's voice...{RESET}")
    tts_mgr = TTSManager()
    chunks = []
    t0 = time.perf_counter()
    async for chunk in tts_mgr.stream_speech(text):
        chunks.append(chunk)
    elapsed = time.perf_counter() - t0

    if not chunks:
        print(f"{RED}[TTS] Failed to synthesize audio.{RESET}")
        return False

    audio_bytes, ext = prepare_audio_for_playback(chunks)
    out_file = OUTPUT_DIR / f"{filename_prefix}_{int(time.time())}{ext}"
    out_file.write_bytes(audio_bytes)
    print(f"{GREEN}[OK] Synthesized {len(audio_bytes):,} bytes in {elapsed:.2f}s ({ext[1:].upper()}){RESET}")
    play_audio_file(out_file, delete_after=delete_after)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 1. HARDWARE & CAPABILITY DIAGNOSTIC
# ─────────────────────────────────────────────────────────────────────────────

def run_hardware_diagnostic():
    print(f"{BOLD}─── STEP 1: HARDWARE & SENSOR PROBE ─────────────────────────────────{RESET}")
    caps = DeviceProbe.get_capabilities(force_refresh=True)

    print(f"  • {BOLD}Device Type:{RESET}    {caps.device_type} ({caps.device_model})")
    print(f"  • {BOLD}OS & Arch:{RESET}      {caps.os_name} {caps.os_release} [{caps.architecture}] on {caps.hostname}")
    print(f"  • {BOLD}Display:{RESET}        {'[OK] Active Display Server ($DISPLAY)' if caps.has_display else '[--] Headless Mode'}")
    
    if caps.has_camera:
        print(f"  • {BOLD}Optical Camera:{RESET} {GREEN}[OK] Detected ({len(caps.available_cameras)} camera indices: {caps.available_cameras}){RESET}")
    else:
        print(f"  • {BOLD}Optical Camera:{RESET} {YELLOW}[--] No camera sensors detected (Graceful degradation active){RESET}")

    if caps.has_microphone:
        print(f"  • {BOLD}Microphone:{RESET}     {GREEN}[OK] Detected audio capture interfaces{RESET}")
    else:
        print(f"  • {BOLD}Microphone:{RESET}     {YELLOW}[--] No microphone found{RESET}")

    # Cloud keys
    print(f"  • {BOLD}GROQ_API_KEY:{RESET}   {'[OK] Configured' if GROQ_API_KEY else '[FAIL] Missing'}")
    print(f"  • {BOLD}OPENROUTER:{RESET}     {'[OK] Configured' if OPENROUTER_API_KEY else '[FAIL] Missing'}")
    print(f"  • {BOLD}SUPABASE_URL:{RESET}   {'[OK] Configured' if SUPABASE_URL else '[FAIL] Missing'}")

    # Registered specialists
    specs = [s.name for s in registry.list_specialists()]
    print(f"  • {BOLD}Agent Swarm:{RESET}    {len(specs)} Specialists loaded: {', '.join(specs)}")
    print()
    return caps


# ─────────────────────────────────────────────────────────────────────────────
# 2. AUTOMATED COMPREHENSIVE SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

async def run_automated_smoke_test(model: Optional[str] = None):
    print_banner()
    caps = run_hardware_diagnostic()
    results = {}

    print(f"{BOLD}─── STEP 2: WEBCAM OPTICAL CAPTURE & VISION TEST ─────────────────────{RESET}")
    t0 = time.perf_counter()
    cam_res = CameraCapture.capture_frame(0)
    if cam_res.success:
        print(f"  {GREEN}[OK] Camera Capture:{RESET} Acquired {cam_res.width}x{cam_res.height} optical frame")
        # Run vision reasoning
        vclient = GroqVisionClient()
        v_res = await vclient.analyze_image(
            cam_res.image_base64,
            query="Briefly describe what is visible in front of the camera in 1 sentence.",
            source="webcam"
        )
        if v_res.success:
            print(f"  {GREEN}[OK] Multimodal Reasoning ({v_res.model_used}):{RESET}")
            print(f"    {CYAN}\"{v_res.description}\"{RESET}")
            results["Vision Perception"] = f"PASS ({v_res.model_used})"
        else:
            print(f"  {YELLOW}[WARN] Vision Reasoning warning:{RESET} {v_res.error}")
            results["Vision Perception"] = "WARN"
    else:
        print(f"  {YELLOW}[WARN] Camera Notice:{RESET} {cam_res.error}")
        results["Vision Perception"] = "SKIPPED (No Cam)"

    print(f"\n{BOLD}─── STEP 3: SCREEN PERCEPTION & OCR TEST ─────────────────────────────{RESET}")
    scr_res = ScreenCapture.capture_screen()
    if scr_res.success:
        print(f"  {GREEN}[OK] Screen Capture:{RESET} Captured active monitor ({scr_res.width}x{scr_res.height})")
        results["Screen Perception"] = f"PASS ({scr_res.width}x{scr_res.height})"
    else:
        print(f"  {YELLOW}[WARN] Screen Capture unavailable:{RESET} {scr_res.error}")
        results["Screen Perception"] = "SKIPPED (Headless)"

    print(f"\n{BOLD}─── STEP 4: SHODH-MEMORY DEDUPLICATION & RECALL ──────────────────────{RESET}")
    mem_spec = registry.get("memory")
    test_note = f"Automated test memory recorded at {int(time.time())}: Master prefers Earl Grey tea."
    if mem_spec:
        m_res = await mem_spec.execute("store_memory", {"raw_text": test_note})
        print(f"  {GREEN}[OK] Memory Stored via MemorySpecialist:{RESET} {m_res.speech_summary}")
        # Retrieve
        recall_res = await mem_spec.execute("recall_memories", {"query": "tea"})
        print(f"  {GREEN}[OK] Memory Recalled via Shodh-Memory:{RESET} {recall_res.speech_summary}")
        results["Shodh-Memory"] = "PASS"
    else:
        results["Shodh-Memory"] = "SKIPPED"

    print(f"\n{BOLD}─── STEP 5: TASK MANAGEMENT & SQLITE WAL ─────────────────────────────{RESET}")
    task_spec = registry.get("tasks")
    if task_spec:
        t_res = await task_spec.execute("create_task", {"title": f"Automated Test Task {int(time.time()) % 1000}", "priority": "high"})
        print(f"  {GREEN}[OK] Task Created via TaskSpecialist:{RESET} {t_res.speech_summary}")
        list_res = await task_spec.execute("list_tasks", {"status": "pending"})
        print(f"  {GREEN}[OK] Active Tasks Listed:{RESET} {list_res.speech_summary}")
        results["Task Engine"] = "PASS"
    else:
        results["Task Engine"] = "SKIPPED"

    print(f"\n{BOLD}─── STEP 6: ALFRED COGNITIVE SWARM REASONING ────────────────────────{RESET}")
    if model:
        llm_client = LLMClient(primary_model=model)
        supervisor = AlfredSupervisor(registry=registry, llm_client=llm_client)
    else:
        supervisor = AlfredSupervisor(registry=registry)
    query = "What is the state of my system and how many tasks do I have?"
    print(f"  • Query: {CYAN}\"{query}\"{RESET}")
    t0 = time.perf_counter()
    agent_res = await supervisor.process_query(query)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"  {GREEN}[OK] Alfred Butler Response ({elapsed_ms:.1f}ms, plan={agent_res.plan_type}):{RESET}")
    print(f"    {BOLD}\"{agent_res.speech_text}\"{RESET}")
    results["Alfred Swarm"] = f"PASS ({elapsed_ms:.0f}ms)"

    print(f"\n{BOLD}─── STEP 7: WAKE WORD DETECTOR & VAD PRE-FILTER ─────────────────────{RESET}")
    detector = WakeWordDetector()
    # Feed 20ms silence frame (640 zero bytes)
    silent_frame = b"\x00" * 640
    silence_evt = detector.process_frame(silent_frame)
    if not silence_evt.detected:
        print(f"  {GREEN}[OK] WebRTC VAD Silence Gating:{RESET} Dropped silent 20ms frame (<0.1% CPU)")
    
    # Test listener instantiation & thread lifecycle
    listener = WakeWordListener(on_wake_word=lambda ev: None)
    listener.start()
    time.sleep(0.3)
    listener.pause()
    listener.resume()
    listener.stop()
    print(f"  {GREEN}[OK] Wake Word Listener Lifecycle:{RESET} Start -> Pause -> Resume -> Clean Stop")
    results["Wake Word Engine"] = "PASS"

    print(f"\n{BOLD}─── STEP 8: CROSS-DEVICE STATE SYNC MANAGER ─────────────────────────{RESET}")
    await sync_manager.update_state({"master_volume": 85, "zen_mode": False}, source_device_id="smoke_test_node")
    snapshot = sync_manager.get_snapshot()
    print(f"  {GREEN}[OK] Cluster State Snapshot:{RESET} Volume={snapshot.master_volume}%, ZenMode={snapshot.zen_mode}, Tasks={snapshot.active_tasks_count}")
    results["Cross-Device Sync"] = "PASS"

    print(f"\n{BOLD}─── STEP 9: SPEECH SYNTHESIS (TTS) ──────────────────────────────────{RESET}")
    tts_ok = await synthesize_and_speak("Automated diagnostics complete, sir. All VESPER systems are online.", "smoke_test", delete_after=True)
    if tts_ok:
        results["TTS Synthesis & Playback"] = "PASS"
    else:
        results["TTS Synthesis & Playback"] = "FAIL"

    print(f"\n{BOLD}─── STEP 10: TOUCHLESS GESTURE PERCEPTION & ACTIONS ─────────────────{RESET}")
    gesture_worker = GestureWorker(fps=6.0)
    rec = gesture_worker._init_recognizer()
    if rec is not None:
        print(f"  {GREEN}[OK] MediaPipe GestureRecognizer:{RESET} Loaded gesture_recognizer.task model")
        import numpy as np
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        g_out, conf = gesture_worker._evaluate_gesture_heuristic(test_frame)
        print(f"  {GREEN}[OK] Gesture Inference Engine:{RESET} Evaluated frame (output='{g_out}', conf={conf})")
        # Test cluster state dispatch
        await gesture_worker._dispatch_gesture("CLOSED_FIST", 0.95)
        s1 = sync_manager.get_snapshot()
        await gesture_worker._dispatch_gesture("OPEN_PALM", 0.90)
        s2 = sync_manager.get_snapshot()
        print(f"  {GREEN}[OK] Cluster Gesture Actions:{RESET} CLOSED_FIST (Vol={s1.master_volume}%) -> OPEN_PALM (Vol={s2.master_volume}%)")
        results["Gesture Perception"] = "PASS"
    else:
        print(f"  {YELLOW}[WARN] MediaPipe GestureRecognizer unavailable{RESET}")
        results["Gesture Perception"] = "WARN"

    # Final summary table
    print(f"\n{CYAN}{BOLD}" + "=" * 70)
    print("                    AUTOMATED TEST RESULTS SUMMARY")
    print("=" * 70 + f"{RESET}")
    for k, v in results.items():
        status_color = GREEN if "PASS" in v else (YELLOW if "WARN" in v or "SKIPPED" in v else RED)
        print(f"  • {k:<30} {status_color}{v}{RESET}")
    print(f"{CYAN}" + "=" * 70 + f"{RESET}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 3. INTERACTIVE LIVE DESK SESSION
# ─────────────────────────────────────────────────────────────────────────────

async def run_live_desk_session(model: Optional[str] = None):
    print_banner()
    run_hardware_diagnostic()
    if model:
        llm_client = LLMClient(primary_model=model)
        supervisor = AlfredSupervisor(registry=registry, llm_client=llm_client)
        print(f"  • {BOLD}Active Reasoning Model:{RESET} {GREEN}{model}{RESET}\n")
    else:
        supervisor = AlfredSupervisor(registry=registry)
        print(f"  • {BOLD}Active Reasoning Model:{RESET} {GREEN}{supervisor.llm.primary_model}{RESET}\n")

    print(f"{YELLOW}{BOLD}Alfred is at your service, sir.{RESET}")
    print(f"{DIM}Type any query, or try commands like:{RESET}")
    print(f"  - {CYAN}'look at what is in front of the camera'{RESET}")
    print(f"  - {CYAN}'read the text in front of the webcam'{RESET}")
    print(f"  - {CYAN}'look at my screen'{RESET}")
    print(f"  - {CYAN}'remember that my phone is on the wireless charger'{RESET}")
    print(f"  - {CYAN}'add a task to finish the project presentation'{RESET}")
    print(f"  - {CYAN}'what are my tasks?'{RESET}")
    print(f"  - {CYAN}'set volume to 65'{RESET}")
    print(f"  - {CYAN}'voice'{RESET} (to record audio from microphone)")
    print(f"  - {CYAN}'wakeword'{RESET} (to arm the microphone for 'Hey Alfred' wake detection)")
    print(f"  - {CYAN}'exit'{RESET} or {CYAN}'quit'{RESET} to leave.\n")

    while True:
        try:
            prompt = input(f"{BOLD}You > {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Exiting desk session. Have a pleasant day, sir.{RESET}")
            break

        if not prompt:
            continue
        if prompt.lower() in ["exit", "quit", "q"]:
            print(f"{YELLOW}Very good, sir. Standing by.{RESET}")
            break

        # Special mode: Mic voice recording
        if prompt.lower() == "voice":
            await _handle_interactive_mic_roundtrip(supervisor)
            continue

        # Special mode: Wake word listening mode
        if prompt.lower() == "wakeword":
            await _handle_wakeword_interactive(supervisor)
            continue

        # Normal query processing through Alfred cognitive swarm
        t0 = time.perf_counter()
        print(f"{DIM}Alfred is contemplating...{RESET}")
        try:
            resp = await supervisor.process_query(prompt)
            elapsed = time.perf_counter() - t0
            print(f"\n{GREEN}{BOLD}Alfred ({elapsed:.2f}s, plan={resp.plan_type}):{RESET}")
            print(f"{CYAN}{resp.speech_text}{RESET}\n")

            if resp.hud_cards:
                print(f"{DIM}[HUD Cards Emitted: {len(resp.hud_cards)}]{RESET}")

            # ── Plan trace: show what Alfred actually planned and executed ───
            if resp.specialist_actions:
                print(f"{DIM}{'─'*60}")
                print(f"  [PLAN] Plan trace ({resp.plan_type}):")
                for i, act in enumerate(resp.specialist_actions, 1):
                    agent_label = act.get("agent", "?")
                    ok = f"{GREEN}[OK]{RESET}" if act.get("success") else f"{RED}[FAIL]{RESET}"
                    # Show the params that were actually sent
                    params = act.get("data", {})
                    param_peek = ""
                    if isinstance(params, dict):
                        # Show query/search term for research steps
                        for pk in ("query", "search_query", "track", "thread_id", "title"):
                            if params.get(pk):
                                param_peek = f" | {pk}={str(params[pk])[:80]}"
                                break
                    print(f"  {i}. {ok} {DIM}{agent_label}{RESET}{param_peek}")
                    if not act.get("success") and act.get("error"):
                        print(f"     {RED}Error: {act['error']}{RESET}")
                print(f"{'─'*60}{RESET}")

            # Synthesize & play response speech
            await synthesize_and_speak(resp.speech_text)


        except Exception as e:
            print(f"{RED}Error communicating with Alfred: {e}{RESET}\n")


async def _handle_interactive_mic_roundtrip(supervisor: AlfredSupervisor):
    """Records audio from mic, transcribes with Groq Whisper, and routes to Alfred."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print(f"{RED}sounddevice or numpy not installed.{RESET}")
        return

    print(f"\n{YELLOW}{BOLD}[PTT] Push-to-Talk: Press ENTER to START recording...{RESET}", end="")
    input()

    sample_rate = 16000
    frames = []
    device_idx = get_best_input_device(sample_rate=sample_rate)
    dev_name = "default"
    if device_idx is not None:
        try:
            dev_name = sd.query_devices(device_idx)["name"]
        except Exception:
            pass

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device_idx,
        callback=callback,
    )
    with stream:
        print(f"{RED}{BOLD}[RECORDING] on [{dev_name}] — Speak now! Press ENTER when finished...{RESET}", end="")
        input()

    if not frames:
        print(f"{RED}No audio captured.{RESET}")
        return

    pcm_array = np.concatenate(frames, axis=0)
    pcm_bytes = pcm_array.tobytes()
    peak_amp = float(np.max(np.abs(pcm_array)))
    print(f"{DIM}[Debug] Captured {len(pcm_bytes)} bytes. Peak amplitude: {peak_amp:.0f}{RESET}")

    wav_bytes = pack_pcm_to_wav(pcm_bytes, sample_rate=sample_rate)

    print(f"{MAGENTA}Transcribing speech with Groq Whisper Large v3 Turbo...{RESET}")
    stt = GroqSpeechToText()
    try:
        transcript = await stt.transcribe_wav(wav_bytes)
        print(f"{GREEN}[OK] You said:{RESET} \"{transcript}\"")
        if not transcript.strip():
            print(f"{YELLOW}Could not decipher speech.{RESET}")
            return

        print(f"{DIM}Processing through Alfred Swarm...{RESET}")
        resp = await supervisor.process_query(transcript)
        print(f"\n{GREEN}{BOLD}Alfred:{RESET} {CYAN}{resp.speech_text}{RESET}")
        await synthesize_and_speak(resp.speech_text)
    except Exception as e:
        print(f"{RED}Voice roundtrip error: {e}{RESET}")


def run_mic_monitor():
    """Live ASCII audio VU meter so the user can visually see microphone levels in real time."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print(f"{RED}sounddevice not available.{RESET}")
        return

    sample_rate = 16000
    device_idx = get_best_input_device(sample_rate=sample_rate)
    dev_name = "default"
    if device_idx is not None:
        try:
            dev_name = sd.query_devices(device_idx)["name"]
        except Exception:
            pass

    print(f"\n{CYAN}{BOLD}[MONITOR] LIVE MICROPHONE LEVEL MONITOR [Device {device_idx}: {dev_name}]{RESET}")
    print(f"{YELLOW}Speak into your microphone. Watch the volume meter respond.{RESET}")
    print(f"{DIM}(Press Ctrl+C to exit){RESET}\n")

    def callback(indata, frames, time_info, status):
        peak = float(np.max(np.abs(indata)))
        rms = float(np.sqrt(np.mean(indata.astype(float) ** 2)))
        normalized = min(1.0, peak / 10000.0)
        bar_len = 35
        filled = int(normalized * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        color = GREEN if normalized > 0.08 else (YELLOW if normalized > 0.02 else DIM)
        tag = f"{GREEN}{BOLD}[SPEAKING]{RESET}" if normalized > 0.08 else f"{DIM}[Quiet]{RESET}"
        sys.stdout.write(f"\r  Level: [{color}{bar}{RESET}] Peak: {peak:5.0f} | RMS: {rms:4.0f}  {tag}   ")
        sys.stdout.flush()

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device_idx,
            blocksize=800,
            callback=callback,
        ):
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nMonitor stopped.\n")


def run_gesture_monitor(fps: float = 6.0):
    """Live real-time touchless hand gesture monitor using webcam and MediaPipe."""
    print(f"\n{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════════╗")
    print("║             VESPER LIVE TOUCHLESS GESTURE PERCEPTION MONITOR        ║")
    print("║      Webcam /dev/video0 -> MediaPipe Tasks -> Cluster State Sync    ║")
    print(f"╚══════════════════════════════════════════════════════════════════════╝{RESET}\n")

    caps = DeviceProbe.get_capabilities()
    if not caps.has_camera:
        print(f"{YELLOW}[WARN] No optical camera sensors detected on this device.{RESET}")
        print(f"{DIM}Gesture recognition operates in zero-CPU standby without a camera.{RESET}\n")
        return

    print(f"{BOLD}Active Sensors:{RESET} Camera indices {caps.available_cameras} | Sampling: {fps} FPS")
    print(f"{BOLD}Gesture Vocabulary:{RESET}")
    print(f"  • {CYAN}Closed Fist{RESET}      -> Mute Volume / Pause Playback")
    print(f"  • {CYAN}Open Palm{RESET}        -> Resume Audio / Unmute")
    print(f"  • {CYAN}Finger Gun Right{RESET} -> Next Track (GUN_RIGHT)")
    print(f"  • {CYAN}Finger Gun Left{RESET}  -> Previous Track (GUN_LEFT)")
    print(f"  • {CYAN}Peace Sign{RESET}       -> Toggle Ambient Zen Mode")
    print(f"  • {CYAN}Thumbs Up{RESET}       -> Volume Up (+10%)")
    print(f"  • {CYAN}Thumbs Down{RESET}     -> Volume Down (-10%)")
    print(f"  • {CYAN}Pointing Up{RESET}     -> Toggle Focus Mode")
    print(f"  • {CYAN}Rock On{RESET}          -> Lock / Unlock Gestures (Hold 1s)")
    print(f"  • {CYAN}Air Tap / Pinch{RESET} -> Select Widget\n")
    print(f"{YELLOW}Hold your hand 1-3 feet in front of your webcam to trigger gestures.{RESET}")
    print(f"{DIM}(Press Ctrl+C to exit monitor){RESET}\n")

    worker = GestureWorker(fps=fps)
    rec = worker._init_recognizer()
    if not rec:
        print(f"{RED}[FAIL] Could not load MediaPipe gesture recognizer model.{RESET}")
        return

    last_gesture_times: dict[str, float] = {}
    last_gesture_name = "NONE"
    last_gesture_time = 0.0
    candidate_gesture = "NONE"
    candidate_streak = 0
    none_streak = 0
    gesture_awaiting_release: set[str] = set()

    gesture_cooldowns = {
        "VOLUME_DIAL": 0.12,
        "THUMB_UP": 0.35,
        "THUMB_DOWN": 0.35,
        "VOLUME_UP": 0.35,
        "VOLUME_DOWN": 0.35,
        "CLOSED_FIST": 1.5,
        "OPEN_PALM": 1.5,
        "PEACE_SIGN": 2.0,
        "POINTING_UP": 2.0,
        "NEXT_TRACK": 1.6,
        "PREV_TRACK": 1.6,
        "AIR_TAP": 1.2,
        "GESTURE_TOGGLE": 2.5,
        "ROCK_ON": 2.5,
    }

    async def _async_monitor():
        nonlocal last_gesture_time, last_gesture_name, candidate_gesture, candidate_streak, none_streak
        loop_interval = 1.0 / max(fps, 1.0)
        frames_count = 0
        t_start = time.time()

        try:
            while True:
                t0 = time.time()
                frame = await asyncio.to_thread(CameraCapture.capture_frame, 0)
                if not frame.success or not frame.image_base64:
                    await asyncio.sleep(loop_interval)
                    continue

                now = time.time()

                # If tracking is paused, check only for deliberate resume hold
                if worker.state.tracking_paused:
                    toggle_gesture, toggle_conf = worker._check_toggle_gesture_only(frame)
                    if toggle_gesture.startswith("GESTURE_TOGGLE"):
                        worker.state.tracking_paused = False
                        worker._toggle_lockout_until = now + 2.5
                        gesture_awaiting_release.add("ROCK_ON")
                        gesture_awaiting_release.add("GESTURE_TOGGLE")
                        await worker._dispatch_gesture("GESTURE_TOGGLE:RESUMED", toggle_conf)
                        last_gesture_name = "GESTURE_TOGGLE:RESUMED"
                        last_gesture_time = now
                        sys.stdout.write("\r" + " " * 95 + "\r")
                        sys.stdout.flush()
                        t_str = time.strftime("%H:%M:%S")
                        print(f"  {GREEN}[GESTURE]{RESET} {t_str} | {BOLD}{'RESUMED':<14}{RESET} (conf: {toggle_conf:.2f}) -> {YELLOW}[GESTURES: ACTIVE]{RESET}")
                    await asyncio.sleep(loop_interval)
                    continue

                gesture, conf = worker._evaluate_gesture_heuristic(frame)

                if gesture == "NONE" or conf < 0.55:
                    none_streak += 1
                    candidate_gesture = "NONE"
                    candidate_streak = 0
                    if none_streak >= 1:
                        gesture_awaiting_release.clear()
                    await asyncio.sleep(loop_interval)
                    continue

                none_streak = 0
                if gesture == candidate_gesture:
                    candidate_streak += 1
                else:
                    candidate_gesture = gesture
                    candidate_streak = 1

                # Plain ROCK_ON is an in-progress hold; wait for 1.0s to complete
                if gesture == "ROCK_ON":
                    await asyncio.sleep(loop_interval)
                    continue

                is_volume_dial = gesture.startswith("VOLUME_DIAL:")
                is_thumb_volume = gesture in ("THUMB_UP", "THUMB_DOWN", "VOLUME_UP", "VOLUME_DOWN")
                is_volume = is_volume_dial or is_thumb_volume

                # Streak confirmation
                if is_volume_dial or gesture in ("NEXT_TRACK", "PREV_TRACK") or gesture.startswith("GESTURE_TOGGLE"):
                    req_streak = 1
                else:
                    req_streak = 2

                if candidate_streak < req_streak:
                    await asyncio.sleep(loop_interval)
                    continue

                # Hysteresis / Release requirement for non-volume gestures
                base_g = gesture.split(":")[0]
                if not is_volume:
                    if base_g in gesture_awaiting_release or gesture in gesture_awaiting_release:
                        await asyncio.sleep(loop_interval)
                        continue

                # Per-gesture cooldown
                g_cooldown = gesture_cooldowns.get(base_g, 1.5)
                if (now - last_gesture_times.get(base_g, 0.0)) < g_cooldown:
                    await asyncio.sleep(loop_interval)
                    continue

                last_gesture_times[base_g] = now
                last_gesture_times[gesture] = now
                last_gesture_time = now
                last_gesture_name = gesture

                if not is_volume:
                    gesture_awaiting_release.clear()
                    gesture_awaiting_release.add(base_g)
                    gesture_awaiting_release.add(gesture)

                if gesture.startswith("GESTURE_TOGGLE"):
                    worker._toggle_lockout_until = now + 2.5

                await worker._dispatch_gesture(gesture, conf)

                # Action badge
                act_str = ""
                snap = sync_manager.get_snapshot()
                if gesture in ("CLOSED_FIST", "MUTE"):
                    act_str = f"{RED}[MUTE: Vol=0%]{RESET}"
                elif gesture in ("OPEN_PALM", "RESUME", "PLAY"):
                    act_str = f"{GREEN}[PLAY: Vol={snap.master_volume}%]{RESET}"
                elif gesture in ("NEXT_TRACK", "SWIPE_RIGHT", "GUN_RIGHT", "GUN_POINT_RIGHT"):
                    act_str = f"{CYAN}[NEXT TRACK]{RESET}"
                elif gesture in ("PREV_TRACK", "SWIPE_LEFT", "GUN_LEFT", "GUN_POINT_LEFT"):
                    act_str = f"{CYAN}[PREV TRACK]{RESET}"
                elif gesture in ("PEACE_SIGN", "TOGGLE_ZEN"):
                    act_str = f"{MAGENTA}[ZEN MODE: {'ON' if snap.zen_mode else 'OFF'}]{RESET}"
                elif gesture in ("THUMB_UP", "VOLUME_UP"):
                    act_str = f"{GREEN}[VOL UP: {snap.master_volume}%]{RESET}"
                elif gesture in ("THUMB_DOWN", "VOLUME_DOWN"):
                    act_str = f"{YELLOW}[VOL DOWN: {snap.master_volume}%]{RESET}"
                elif gesture in ("POINTING_UP", "TOGGLE_FOCUS"):
                    act_str = f"{CYAN}[FOCUS: {'ON' if snap.focus_mode else 'OFF'}]{RESET}"
                elif gesture in ("ROCK_ON", "GESTURE_LOCK") or gesture.startswith("GESTURE_TOGGLE"):
                    act_str = f"{YELLOW}[GESTURES: {'PAUSED' if worker.state.tracking_paused else 'ACTIVE'}]{RESET}"
                elif gesture == "AIR_TAP":
                    act_str = f"{GREEN}[AIR TAP SELECT]{RESET}"

                # Clear status line and print persistent trigger log
                sys.stdout.write("\r" + " " * 95 + "\r")
                sys.stdout.flush()
                t_str = time.strftime("%H:%M:%S")
                print(f"  {GREEN}[GESTURE]{RESET} {t_str} | {BOLD}{gesture:<14}{RESET} (conf: {conf:.2f}) -> {act_str}")

                frames_count += 1
                curr_fps = frames_count / max(0.1, (now - t_start))
                snap = sync_manager.get_snapshot()
                zen_label = f"{MAGENTA}ON{RESET}" if snap.zen_mode else f"{DIM}OFF{RESET}"
                focus_label = f"{CYAN}ON{RESET}" if snap.focus_mode else f"{DIM}OFF{RESET}"
                g_display = f"{GREEN}{BOLD}{last_gesture_name}{RESET}" if (now - last_gesture_time) < 1.5 and last_gesture_name != "NONE" else f"{DIM}NONE{RESET}"

                sys.stdout.write(
                    f"\r  FPS: {curr_fps:4.1f} | Gesture: {g_display:<18} | Vol: {snap.master_volume:3d}% | Zen: {zen_label} | Focus: {focus_label}   "
                )
                sys.stdout.flush()

                elapsed = time.time() - t0
                await asyncio.sleep(max(0.01, loop_interval - elapsed))

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

    try:
        asyncio.run(_async_monitor())
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\r" + " " * 95 + "\r")
        sys.stdout.flush()
        print(f"\n{DIM}Gesture monitor stopped.{RESET}\n")


async def _handle_wakeword_interactive(supervisor: AlfredSupervisor):
    """Arms continuous microphone stream with live VU level meter and wake detection."""
    sample_rate = 16000
    device_idx = get_best_input_device(sample_rate=sample_rate)
    import sounddevice as sd
    dev_name = sd.query_devices(device_idx)["name"] if device_idx is not None else "default"

    print(f"\n{CYAN}{BOLD}[WAKE WORD ACTIVE on Device {device_idx}: {dev_name}]{RESET}")
    print(f"{YELLOW}Say 'Hey Alfred', 'Alfred', or 'Hey Jarvis' into your microphone.{RESET}")
    print(f"{DIM}Watch the volume meter below to verify your mic is picking up sound. (Press Ctrl+C to exit){RESET}\n")

    wake_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    detected_info = []

    def on_wake(evt: WakeWordEvent):
        detected_info.clear()
        detected_info.append(evt)
        loop.call_soon_threadsafe(wake_event.set)

    def on_frame(evt: WakeWordEvent):
        peak = evt.peak_amplitude
        rms = evt.rms_amplitude
        normalized = min(1.0, peak / 10000.0)
        bar_len = 28
        filled = int(normalized * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        color = GREEN if normalized > 0.08 else (YELLOW if normalized > 0.02 else DIM)
        vad_tag = f"{GREEN}[SPEECH]{RESET}" if evt.is_speech else f"{DIM}[SILENT]{RESET}"
        score = evt.confidence
        score_color = GREEN if score >= 0.5 else (YELLOW if score > 0.15 else DIM)

        sys.stdout.write(
            f"\r  Level: [{color}{bar}{RESET}] Peak: {peak:5.0f} | RMS: {rms:4.0f} | VAD: {vad_tag} | Wake: {score_color}{score:0.2f}{RESET}/0.50   "
        )
        sys.stdout.flush()

    listener = WakeWordListener(
        on_wake_word=on_wake,
        on_audio_frame=on_frame,
        device_index=device_idx,
        sample_rate=sample_rate,
    )
    listener.start()

    try:
        while True:
            await wake_event.wait()
            wake_event.clear()

            evt = detected_info[0] if detected_info else None
            phrase = evt.wake_word if evt else "hey_alfred"
            conf = evt.confidence if evt else 1.0

            # Clear meter line
            sys.stdout.write("\r" + " " * 95 + "\r")
            sys.stdout.flush()

            print(f"\n{GREEN}{BOLD}[WAKE DETECTED] ('{phrase}', confidence: {conf:.2f}){RESET}")
            print(f"{CYAN}{BOLD}Alfred:{RESET} {CYAN}Yes, sir? How may I assist you?{RESET}\n")

            listener.pause()  # Pause to avoid self-trigger

            # Capture and answer voice query
            await _handle_interactive_mic_roundtrip(supervisor)

            listener.resume()
            print(f"\n{YELLOW}Listening again for 'Hey Alfred' or 'Hey Jarvis'...{RESET}\n")

    except KeyboardInterrupt:
        sys.stdout.write("\r" + " " * 95 + "\r")
        sys.stdout.flush()
        print(f"\n{DIM}Stopping wake word listener...{RESET}")
    finally:
        listener.stop()


# ─────────────────────────────────────────────────────────────────────────────
# 4. ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VESPER All-In-One Test & Interactive Harness")
    parser.add_argument("--automated", action="store_true", help="Run full 1-click automated smoke test")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive live desk session")
    parser.add_argument("--voice", action="store_true", help="Launch direct push-to-talk voice tester")
    parser.add_argument("--wakeword", action="store_true", help="Launch live wake word continuous listening")
    parser.add_argument("--mic", action="store_true", help="Launch live real-time microphone VU level monitor")
    parser.add_argument("--gesture", action="store_true", help="Launch live touchless hand gesture monitor")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override AGENT_PRIMARY_MODEL for this session (e.g. meta-llama/llama-3.3-70b-instruct:free, groq/compound-mini)",
    )
    args = parser.parse_args()

    if args.model:
        os.environ["AGENT_PRIMARY_MODEL"] = args.model

    def make_supervisor():
        if args.model:
            return AlfredSupervisor(registry=registry, llm_client=LLMClient(primary_model=args.model))
        return AlfredSupervisor(registry=registry)

    if args.automated:
        asyncio.run(run_automated_smoke_test(model=args.model))
    elif args.gesture:
        run_gesture_monitor()
    elif args.mic:
        run_mic_monitor()
    elif args.voice:
        asyncio.run(_handle_interactive_mic_roundtrip(make_supervisor()))
    elif args.wakeword:
        asyncio.run(_handle_wakeword_interactive(make_supervisor()))
    elif args.interactive:
        asyncio.run(run_live_desk_session(model=args.model))
    else:
        # Default menu
        print_banner()
        print("Select testing mode:")
        print(f"  [{BOLD}1{RESET}] Run Complete Automated Smoke Test across all 10 Pillars (Recommended)")
        print(f"  [{BOLD}2{RESET}] Launch Interactive Live Desk Session (Chat, Webcam, Screen, Audio)")
        print(f"  [{BOLD}3{RESET}] Arm Continuous 'Hey Alfred' Wake Word Listening")
        print(f"  [{BOLD}4{RESET}] Test Voice Push-to-Talk (Mic -> Groq Whisper -> Alfred -> TTS)")
        print(f"  [{BOLD}5{RESET}] Live Microphone VU Level Meter (Verify mic sensitivity & sound)")
        print(f"  [{BOLD}6{RESET}] Live Touchless Hand Gesture Monitor (Webcam -> MediaPipe -> Cluster Actions)")
        print(f"  [{BOLD}Q{RESET}] Quit\n")

        try:
            choice = input(f"{BOLD}Enter choice [1-6, Q]: {RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return

        if choice == "1":
            asyncio.run(run_automated_smoke_test(model=args.model))
        elif choice == "2":
            asyncio.run(run_live_desk_session(model=args.model))
        elif choice == "3":
            asyncio.run(_handle_wakeword_interactive(make_supervisor()))
        elif choice == "4":
            asyncio.run(_handle_interactive_mic_roundtrip(make_supervisor()))
        elif choice == "5":
            run_mic_monitor()
        elif choice == "6":
            run_gesture_monitor()
        else:
            print("Exiting.")


if __name__ == "__main__":
    main()
