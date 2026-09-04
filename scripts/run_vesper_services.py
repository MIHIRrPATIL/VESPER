#!/usr/bin/env python3
"""VESPER Unified Terminal Services Orchestrator & Desktop HUD.

Boots and coordinates all core backend microservices:
  - Gateway (:8000)
  - Agent Swarm (:8001)
  - Voice Subsystem (:8002)
  - Optional: Peripheral Daemons (Webcam Gestures, Mic Wake Word)

Attaches an interactive Terminal Desktop HUD that connects over WebSockets
(ws://localhost:8000/ws) as a simulated desktop companion device (DESK_HUD),
rendering live HUD cards, streaming Alfred responses, responding to heartbeat
pings to stay connected, and providing a fast hands-free voice & REPL command center.

Usage:
  .venv/bin/python3 scripts/run_vesper_services.py                 # Full stack + Desktop HUD
  .venv/bin/python3 scripts/run_vesper_services.py --services-only # Background services only
  .venv/bin/python3 scripts/run_vesper_services.py --client-only   # Desktop HUD only
  .venv/bin/python3 scripts/run_vesper_services.py --with-gestures # Arm live webcam touchless gestures
  .venv/bin/python3 scripts/run_vesper_services.py --with-wakeword # Arm live mic 'Hey Alfred' wake word
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import select
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup root path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / ".env")

import httpx
import websockets
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from backend.shared.config import (
    AGENT_SERVICE_URL,
    GATEWAY_PORT,
    VOICE_SERVICE_URL,
)
from backend.shared.events import (
    Channel,
    ClientEnvelope,
    ClientHelloPayload,
    ClientType,
    EventType,
    ServerEnvelope,
)

console = Console()

GATEWAY_URL = f"http://localhost:{GATEWAY_PORT}"
GATEWAY_WS_URL = f"ws://localhost:{GATEWAY_PORT}/ws"
AGENT_URL = AGENT_SERVICE_URL
VOICE_URL = VOICE_SERVICE_URL
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def play_audio_file(audio_path: Path, delete_after: bool = True) -> None:
    """Plays audio through system speakers via low-latency player."""
    p_str = str(audio_path)
    try:
        for cmd in [["pw-play", p_str], ["paplay", p_str], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", p_str], ["mpv", "--no-terminal", p_str]]:
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=True, timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except Exception:
                    pass
    finally:
        if delete_after and audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                pass


async def speak_text(text: str) -> None:
    """Synthesizes text through Alfred's TTS and plays through the speakers."""
    from backend.voice.tts.manager import TTSManager
    from backend.voice.audio_utils import prepare_audio_for_playback

    tts_mgr = TTSManager()
    chunks = []
    try:
        async for chunk in tts_mgr.stream_speech(text):
            chunks.append(chunk)
        if chunks:
            audio_bytes, ext = prepare_audio_for_playback(chunks)
            out_file = OUTPUT_DIR / f"alfred_live_{int(time.time())}{ext}"
            out_file.write_bytes(audio_bytes)
            await asyncio.to_thread(play_audio_file, out_file, True)
    except Exception as e:
        console.print(f"[dim red][TTS Error] {e}[/dim red]")


# ─────────────────────────────────────────────────────────────────────────────
# 1. SERVICE SUPERVISOR
# ─────────────────────────────────────────────────────────────────────────────

class ServiceSupervisor:
    """Manages lifecycle of VESPER FastAPI microservices."""

    def __init__(self) -> None:
        self.processes: Dict[str, subprocess.Popen] = {}
        self._shutting_down = False

    def start_service(self, name: str, cmd: List[str], env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
        """Starts a service as a non-blocking subprocess."""
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=merged_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.processes[name] = proc
        return proc

    async def wait_for_health(self, name: str, url: str, timeout_seconds: float = 12.0) -> bool:
        """Polls a /health endpoint until it responds HTTP 200."""
        t0 = time.time()
        health_url = f"{url.rstrip('/')}/health"
        async with httpx.AsyncClient(timeout=1.5) as client:
            while time.time() - t0 < timeout_seconds:
                try:
                    res = await client.get(health_url)
                    if res.status_code == 200:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.3)
        return False

    async def start_all(
        self,
        with_gestures: bool = False,
        with_wakeword: bool = False,
    ) -> bool:
        """Boots all core backend microservices and verifies health."""
        python_bin = sys.executable

        console.print("[bold cyan]=== STARTING VESPER CORE MICROSERVICES ===[/bold cyan]")

        # 1. Start Gateway Service (Port 8000)
        console.print("  • Starting Gateway Service (Port 8000)...", end=" ")
        self.start_service(
            "gateway",
            [python_bin, "-m", "uvicorn", "backend.gateway.app:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
        )
        gw_ok = await self.wait_for_health("gateway", GATEWAY_URL, timeout_seconds=10.0)
        if gw_ok:
            console.print("[bold green][ONLINE][/bold green]")
        else:
            console.print("[bold red][FAILED][/bold red]")
            self.stop_all()
            return False

        # 2. Start Agent Swarm Service (Port 8001)
        console.print("  • Starting Agent Swarm Service (Port 8001)...", end=" ")
        self.start_service(
            "agent",
            [python_bin, "-m", "uvicorn", "backend.agent.app:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "warning"],
        )
        agent_ok = await self.wait_for_health("agent", AGENT_URL, timeout_seconds=10.0)
        if agent_ok:
            console.print("[bold green][ONLINE][/bold green]")
        else:
            console.print("[bold red][FAILED][/bold red]")
            self.stop_all()
            return False

        # 3. Start Voice Subsystem (Port 8002)
        console.print("  • Starting Voice Subsystem (Port 8002)...", end=" ")
        self.start_service(
            "voice",
            [python_bin, "-m", "uvicorn", "backend.voice.app:app", "--host", "0.0.0.0", "--port", "8002", "--log-level", "warning"],
        )
        voice_ok = await self.wait_for_health("voice", VOICE_URL, timeout_seconds=10.0)
        if voice_ok:
            console.print("[bold green][ONLINE][/bold green]")
        else:
            console.print("[bold red][FAILED][/bold red]")
            self.stop_all()
            return False

        console.print("[bold green]All core services initialized and ready.[/bold green]\n")
        return True

    def stop_all(self) -> None:
        """Gracefully terminates all child processes and process groups."""
        if self._shutting_down:
            return
        self._shutting_down = True

        console.print("\n[bold yellow]Stopping VESPER services...[/bold yellow]")
        for name, proc in list(self.processes.items()):
            try:
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass

        time.sleep(0.8)

        for name, proc in list(self.processes.items()):
            try:
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        self.processes.clear()
        console.print("[bold green]All background services stopped cleanly.[/bold green]")


# ─────────────────────────────────────────────────────────────────────────────
# 2. TERMINAL DESKTOP HUD & REPL CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class TerminalDesktopHUD:
    """Full-duplex WebSocket Desktop Companion HUD with Heartbeat & Hands-Free Audio."""

    def __init__(self, ws_url: str = GATEWAY_WS_URL, client_id: str = "vesper-desktop-terminal") -> None:
        self.ws_url = ws_url
        self.client_id = client_id
        self.websocket: Optional[Any] = None
        self.session_id: Optional[str] = None
        self.is_running = True
        self._bg_tasks: List[asyncio.Task] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Peripherals
        self._gesture_worker = None
        self._gesture_task: Optional[asyncio.Task] = None
        self._wakeword_listener = None
        self._is_handling_voice = False

        # Audio / TTS Playback Lock & Task Coordination
        self._tts_mgr = None
        self._tts_lock = asyncio.Lock()
        self._current_tts_task: Optional[asyncio.Task] = None
        self._current_tts_proc: Optional[asyncio.subprocess.Process] = None

    async def connect(self) -> bool:
        """Establishes WebSocket connection and completes CLIENT_HELLO handshake."""
        try:
            self._loop = asyncio.get_running_loop()
            self.websocket = await websockets.connect(self.ws_url)

            # Send CLIENT_HELLO
            hello_envelope = ClientEnvelope(
                uuid=str(uuid.uuid4()),
                channel=Channel.CONTROL,
                type=EventType.CLIENT_HELLO,
                payload=ClientHelloPayload(
                    client_id=self.client_id,
                    client_type=ClientType.DESK_HUD,
                    capabilities=["control", "system", "voice", "gesture", "notify", "sync"],
                ).model_dump(),
            )
            await self.websocket.send(hello_envelope.model_dump_json())

            # Await SERVER_HELLO
            raw_res = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            res_data = json.loads(raw_res)
            server_hello = ServerEnvelope.model_validate(res_data)

            if server_hello.type == EventType.SERVER_HELLO:
                self.session_id = server_hello.payload.get("session_id")
                return True
            return False
        except Exception as e:
            console.print(f"[bold red]Connection failed:[/bold red] {e}")
            return False

    async def send_envelope(self, channel: Channel, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Encapsulates and dispatches a validated ClientEnvelope to the Gateway."""
        if not self.websocket:
            return
        envelope = ClientEnvelope(
            uuid=str(uuid.uuid4()),
            channel=channel,
            type=event_type,
            payload=payload,
        )
        try:
            await self.websocket.send(envelope.model_dump_json())
        except Exception as e:
            console.print(f"[dim red][WS Send Error] {e}[/dim red]")

    async def _heartbeat_loop(self) -> None:
        """Maintains active session heartbeat with the Gateway."""
        while self.is_running and self.websocket:
            try:
                await asyncio.sleep(12.0)
                await self.send_envelope(
                    Channel.CONTROL,
                    EventType.PING,
                    {"client_time": time.time()},
                )
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _receive_loop(self) -> None:
        """Asynchronously listens for server broadcasts and renders them to the console."""
        while self.is_running and self.websocket:
            try:
                raw_msg = await self.websocket.recv()
                data = json.loads(raw_msg)
                envelope = ServerEnvelope.model_validate(data)

                # CRITICAL: Always reply immediately to server PING with PONG to prevent eviction!
                if envelope.type == EventType.PING:
                    pong = ClientEnvelope(
                        uuid=str(uuid.uuid4()),
                        channel=Channel.CONTROL,
                        type=EventType.PONG,
                        payload={"client_time": time.time(), "server_time": envelope.payload.get("server_time", time.time())},
                    )
                    await self.websocket.send(pong.model_dump_json())
                    continue

                if envelope.type == EventType.PONG:
                    continue

                # Render regular event
                self._render_incoming_envelope(envelope)
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                if self.is_running:
                    console.print("[bold yellow][DISCONNECT] Gateway connection closed.[/bold yellow]")
                break
            except Exception as e:
                if self.is_running:
                    console.print(f"[dim red][ERROR] Inbound parse error: {e}[/dim red]")

    def _render_incoming_envelope(self, envelope: ServerEnvelope) -> None:
        """Renders server events into styled terminal components."""
        p = envelope.payload

        if envelope.type == EventType.AGENT_RESPONSE:
            response = p.get("response", "")
            markdown_body = p.get("markdown_body", "")
            hud_cards = p.get("hud_cards", [])
            latency_ms = p.get("latency_ms", 0)

            # Speech text banner
            console.print()
            console.print(
                Panel(
                    f"[bold white]{response}[/bold white]",
                    title=f"[bold cyan]Alfred Butler Response ({latency_ms:.0f}ms)[/bold cyan]",
                    border_style="cyan",
                )
            )

            # Markdown Body (if detailed)
            if markdown_body and markdown_body != response:
                console.print(
                    Panel(
                        Markdown(markdown_body),
                        title="[dim]Detailed Briefing[/dim]",
                        border_style="blue",
                    )
                )

            # HUD Cards
            for card in hud_cards:
                self._render_hud_card(card)

            # Trigger real-time speech synthesis through host speakers
            if response:
                if self._current_tts_task and not self._current_tts_task.done():
                    self._current_tts_task.cancel()
                if self._current_tts_proc:
                    try:
                        self._current_tts_proc.terminate()
                    except Exception:
                        pass
                self._current_tts_task = asyncio.create_task(self._play_tts_response(response))

            sys.stdout.write("\nvesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.STATE_SYNC:
            state = p.get("state", {})
            vol = state.get("master_volume", "--")
            zen = state.get("zen_mode", False)
            focus = state.get("focus_mode", False)
            console.print(
                f"\n[dim magenta][STATE_SYNC] Volume={vol}%, ZenMode={'ON' if zen else 'OFF'}, FocusMode={'ON' if focus else 'OFF'}[/dim magenta]"
            )
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.SET_VOLUME:
            vol = p.get("volume", "--")
            muted = p.get("muted", False)
            action = p.get("media_action", "")
            console.print(f"\n[dim magenta][VOLUME] Master Volume: {vol}% {'(MUTED)' if muted else ''} {action}[/dim magenta]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.ZEN_MODE_STATE:
            zen = p.get("zen_mode", False)
            console.print(f"\n[dim magenta][ZEN MODE] {'ACTIVATED' if zen else 'DEACTIVATED'}[/dim magenta]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.MEDIA_CONTROL:
            action = p.get("action", "")
            console.print(f"\n[dim yellow][MEDIA_CONTROL] Action: {action.upper()}[/dim yellow]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.GESTURE_EVENT:
            gesture = p.get("gesture", "")
            conf = p.get("confidence", 1.0)
            if gesture.startswith("GESTURE_TOGGLE"):
                if ":PAUSED" in gesture or p.get("tracking_paused") is True:
                    console.print("\n[dim yellow][GESTURE] Tracking is now PAUSED[/dim yellow]")
                elif ":RESUMED" in gesture or p.get("tracking_paused") is False:
                    console.print("\n[dim green][GESTURE] Tracking is now RESUMED[/dim green]")
            elif gesture.startswith("VOLUME_DIAL:"):
                pass
            else:
                console.print(f"\n[dim green][GESTURE] Recognized: {gesture} (conf={conf:.2f})[/dim green]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.ERROR:
            msg = p.get("message", "Unknown error")
            console.print(f"\n[bold red][GATEWAY ERROR] {msg}[/bold red]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

    def _render_hud_card(self, card: Dict[str, Any]) -> None:
        """Renders specific HUD card payloads cleanly in terminal."""
        card_type = card.get("type", "generic_card")

        if card_type == "task_list_card":
            table = Table(title="Active Task Ledger", border_style="green", show_lines=True)
            table.add_column("ID", style="dim")
            table.add_column("Title", style="bold")
            table.add_column("Status")
            table.add_column("Priority")
            for t in card.get("tasks", []):
                table.add_row(str(t.get("id", "")), str(t.get("title", "")), str(t.get("status", "")), str(t.get("priority", "")))
            console.print(table)

        elif card_type == "system_vitals_card":
            table = Table(title="System Vitals", border_style="cyan")
            table.add_column("Metric", style="bold")
            table.add_column("Value")
            table.add_row("CPU Load", f"{card.get('cpu_load_percent', '--')}%")
            table.add_row("RAM Used", f"{card.get('ram_used_gb', '--')} / {card.get('ram_total_gb', '--')} GB")
            table.add_row("Disk Used", f"{card.get('disk_used_percent', '--')}%")
            console.print(table)

        elif card_type == "memory_card":
            table = Table(title="Shodh Memory Committal", border_style="magenta")
            table.add_column("Statement", style="bold")
            table.add_column("Category")
            table.add_column("Action")
            table.add_row(str(card.get("statement", "")), str(card.get("category", "")), str(card.get("action", "stored")))
            console.print(table)

        else:
            console.print(Panel(json.dumps(card, indent=2), title=f"HUD Card: {card_type}", border_style="dim"))

    # ── Peripheral Helpers ───────────────────────────────────────────────────

    def start_gestures(self) -> None:
        """Arms continuous webcam touchless gesture tracker using persistent capture."""
        if self._gesture_worker is not None:
            console.print("[yellow]Gesture tracker already active.[/yellow]")
            return

        from backend.vision.gesture_service import GestureWorker

        async def _on_gesture_detected(gesture: str, conf: float):
            if gesture.startswith("GESTURE_TOGGLE"):
                if ":PAUSED" in gesture:
                    console.print("\n[bold yellow][GESTURES] Tracking PAUSED (Rock On 🤟 hold 1s). Other gestures disabled.[/bold yellow]")
                elif ":RESUMED" in gesture:
                    console.print("\n[bold green][GESTURES] Tracking RESUMED (Rock On 🤟 hold 1s). Gestures active.[/bold green]")
                else:
                    console.print(f"\n[bold yellow][GESTURES] Tracking TOGGLED: {gesture}[/bold yellow]")
            elif gesture.startswith("VOLUME_DIAL:"):
                try:
                    dial_val = gesture.split(":")[1]
                    console.print(f"\n[bold cyan][VOLUME KNOB][/bold cyan] {dial_val}%")
                except Exception:
                    console.print(f"\n[bold green][GESTURE DETECTED][/bold green] {gesture} (conf={conf:.2f})")
            else:
                console.print(f"\n[bold green][GESTURE DETECTED][/bold green] {gesture} (conf={conf:.2f})")
            await self.send_envelope(
                Channel.GESTURE,
                EventType.GESTURE_EVENT,
                {"gesture": gesture, "confidence": conf},
            )
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        self._gesture_worker = GestureWorker(
            fps=8.0,
            on_gesture_callback=_on_gesture_detected,
        )
        self._gesture_task = asyncio.create_task(self._gesture_worker.start())
        console.print("[bold green][GESTURES] Armed touchless hand tracking (webcam active).[/bold green]")

    def stop_gestures(self) -> None:
        """Disarms gesture tracker and releases camera hardware."""
        if self._gesture_worker:
            asyncio.create_task(self._gesture_worker.stop())
            self._gesture_worker = None
        if self._gesture_task:
            self._gesture_task.cancel()
            self._gesture_task = None
        console.print("[yellow][GESTURES] Disarmed touchless hand tracking (camera released).[/yellow]")

    async def _play_tts_response(self, text: str) -> None:
        """Synthesizes and plays Alfred's speech response through host speakers."""
        if not text or not text.strip():
            return

        async with self._tts_lock:
            if self._wakeword_listener:
                self._wakeword_listener.pause()

            temp_audio_path = None
            try:
                if self._tts_mgr is None:
                    from backend.voice.tts.manager import TTSManager
                    self._tts_mgr = TTSManager()

                from backend.voice.audio_utils import prepare_audio_for_playback
                import tempfile
                import shutil

                chunks = []
                async for chunk in self._tts_mgr.stream_speech(text):
                    chunks.append(chunk)

                if not chunks:
                    return

                audio_bytes, ext = prepare_audio_for_playback(chunks)
                if not audio_bytes:
                    return

                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                    f.write(audio_bytes)
                    temp_audio_path = f.name

                player = shutil.which("mpv")
                cmd = [player, "--no-video", "--really-quiet", temp_audio_path] if player else None
                if not cmd:
                    ffplay = shutil.which("ffplay")
                    if ffplay:
                        cmd = [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", temp_audio_path]
                if not cmd and ext == ".wav":
                    paplay = shutil.which("paplay")
                    if paplay:
                        cmd = [paplay, temp_audio_path]

                if cmd:
                    self._current_tts_proc = await asyncio.create_subprocess_exec(*cmd)
                    await self._current_tts_proc.wait()
                    self._current_tts_proc = None

            except asyncio.CancelledError:
                if self._current_tts_proc:
                    try:
                        self._current_tts_proc.terminate()
                    except Exception:
                        pass
                    self._current_tts_proc = None
                raise
            except Exception as e:
                logger.debug(f"[TTS Playback Error] {e}")
            finally:
                if temp_audio_path:
                    try:
                        os.unlink(temp_audio_path)
                    except Exception:
                        pass
                if self._wakeword_listener and self.is_running:
                    self._wakeword_listener.resume()

    def _on_wake_detected(self, event: Any) -> None:
        """Invoked on the main asyncio thread when a wake word is detected."""
        console.print(f"\n[bold green][WAKE DETECTED][/bold green] ('{event.wake_word}', conf={event.confidence:.2f})")
        console.print("[dim cyan]Alfred is listening... (speak your command)[/dim cyan]")

    async def _on_utterance_recorded(self, pcm_bytes: bytes) -> None:
        """Invoked on the main asyncio thread when the user's spoken command is captured."""
        if self._is_handling_voice:
            return
        self._is_handling_voice = True

        try:
            from backend.voice.audio_utils import pack_pcm_to_wav
            from backend.voice.stt import GroqSpeechToText

            wav_bytes = pack_pcm_to_wav(pcm_bytes, sample_rate=16000)
            stt = GroqSpeechToText()
            transcript = await stt.transcribe_wav(wav_bytes)

            if transcript.strip():
                console.print(f'[bold green]You (Voice):[/bold green] "{transcript}"')
                await self.send_envelope(Channel.VOICE, EventType.VOICE_COMMAND, {"command": transcript})
            else:
                console.print("[dim yellow][Voice] Could not decipher speech.[/dim yellow]")
        except Exception as e:
            console.print(f"[dim red][Voice Error] {e}[/dim red]")
        finally:
            self._is_handling_voice = False
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

    def start_wakeword(self) -> None:
        """Arms 'Hey Alfred' wake-word detector with WebRTC VAD hands-free recording."""
        if self._wakeword_listener is not None:
            console.print("[yellow]Wake word listener already active.[/yellow]")
            return

        from backend.voice.audio_utils import get_best_input_device
        from backend.voice.wakeword.listener import WakeWordListener

        sample_rate = 16000
        device_idx = get_best_input_device(sample_rate=sample_rate)
        loop = self._loop or asyncio.get_running_loop()

        def _wake_cb(event):
            if loop and loop.is_running():
                loop.call_soon_threadsafe(self._on_wake_detected, event)

        def _utterance_cb(pcm_bytes: bytes):
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self._on_utterance_recorded(pcm_bytes), loop)

        self._wakeword_listener = WakeWordListener(
            on_wake_word=_wake_cb,
            on_utterance_complete=_utterance_cb,
            device_index=device_idx,
            sample_rate=sample_rate,
        )
        self._wakeword_listener.start()
        console.print("[bold green][WAKE WORD] Armed 'Hey Alfred' / 'Hey Jarvis' continuous listener.[/bold green]")

    def stop_wakeword(self) -> None:
        """Disarms wake word listener and releases microphone."""
        if self._wakeword_listener:
            self._wakeword_listener.stop()
            self._wakeword_listener = None
        console.print("[yellow][WAKE WORD] Disarmed wake word listener.[/yellow]")

    # ── Interactive REPL ─────────────────────────────────────────────────────

    async def start_session(self, with_gestures: bool = False, with_wakeword: bool = False) -> None:
        """Runs the background receivers, armed daemons, and interactive REPL."""
        self._loop = asyncio.get_running_loop()
        self._bg_tasks.append(asyncio.create_task(self._receive_loop()))
        self._bg_tasks.append(asyncio.create_task(self._heartbeat_loop()))

        if with_gestures:
            self.start_gestures()
        if with_wakeword:
            self.start_wakeword()

        # Pre-warm local Piper TTS in background for instant speech synthesis (<150ms)
        async def _prewarm_tts() -> None:
            try:
                from backend.voice.tts.manager import TTSManager
                if self._tts_mgr is None:
                    self._tts_mgr = TTSManager()
                active = self._tts_mgr.get_active_providers()
                if active and hasattr(active[0], "_get_voice"):
                    await asyncio.to_thread(active[0]._get_voice)
            except Exception:
                pass

        asyncio.create_task(_prewarm_tts())

        # Welcome banner
        console.print(
            Panel(
                "[bold cyan]VESPER TERMINAL DESKTOP HUD READY[/bold cyan]\n"
                "[dim]Multiplexed WebSocket Session established with Gateway (:8000).\n"
                "Type commands or queries directly. Use [bold]/help[/bold] for special controls.[/dim]",
                border_style="cyan",
            )
        )

        async def _async_input(prompt: str) -> Optional[str]:
            sys.stdout.write(prompt)
            sys.stdout.flush()
            while self.is_running:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if r:
                    line = sys.stdin.readline()
                    if not line:
                        return None
                    return line.rstrip("\r\n")
                await asyncio.sleep(0.05)
            return None

        while self.is_running:
            try:
                line_str = await _async_input("vesper> ")
                if line_str is None:
                    break
                line = line_str.strip()
                if not line:
                    continue

                if line.lower() in ("/quit", "/exit", "quit", "exit", "q"):
                    break
                elif line.lower() == "/help":
                    self._print_help()
                elif line.lower() == "/state":
                    await self._fetch_cluster_state()
                elif line.lower() == "/devices":
                    await self._fetch_cluster_devices()
                elif line.lower() == "/services":
                    await self._check_services_health()
                elif line.lower() in ("/gestures on", "/gesture on"):
                    self.start_gestures()
                elif line.lower() in ("/gestures off", "/gesture off"):
                    self.stop_gestures()
                elif line.lower() in ("/wakeword on", "/voice on"):
                    self.start_wakeword()
                elif line.lower() in ("/wakeword off", "/voice off"):
                    self.stop_wakeword()
                elif line.lower().startswith("/gesture "):
                    gesture_name = line.split(" ", 1)[1].strip().upper()
                    await self.send_envelope(Channel.GESTURE, EventType.GESTURE_EVENT, {"gesture": gesture_name, "confidence": 1.0})
                    console.print(f"[green]Dispatched gesture: {gesture_name}[/green]")
                elif line.lower().startswith("/media "):
                    action_name = line.split(" ", 1)[1].strip().lower()
                    await self.send_envelope(Channel.SYSTEM, EventType.MEDIA_CONTROL, {"action": action_name})
                    console.print(f"[yellow]Dispatched media action: {action_name}[/yellow]")
                elif line.lower().startswith("/vol "):
                    val_str = line.split(" ", 1)[1].strip()
                    try:
                        vol = max(0, min(100, int(val_str)))
                        await self.send_envelope(Channel.SYSTEM, EventType.SET_VOLUME, {"volume": vol})
                        console.print(f"[magenta]Volume updated to: {vol}%[/magenta]")
                    except ValueError:
                        console.print("[red]Usage: /vol <0-100>[/red]")
                elif line.lower() == "/zen":
                    await self.send_envelope(Channel.GESTURE, EventType.GESTURE_EVENT, {"gesture": "PEACE_SIGN"})
                    console.print("[magenta]Toggled Zen Mode via PEACE_SIGN[/magenta]")
                elif line.lower() == "/focus":
                    await self.send_envelope(Channel.GESTURE, EventType.GESTURE_EVENT, {"gesture": "POINTING_UP"})
                    console.print("[magenta]Toggled Focus Mode via POINTING_UP[/magenta]")
                elif line.lower() == "/cam":
                    await self._inspect_webcam()
                elif line.lower() == "/screen":
                    await self._inspect_screen()
                else:
                    # Regular user query to Alfred via VOICE_COMMAND
                    console.print(f"[dim]Processing query through Cognitive Swarm...[/dim]")
                    await self.send_envelope(Channel.VOICE, EventType.VOICE_COMMAND, {"command": line})

            except (EOFError, KeyboardInterrupt):
                break

        self.is_running = False
        self.stop_gestures()
        self.stop_wakeword()

        for t in self._bg_tasks:
            t.cancel()
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass

    def _print_help(self) -> None:
        """Displays available REPL commands."""
        table = Table(title="Terminal Desktop Commands", border_style="cyan")
        table.add_column("Command", style="bold green")
        table.add_column("Description")

        table.add_row("<any text>", "Send query/command to Alfred Butler cognitive swarm")
        table.add_row("/services", "Check health of Gateway (:8000), Agent (:8001), Voice (:8002)")
        table.add_row("/state", "Print live cross-device cluster state snapshot")
        table.add_row("/devices", "List all active discovered devices on local subnet")
        table.add_row("/gestures on|off", "Arm or disarm live optical webcam gesture tracker")
        table.add_row("/wakeword on|off", "Arm or disarm live microphone 'Hey Alfred' wake word listener")
        table.add_row("/gesture <NAME>", "Emulate gesture (CLOSED_FIST, OPEN_PALM, NEXT_TRACK, PREV_TRACK, PEACE_SIGN, THUMB_UP, THUMB_DOWN, AIR_TAP)")
        table.add_row("/media <ACTION>", "Emulate media action (play, pause, next_track, previous_track)")
        table.add_row("/vol <0-100>", "Set master cluster audio volume")
        table.add_row("/zen", "Toggle ambient minimal clock (Zen Mode)")
        table.add_row("/focus", "Toggle Focus Mode (mute notifications)")
        table.add_row("/cam", "Capture and reason about webcam scene using Gemini Flash")
        table.add_row("/screen", "Capture and analyze current monitor screen")
        table.add_row("/quit, /exit, q", "Gracefully terminate all services and exit")
        console.print(table)

    async def _fetch_cluster_state(self) -> None:
        """Queries and displays live cluster snapshot."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{GATEWAY_URL}/sync/state")
                if res.status_code == 200:
                    data = res.json()
                    table = Table(title="Cluster State Snapshot", border_style="magenta")
                    table.add_column("Field", style="bold")
                    table.add_column("Value")
                    for k, v in data.items():
                        table.add_row(str(k), str(v))
                    console.print(table)
                else:
                    console.print(f"[red]Failed to fetch state: HTTP {res.status_code}[/red]")
        except Exception as e:
            console.print(f"[red]State fetch error: {e}[/red]")

    async def _fetch_cluster_devices(self) -> None:
        """Queries and lists active devices from Gateway."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{GATEWAY_URL}/sync/devices")
                if res.status_code == 200:
                    devices = res.json().get("devices", [])
                    table = Table(title="Active Cluster Topology Nodes", border_style="cyan")
                    table.add_column("Device ID", style="bold")
                    table.add_column("Type")
                    table.add_column("IP")
                    table.add_column("Status")
                    for d in devices:
                        table.add_row(d.get("device_id", ""), d.get("device_type", ""), d.get("ip_address", ""), "ONLINE" if d.get("is_active") else "OFFLINE")
                    console.print(table)
                else:
                    console.print(f"[red]Failed to fetch devices: HTTP {res.status_code}[/red]")
        except Exception as e:
            console.print(f"[red]Device list error: {e}[/red]")

    async def _check_services_health(self) -> None:
        """Pings health endpoints for all 3 microservices."""
        table = Table(title="VESPER Microservices Status", border_style="green")
        table.add_column("Service", style="bold")
        table.add_column("Port")
        table.add_column("Endpoint")
        table.add_column("Status")

        endpoints = [
            ("Gateway Service", "8000", f"{GATEWAY_URL}/health"),
            ("Agent Swarm", "8001", f"{AGENT_URL}/health"),
            ("Voice Subsystem", "8002", f"{VOICE_URL}/health"),
        ]

        async with httpx.AsyncClient(timeout=1.5) as client:
            for name, port, url in endpoints:
                try:
                    res = await client.get(url)
                    status = "[bold green]HEALTHY[/bold green]" if res.status_code == 200 else f"[red]HTTP {res.status_code}[/red]"
                except Exception:
                    status = "[bold red]OFFLINE[/bold red]"
                table.add_row(name, port, url, status)

        console.print(table)

    async def _inspect_webcam(self) -> None:
        """Captures frame from camera 0 and analyzes scene."""
        console.print("[dim]Capturing optical frame from webcam...[/dim]")
        from backend.vision.camera_stream import CameraCapture
        from backend.vision.vllm import GroqVisionClient

        cam_res = CameraCapture.capture_frame(0)
        if not cam_res.success:
            console.print(f"[yellow]Camera unavailable: {cam_res.error}[/yellow]")
            return

        console.print(f"[green]Acquired {cam_res.width}x{cam_res.height} optical frame. Analyzing...[/green]")
        vclient = GroqVisionClient()
        v_res = await vclient.analyze_image(
            cam_res.image_base64,
            query="Describe the room, user, and desk environment in 2 concise sentences.",
            source="webcam",
        )
        if v_res.success:
            console.print(Panel(f"[bold white]{v_res.description}[/bold white]", title=f"Vision Reasoning ({v_res.model_used})", border_style="cyan"))
        else:
            console.print(f"[red]Vision reasoning failed: {v_res.error}[/red]")

    async def _inspect_screen(self) -> None:
        """Captures active screen monitor and inspects."""
        console.print("[dim]Capturing active desktop monitor...[/dim]")
        from backend.vision.camera_stream import ScreenCapture

        scr_res = ScreenCapture.capture_screen()
        if not scr_res.success:
            console.print(f"[yellow]Screen capture unavailable: {scr_res.error}[/yellow]")
            return

        console.print(f"[green]Captured active screen: {scr_res.width}x{scr_res.height}[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# 3. MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VESPER All Services Launcher & Terminal Desktop HUD")
    parser.add_argument("--services-only", action="store_true", help="Start background services without launching the interactive HUD")
    parser.add_argument("--client-only", action="store_true", help="Launch the terminal HUD client only (connects to existing Gateway)")
    parser.add_argument("--with-gestures", action="store_true", help="Also arm live webcam touchless gesture tracker")
    parser.add_argument("--with-wakeword", action="store_true", help="Also arm live microphone 'Hey Alfred' wake word listener")
    args = parser.parse_args()

    supervisor = ServiceSupervisor()

    def signal_handler(sig, frame):
        supervisor.stop_all()
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def _run():
        if not args.client_only:
            ok = await supervisor.start_all()
            if not ok:
                console.print("[bold red]Failed to boot core services. Exiting.[/bold red]")
                return

        if args.services_only:
            console.print("[bold green]Services running in background. Press Ctrl+C to stop.[/bold green]")
            try:
                while True:
                    await asyncio.sleep(1.0)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                supervisor.stop_all()
            return

        # Launch Terminal Desktop HUD
        hud = TerminalDesktopHUD()
        console.print(f"[dim]Connecting to Gateway at {GATEWAY_WS_URL}...[/dim]")
        connected = await hud.connect()
        if not connected:
            console.print("[bold red]Failed to connect to Gateway WebSocket. Exiting.[/bold red]")
            supervisor.stop_all()
            return

        try:
            await hud.start_session(
                with_gestures=args.with_gestures,
                with_wakeword=args.with_wakeword,
            )
        finally:
            if not args.client_only:
                supervisor.stop_all()

    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, SystemExit):
        supervisor.stop_all()


if __name__ == "__main__":
    main()
