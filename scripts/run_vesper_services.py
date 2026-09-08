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
logger = logging.getLogger("vesper.run_services")

GATEWAY_HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
GATEWAY_URL = os.getenv("GATEWAY_URL", f"http://{GATEWAY_HOST}:{GATEWAY_PORT}")
GATEWAY_WS_URL = os.getenv("GATEWAY_WS_URL", f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}/ws")
AGENT_URL = AGENT_SERVICE_URL
VOICE_URL = VOICE_SERVICE_URL
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def play_audio_file(audio_path: Path, delete_after: bool = True) -> None:
    """Plays audio through system speakers via low-latency player."""
    p_str = str(audio_path)
    try:
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(p_str, winsound.SND_FILENAME)
                return
            except Exception:
                pass

        candidate_cmds = [
            ["afplay", p_str],
            ["pw-play", p_str],
            ["paplay", p_str],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", p_str],
            ["mpv", "--no-terminal", p_str],
        ]
        for cmd in candidate_cmds:
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


import atexit
_ACTIVE_DUCK_STATES: List[Dict[str, Any]] = []
_LAST_KNOWN_NORMAL_VOLUMES: Dict[str, Any] = {
    "playerctl": 0.8,
    "sink_inputs": {},
}


def _duck_background_audio(duck_pct: int = 20) -> Dict[str, Any]:
    """Temporarily reduces volume of active media players and background streams during voice/TTS."""
    state: Dict[str, Any] = {"sink_inputs": {}}
    target_vol_ratio = max(0.05, duck_pct / 100.0)

    # 1. Playerctl volume ducking (Spotify, VLC, web browsers, MPRIS)
    try:
        playerctl = shutil.which("playerctl")
        if playerctl:
            r = subprocess.run([playerctl, "-a", "volume"], capture_output=True, text=True, timeout=1)
            if r.returncode == 0 and r.stdout.strip():
                try:
                    curr = float(r.stdout.strip().splitlines()[0])
                    # If current volume is already ducked (<= 0.25), retain previous normal baseline
                    if curr > 0.25:
                        _LAST_KNOWN_NORMAL_VOLUMES["playerctl"] = curr
                        state["playerctl"] = curr
                    else:
                        state["playerctl"] = _LAST_KNOWN_NORMAL_VOLUMES.get("playerctl", 0.8)
                except ValueError:
                    state["playerctl"] = _LAST_KNOWN_NORMAL_VOLUMES.get("playerctl", 0.8)
            else:
                state["playerctl"] = _LAST_KNOWN_NORMAL_VOLUMES.get("playerctl", 0.8)

            subprocess.run(
                [playerctl, "-a", "volume", str(target_vol_ratio)],
                timeout=1, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass

    # 2. PulseAudio / PipeWire sink-input volume ducking
    try:
        pactl = shutil.which("pactl")
        if pactl:
            r = subprocess.run([pactl, "list", "sink-inputs"], capture_output=True, text=True, timeout=1)
            if r.returncode == 0 and r.stdout.strip():
                import re
                blocks = re.split(r"Sink Input #(\d+)", r.stdout)
                for i in range(1, len(blocks), 2):
                    sid = blocks[i]
                    block = blocks[i + 1]
                    m = re.search(r"Volume:.*?/\s*(\d+)%", block)
                    curr_pct = int(m.group(1)) if m else 100
                    # If current volume is already ducked (<= 25%), retain previous normal baseline
                    if curr_pct > 25:
                        orig_vol = f"{curr_pct}%"
                        _LAST_KNOWN_NORMAL_VOLUMES["sink_inputs"][sid] = orig_vol
                    else:
                        orig_vol = _LAST_KNOWN_NORMAL_VOLUMES["sink_inputs"].get(sid, "100%")

                    state["sink_inputs"][sid] = orig_vol
                    subprocess.run(
                        [pactl, "set-sink-input-volume", sid, f"{duck_pct}%"],
                        timeout=1, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
    except Exception:
        pass

    _ACTIVE_DUCK_STATES.append(state)
    return state


def _unduck_background_audio(state: Optional[Dict[str, Any]] = None) -> None:
    """Restores background media players and audio streams back to normal volume."""
    if state and state in _ACTIVE_DUCK_STATES:
        _ACTIVE_DUCK_STATES.remove(state)

    # 1. Restore Playerctl volume (Spotify, etc.)
    try:
        playerctl = shutil.which("playerctl")
        if playerctl:
            vol = 0.8
            if state and "playerctl" in state and float(state["playerctl"]) > 0.25:
                vol = float(state["playerctl"])
            elif _LAST_KNOWN_NORMAL_VOLUMES.get("playerctl", 0.8) > 0.25:
                vol = float(_LAST_KNOWN_NORMAL_VOLUMES["playerctl"])
            subprocess.run(
                [playerctl, "-a", "volume", str(vol)],
                timeout=1, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass

    # 2. Restore PulseAudio / PipeWire sink-inputs
    try:
        pactl = shutil.which("pactl")
        if pactl:
            if state and state.get("sink_inputs"):
                for s_id, orig_vol in state["sink_inputs"].items():
                    vol_str = orig_vol if (orig_vol and int(str(orig_vol).rstrip("%")) > 25) else "100%"
                    subprocess.run(
                        [pactl, "set-sink-input-volume", str(s_id), vol_str],
                        timeout=1, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )

            # SWEEPER: Sweep all active sink inputs in PipeWire.
            # Any sink input currently throttled to <= 25% (e.g. Spotify after track transition)
            # is restored back to normal volume (100% or known baseline).
            r = subprocess.run([pactl, "list", "sink-inputs"], capture_output=True, text=True, timeout=1)
            if r.returncode == 0 and r.stdout.strip():
                import re
                blocks = re.split(r"Sink Input #(\d+)", r.stdout)
                for i in range(1, len(blocks), 2):
                    sid = blocks[i]
                    block = blocks[i + 1]
                    m = re.search(r"Volume:.*?/\s*(\d+)%", block)
                    if m and int(m.group(1)) <= 25:
                        restore_vol = _LAST_KNOWN_NORMAL_VOLUMES["sink_inputs"].get(sid, "100%")
                        if int(restore_vol.rstrip("%")) <= 25:
                            restore_vol = "100%"
                        subprocess.run(
                            [pactl, "set-sink-input-volume", sid, restore_vol],
                            timeout=1, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
    except Exception:
        pass


def _restore_all_ducked_audio() -> None:
    """Unconditionally restores all background audio, media players, and sinks to normal volume."""
    while _ACTIVE_DUCK_STATES:
        st = _ACTIVE_DUCK_STATES.pop()
        try:
            _unduck_background_audio(st)
        except Exception:
            pass

    # Sweep with no specific state
    _unduck_background_audio(None)

    # Force sweep playerctl if any player remains <= 0.25
    try:
        playerctl = shutil.which("playerctl")
        if playerctl:
            r = subprocess.run([playerctl, "-a", "volume"], capture_output=True, text=True, timeout=1)
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.strip().splitlines():
                    try:
                        if float(line) <= 0.25:
                            restore_val = str(_LAST_KNOWN_NORMAL_VOLUMES.get("playerctl", 0.8))
                            subprocess.run([playerctl, "-a", "volume", restore_val], timeout=1, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            break
                    except ValueError:
                        pass
    except Exception:
        pass


atexit.register(_restore_all_ducked_audio)


async def speak_text(text: str) -> None:
    """Synthesizes text through Alfred's TTS and plays through the speakers."""
    from backend.voice.tts.manager import TTSManager
    from backend.voice.audio_utils import prepare_audio_for_playback

    tts_mgr = TTSManager()
    chunks = []
    duck_state = await asyncio.to_thread(_duck_background_audio, 20)
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
    finally:
        await asyncio.to_thread(_unduck_background_audio, duck_state)


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

    async def wait_for_health(self, name: str, url: str, timeout_seconds: float = 25.0) -> bool:
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

        # Wait up to 1.2s for graceful microservice shutdown
        t0 = time.time()
        for name, proc in list(self.processes.items()):
            while proc.poll() is None and (time.time() - t0 < 1.2):
                time.sleep(0.05)

        for name, proc in list(self.processes.items()):
            try:
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                proc.wait(timeout=0.5)
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
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None

        # Peripherals
        self._gesture_worker = None
        self._gesture_task: Optional[asyncio.Task] = None
        self._wakeword_listener = None
        self._wakeword_manually_muted = False
        self._is_handling_voice = False

        # Audio / TTS Playback Lock & Task Coordination
        self._tts_mgr = None
        self._tts_lock = asyncio.Lock()
        self._current_tts_task: Optional[asyncio.Task] = None
        self._current_tts_proc: Optional[asyncio.subprocess.Process] = None
        self._tts_duck_state: Optional[Dict[str, Any]] = None
        self._call_duck_state: Optional[Dict[str, Any]] = None
        self._call_watchdog_task: Optional[asyncio.Task] = None
        self._voice_duck_state: Optional[Dict[str, Any]] = None
        self._voice_watchdog_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """Establishes WebSocket connection and completes CLIENT_HELLO handshake."""
        try:
            self._loop = asyncio.get_running_loop()
            if self._receive_task and not self._receive_task.done():
                self._receive_task.cancel()
                self._receive_task = None
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                self._heartbeat_task = None

            if self.websocket:
                try:
                    await self.websocket.close()
                except Exception:
                    pass
                self.websocket = None

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
            self.websocket = None
            console.print(f"[bold red]Connection failed:[/bold red] {e}")
            return False

    @property
    def is_connected(self) -> bool:
        """Evaluates whether the underlying WebSocket connection is active and open."""
        ws = self.websocket
        if ws is None:
            return False
        # Modern websockets (v13+) use .state (State.OPEN == 1)
        if hasattr(ws, "state"):
            try:
                from websockets.protocol import State
                return ws.state == State.OPEN
            except Exception:
                return getattr(ws, "state", None) == 1
        # Legacy websockets (v12 and earlier)
        if hasattr(ws, "open"):
            return bool(ws.open)
        if hasattr(ws, "closed"):
            return not bool(ws.closed)
        return True

    async def send_envelope(self, channel: Channel, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Encapsulates and dispatches a validated ClientEnvelope to the Gateway."""
        if not self.is_connected:
            return
        envelope = ClientEnvelope(
            uuid=str(uuid.uuid4()),
            channel=channel,
            type=event_type,
            payload=payload,
        )
        try:
            await self.websocket.send(envelope.model_dump_json())
        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
            self.websocket = None
        except Exception as e:
            if self.is_connected:
                console.print(f"[dim red][WS Send Error] {e}[/dim red]")
            self.websocket = None

    async def _heartbeat_loop(self) -> None:
        """Maintains active session heartbeat with the Gateway."""
        while self.is_running and self.is_connected:
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

    async def _reconnect_supervisor(self) -> None:
        """Continuously monitors gateway connection and reconnects automatically if dropped."""
        while self.is_running:
            await asyncio.sleep(2.5)
            if self.is_running and not self.is_connected:
                self.websocket = None
                try:
                    reconnected = await self.connect()
                    if reconnected:
                        console.print("\n[bold green][GATEWAY] Reconnected to Gateway successfully.[/bold green]")
                        sys.stdout.write("vesper> ")
                        sys.stdout.flush()
                        if self._receive_task and not self._receive_task.done():
                            self._receive_task.cancel()
                        if self._heartbeat_task and not self._heartbeat_task.done():
                            self._heartbeat_task.cancel()
                        self._receive_task = asyncio.create_task(self._receive_loop())
                        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                        self._bg_tasks = [t for t in self._bg_tasks if not t.done()]
                        self._bg_tasks.extend([self._receive_task, self._heartbeat_task])
                except Exception:
                    pass

    async def _receive_loop(self) -> None:
        """Asynchronously listens for server broadcasts and renders them to the console."""
        while self.is_running and self.is_connected:
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
                await self._render_incoming_envelope(envelope)
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                self.websocket = None
                if self.is_running:
                    console.print("\n[bold yellow][DISCONNECT] Gateway connection closed. Attempting reconnect in background...[/bold yellow]")
                    sys.stdout.write("vesper> ")
                    sys.stdout.flush()
                break
            except RuntimeError as re:
                if self.is_running:
                    console.print(f"[dim red][WS Concurrency Break] {re}[/dim red]")
                break
            except Exception as e:
                if self.is_running:
                    console.print(f"[dim red][ERROR] Inbound parse error: {e}[/dim red]")
                await asyncio.sleep(0.5)

    async def _render_incoming_envelope(self, envelope: ServerEnvelope) -> None:
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

        elif envelope.type in (EventType.WAKE_WORD_STATE, EventType.WAKE_WORD_TOGGLE):
            is_active = p.get("wakeword_active")
            if is_active is None and p.get("toggle"):
                is_active = self._wakeword_manually_muted

            if is_active is False or p.get("action") == "pause":
                self._wakeword_manually_muted = True
                if self._wakeword_listener:
                    self._wakeword_listener.pause()
                console.print(f"\n[bold yellow][WAKE WORD] Listener PAUSED (Muted via {p.get('source', 'client')})[/bold yellow]")
            elif is_active is True or p.get("action") == "resume":
                self._wakeword_manually_muted = False
                if self._wakeword_listener and self.is_running:
                    self._wakeword_listener.resume()
                console.print("\n[bold green][WAKE WORD] Listener ARMED[/bold green]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type in (EventType.GESTURE_EVENT, EventType.GESTURE_TOGGLE):
            # Suppress self-echo to avoid duplicate terminal lines
            if p.get("source") == self.client_id:
                return

            gesture = p.get("gesture", "")
            conf = p.get("confidence", 1.0)
            if gesture in ("CLOSED_FIST", "MUTE", "STOP", "INTERRUPT"):
                # If background audio is ducked for wake word, call, or speech, restore it immediately
                if self._voice_duck_state is not None:
                    if self._voice_watchdog_task and not self._voice_watchdog_task.done():
                        self._voice_watchdog_task.cancel()
                    await asyncio.to_thread(_unduck_background_audio, self._voice_duck_state)
                    self._voice_duck_state = None

                if self._call_duck_state is not None:
                    if self._call_watchdog_task and not self._call_watchdog_task.done():
                        self._call_watchdog_task.cancel()
                    await asyncio.to_thread(_unduck_background_audio, self._call_duck_state)
                    self._call_duck_state = None
                    console.print("\n[dim green][CALL DISMISSED] Background audio restored via Closed Fist gesture.[/dim green]")

                if self._tts_duck_state is not None:
                    await asyncio.to_thread(_unduck_background_audio, self._tts_duck_state)
                    self._tts_duck_state = None

                # Fallback sweeper to guarantee all media players and sink inputs are unthrottled
                await asyncio.to_thread(_restore_all_ducked_audio)

                # If assistant is currently speaking or processing voice/research, execute instant touchless cutoff
                is_active = bool(
                    self._current_tts_proc
                    or (self._current_tts_task and not self._current_tts_task.done())
                    or self._is_handling_voice
                )
                if is_active:
                    if self._current_tts_task and not self._current_tts_task.done():
                        self._current_tts_task.cancel()
                    if self._current_tts_proc:
                        try:
                            self._current_tts_proc.terminate()
                        except Exception:
                            pass
                        self._current_tts_proc = None
                    self._is_handling_voice = False
                    self._wakeword_manually_muted = False
                    if self._wakeword_listener and self.is_running:
                        self._wakeword_listener.resume()

                    console.print("\n[bold red][INTERRUPT] Assistant stopped via Closed Fist gesture.[/bold red]")
                    if self.websocket:
                        asyncio.create_task(
                            self.send_envelope(Channel.SYSTEM, EventType.INTERRUPT, {"reason": "GESTURE_CLOSED_FIST"})
                        )
                else:
                    self._wakeword_manually_muted = True
                    if self._wakeword_listener:
                        self._wakeword_listener.pause()
                    console.print(f"\n[bold yellow][WAKE WORD] Listener PAUSED (Gesture: {gesture})[/bold yellow]")
            elif gesture in ("OPEN_PALM", "RESUME", "UNMUTE"):
                if self._voice_duck_state is not None and self._call_duck_state is None:
                    if self._voice_watchdog_task and not self._voice_watchdog_task.done():
                        self._voice_watchdog_task.cancel()
                    await asyncio.to_thread(_unduck_background_audio, self._voice_duck_state)
                    self._voice_duck_state = None

                if self._call_duck_state is not None:
                    if self._call_watchdog_task and not self._call_watchdog_task.done():
                        self._call_watchdog_task.cancel()
                    await asyncio.to_thread(_unduck_background_audio, self._call_duck_state)
                    self._call_duck_state = None
                    console.print("\n[dim green][CALL CONCLUDED] Background audio restored via Open Palm gesture.[/dim green]")

                self._wakeword_manually_muted = False
                if self._wakeword_listener and self.is_running:
                    self._wakeword_listener.resume()
                console.print(f"\n[bold green][WAKE WORD] Listener ARMED (Gesture: {gesture})[/bold green]")
            elif gesture in ("THREE_FINGERS", "PLAY_PAUSE", "MEDIA_PLAY_PAUSE"):
                await asyncio.to_thread(_control_media_player, "play-pause")
                console.print(f"\n[bold yellow][MEDIA_CONTROL] Media Play/Pause toggled via Three Fingers ({gesture})[/bold yellow]")
            elif gesture in ("PEACE_SIGN", "VICTORY", "TOGGLE_ZEN", "ZEN_MODE"):
                console.print(f"\n[bold magenta][ZEN_MODE] Zen Mode toggle signal sent via Peace Sign ({gesture})[/bold magenta]")
                if self.websocket:
                    asyncio.create_task(
                        self.send_envelope(Channel.GESTURE, EventType.GESTURE_EVENT, {"gesture": "PEACE_SIGN"})
                    )
            elif gesture in ("TOGGLE_WAKEWORD", "WAKEWORD_TOGGLE"):
                self._wakeword_manually_muted = not self._wakeword_manually_muted
                if self._wakeword_manually_muted:
                    if self._wakeword_listener:
                        self._wakeword_listener.pause()
                    console.print(f"\n[bold yellow][WAKE WORD] Listener PAUSED (Gesture: {gesture})[/bold yellow]")
                else:
                    if self._wakeword_listener and self.is_running:
                        self._wakeword_listener.resume()
                    console.print(f"\n[bold green][WAKE WORD] Listener ARMED (Gesture: {gesture})[/bold green]")

            elif gesture in ("ROCK_ON", "GESTURE_LOCK", "TOGGLE_GESTURES") or gesture.startswith("GESTURE_TOGGLE"):
                if self._gesture_worker:
                    if ":PAUSED" in gesture:
                        self._gesture_worker.state.tracking_paused = True
                    elif ":RESUMED" in gesture:
                        self._gesture_worker.state.tracking_paused = False
                    elif gesture.startswith("GESTURE_TOGGLE"):
                        self._gesture_worker.state.tracking_paused = not self._gesture_worker.state.tracking_paused
                    else:
                        return
                    is_paused = self._gesture_worker.state.tracking_paused
                    status = "PAUSED (Gestures Locked)" if is_paused else "RESUMED (Gestures Active)"
                    color = "yellow" if is_paused else "green"
                    console.print(f"\n[bold {color}][GESTURES] Tracking {status} via ROCK_ON[/bold {color}]")

            elif gesture.startswith("VOLUME_DIAL:"):
                pass
            else:
                console.print(f"\n[dim green][GESTURE] Recognized: {gesture} (conf={conf:.2f})[/dim green]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.AGENT_ACTIVATING:
            if self._wakeword_listener:
                self._wakeword_listener.pause()
            cmd = p.get("command", "")
            console.print(f"\n[dim cyan][THINKING] Alfred is processing: \"{cmd}\"...[/dim cyan]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.WAKE_WORD_DETECTED:
            # Only print if originated from another cluster client (avoid echo from self)
            if p.get("source") != self.client_id:
                ww = p.get("wake_word", "hey alfred")
                conf = float(p.get("confidence", 1.0))
                console.print(f"\n[bold green][WAKE DETECTED] Wake word detected on cluster: '{ww}' (conf={conf:.2f}). Alfred is listening...[/bold green]")
                sys.stdout.write("vesper> ")
                sys.stdout.flush()

        elif envelope.type == EventType.AGENT_SPEAKING:
            console.print(f"\n[dim green][SPEAKING] Alfred is speaking...[/dim green]")
            sys.stdout.write("vesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.AGENT_IDLE:
            # Do not prematurely unduck if local TTS playback is still underway
            is_speaking = bool(
                self._current_tts_proc
                or (self._current_tts_task and not self._current_tts_task.done())
            )
            if not is_speaking:
                if self._voice_duck_state is not None and self._call_duck_state is None:
                    if self._voice_watchdog_task and not self._voice_watchdog_task.done():
                        self._voice_watchdog_task.cancel()
                    await asyncio.to_thread(_unduck_background_audio, self._voice_duck_state)
                    self._voice_duck_state = None
                if self._tts_duck_state is not None:
                    await asyncio.to_thread(_unduck_background_audio, self._tts_duck_state)
                    self._tts_duck_state = None

            # Standby idle - re-arm microphone listener cleanly once speech finishes unless manually muted
            if self._wakeword_listener and self.is_running and not self._wakeword_manually_muted:
                async def _idle_resume():
                    await asyncio.sleep(0.3)
                    if self._wakeword_listener and self.is_running and not self._is_handling_voice and not self._current_tts_proc and not self._wakeword_manually_muted:
                        self._wakeword_listener.resume()
                asyncio.create_task(_idle_resume())

        elif envelope.type in (EventType.NOTIFICATION_DIGEST, EventType.CALL_STATE) or envelope.channel == Channel.NOTIFY:
            notif = p.get("notification", {})
            title = notif.get("title") or p.get("title") or "Notification Alert"
            app_name = notif.get("app_name") or "Alfred Sentinel"
            speech = p.get("speech") or notif.get("text") or ""
            is_proactive = bool(p.get("proactive") or p.get("action_required"))
            staged = p.get("staged_action")
            body_text = speech or notif.get("text", "")

            # ── Telephony & Call Ducking Interceptor ─────────────────────────
            is_call = bool(p.get("is_call") or notif.get("is_call") or envelope.type == EventType.CALL_STATE)
            call_phase = p.get("call_phase") or notif.get("call_phase") or p.get("state") or p.get("phase")

            if not is_call:
                from backend.sync.notification_service import NotificationService
                pkg = notif.get("package_name") or p.get("package_name") or ""
                is_call, detected_phase = NotificationService.detect_call_event(pkg, title, body_text)
                if detected_phase:
                    call_phase = detected_phase

            if is_call:
                phase = (call_phase or "INCOMING").upper()
                if phase in ("INCOMING", "RINGING", "ACTIVE", "OFFHOOK"):
                    if self._call_duck_state is None:
                        self._call_duck_state = await asyncio.to_thread(_duck_background_audio, 20)
                        caller_label = f"{title}" if title else "Incoming Call"
                        console.print(f"\n[bold red][CALL DETECTED] Background audio ducked to 20% for incoming call ({caller_label}).[/bold red]")

                    # Arm 45-second fallback watchdog to avoid permanent ducking if no call-end event arrives
                    if self._call_watchdog_task and not self._call_watchdog_task.done():
                        self._call_watchdog_task.cancel()

                    async def _call_timeout_watchdog():
                        try:
                            await asyncio.sleep(45.0)
                            if self._call_duck_state:
                                console.print("\n[dim yellow][CALL TIMEOUT] No call-ended update after 45s; restoring audio.[/dim yellow]")
                                await asyncio.to_thread(_unduck_background_audio, self._call_duck_state)
                                self._call_duck_state = None
                        except asyncio.CancelledError:
                            pass

                    self._call_watchdog_task = asyncio.create_task(_call_timeout_watchdog())

                elif phase in ("ENDED", "MISSED", "REJECTED", "DISCONNECTED", "IDLE"):
                    if self._call_duck_state is not None:
                        if self._call_watchdog_task and not self._call_watchdog_task.done():
                            self._call_watchdog_task.cancel()
                        await asyncio.to_thread(_unduck_background_audio, self._call_duck_state)
                        self._call_duck_state = None
                        console.print(f"\n[bold green][CALL CONCLUDED] Restored background audio to original volume ({title}).[/bold green]")

            console.print()
            border = "yellow" if is_proactive else ("red" if is_call and (call_phase or "").upper() in ("INCOMING", "RINGING") else "cyan")
            header = f"[bold yellow][PROACTIVE ADVISORY] {app_name}: {title}[/bold yellow]" if is_proactive else f"[bold {border}][NOTIFICATION] {app_name}: {title}[/bold {border}]"
            if staged:
                body_text += f"\n[dim]Action Staged: {staged.get('domain')}:{staged.get('action')} - Use voice or /help to confirm.[/dim]"

            console.print(
                Panel(
                    f"[bold white]{body_text}[/bold white]",
                    title=header,
                    border_style=border,
                )
            )

            # Trigger real-time speech playback for proactive alerts
            if speech and is_proactive:
                if self._current_tts_task and not self._current_tts_task.done():
                    self._current_tts_task.cancel()
                if self._current_tts_proc:
                    try:
                        self._current_tts_proc.terminate()
                    except Exception:
                        pass
                self._current_tts_task = asyncio.create_task(self._play_tts_response(speech))

            sys.stdout.write("\nvesper> ")
            sys.stdout.flush()

        elif envelope.type == EventType.INTERRUPT:
            # If voice duck state active, restore audio
            if self._voice_duck_state is not None:
                if self._voice_watchdog_task and not self._voice_watchdog_task.done():
                    self._voice_watchdog_task.cancel()
                await asyncio.to_thread(_unduck_background_audio, self._voice_duck_state)
                self._voice_duck_state = None

            # If call duck state active, restore audio
            if self._call_duck_state is not None:
                if self._call_watchdog_task and not self._call_watchdog_task.done():
                    self._call_watchdog_task.cancel()
                await asyncio.to_thread(_unduck_background_audio, self._call_duck_state)
                self._call_duck_state = None

            # If TTS speech duck state active, restore audio
            if self._tts_duck_state is not None:
                await asyncio.to_thread(_unduck_background_audio, self._tts_duck_state)
                self._tts_duck_state = None

            # Fallback sweeper to ensure all media players and sink inputs are unthrottled
            await asyncio.to_thread(_restore_all_ducked_audio)

            # Out-of-band interrupt received: terminate audio playback & reset state
            if self._current_tts_task and not self._current_tts_task.done():
                self._current_tts_task.cancel()
            if self._current_tts_proc:
                try:
                    self._current_tts_proc.terminate()
                except Exception:
                    pass
                self._current_tts_proc = None
            self._is_handling_voice = False
            if self._wakeword_listener and self.is_running and not self._wakeword_manually_muted:
                self._wakeword_listener.resume()
            console.print("\n[bold red][INTERRUPTED] Assistant stopped via interrupt signal.[/bold red]")
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

        if card_type in ("NOTIFICATION_DIGEST", "notification_digest"):
            raw_notifs = card.get("items") or card.get("notifications") or []
            notifs: List[Dict[str, Any]] = raw_notifs if isinstance(raw_notifs, list) else []
            title = card.get("title", "Active Mobile Notifications")
            table = Table(title=title, border_style="cyan", show_lines=True)
            table.add_column("App", style="bold cyan")
            table.add_column("Sender / Title", style="bold")
            table.add_column("Message", style="white")
            table.add_column("Priority", style="yellow")
            for item in notifs:
                table.add_row(
                    str(item.get("app_name", "Mobile")),
                    str(item.get("title", "")),
                    str(item.get("text", ""))[:80],
                    str(item.get("priority", "NORMAL")),
                )
            console.print(table)
            if card.get("unread_emails"):
                console.print(f"[dim cyan]Unread Emails in Inbox: {card.get('unread_emails')}[/dim cyan]")

        elif card_type == "task_list_card":
            table = Table(title="Active Task Ledger", border_style="green", show_lines=True)
            table.add_column("ID", style="dim")
            table.add_column("Title", style="bold")
            table.add_column("Status")
            table.add_column("Priority")
            raw_tasks = card.get("tasks") or []
            tasks: List[Dict[str, Any]] = raw_tasks if isinstance(raw_tasks, list) else []
            for t in tasks:
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

        elif card_type in ("spotify_playlists_card", "spotify_playlists"):
            raw_playlists = card.get("playlists") or []
            playlists: List[Dict[str, Any]] = raw_playlists if isinstance(raw_playlists, list) else []
            table = Table(title=str(card.get("title", "Your Spotify Playlists")), border_style="green", show_lines=True)
            table.add_column("No.", style="dim", width=4)
            table.add_column("Playlist Name", style="bold green")
            table.add_column("Tracks", style="cyan", justify="right")
            table.add_column("Curator / Owner", style="yellow")
            for idx, p in enumerate(playlists, start=1):
                table.add_row(
                    str(idx),
                    str(p.get("name", "Untitled")),
                    str(p.get("total_tracks", "--")),
                    str(p.get("owner", "Spotify")),
                )
            console.print(table)

        elif card_type in ("weather_card",):
            table = Table(title=f"Weather - {card.get('city', 'Unknown')}, {card.get('country', '')}", border_style="cyan")
            table.add_column("Metric", style="bold")
            table.add_column("Value")
            cond = card.get("condition", "--")
            temp = card.get("temperature_c")
            feels = card.get("feels_like_c")
            humidity = card.get("humidity_pct")
            wind = card.get("wind_speed_kmh")
            uv = card.get("uv_index")
            precip = card.get("precip_probability_pct")
            table.add_row("Condition", str(cond))
            if temp is not None:
                table.add_row("Temperature", f"{temp}\u00b0C")
            if feels is not None:
                table.add_row("Feels Like", f"{feels}\u00b0C")
            if humidity is not None:
                table.add_row("Humidity", f"{humidity}%")
            if wind is not None:
                table.add_row("Wind Speed", f"{wind:.0f} km/h")
            if uv is not None:
                table.add_row("UV Index", str(uv))
            if precip is not None:
                table.add_row("Precip. Probability", f"{precip}%")
            if card.get("observed_at"):
                table.add_row("Observed At", str(card["observed_at"]))
            console.print(table)

        elif card_type in ("weather_forecast_card",):
            city = card.get("city", "Unknown")
            country = card.get("country", "")
            table = Table(title=f"Forecast - {city}, {country}", border_style="cyan", show_lines=True)
            table.add_column("Date", style="bold")
            table.add_column("Condition")
            table.add_column("Max", style="red")
            table.add_column("Min", style="blue")
            table.add_column("Rain %", style="cyan")
            table.add_column("UV", style="yellow")
            for d in card.get("days", []):
                table.add_row(
                    str(d.get("date", "--")),
                    str(d.get("condition", "--")),
                    f"{d.get('temp_max_c', '--')}\u00b0C",
                    f"{d.get('temp_min_c', '--')}\u00b0C",
                    f"{d.get('precip_probability_pct', '--')}%",
                    str(d.get("uv_index_max", "--")),
                )
            console.print(table)

        elif card_type in ("weather_rain_card",):
            city = card.get("city", "Unknown")
            rain_likely = card.get("rain_likely", False)
            prob = card.get("max_probability_pct", 0)
            onset = card.get("onset_time", "--")
            cond = card.get("condition_at_onset", "--")
            style = "bold red" if rain_likely else "bold green"
            label = "RAIN LIKELY" if rain_likely else "DRY CONDITIONS"
            table = Table(title=f"Precipitation Check - {city}", border_style="cyan")
            table.add_column("Detail", style="bold")
            table.add_column("Value")
            table.add_row("Status", f"[{style}]{label}[/{style}]")
            table.add_row("Probability", f"{prob}%")
            if rain_likely:
                table.add_row("Onset Time", str(onset))
                table.add_row("Condition", str(cond))
            table.add_row("Hours Checked", str(card.get("hours_checked", "--")))
            console.print(table)

        elif card_type in ("conversation_card",):
            response = card.get("response", "")
            topics = card.get("recent_topics", [])
            console.print(Panel(response, title="Alfred - Conversation", border_style="magenta", padding=(1, 2)))
            if topics:
                console.print(f"[dim magenta]Recent topics: {', '.join(topics[:5])}[/dim magenta]")

        elif card_type in ("conversation_recall_card",):
            results = card.get("results", [])
            topics = card.get("topics", [])
            table = Table(title="Conversation History Recall", border_style="magenta", show_lines=True)
            table.add_column("When", style="dim", width=16)
            table.add_column("Role", width=10)
            table.add_column("Content")
            for r in results[:5]:
                ts = str(r.get("timestamp", ""))[:16]
                table.add_row(ts, r.get("role", "--"), str(r.get("content", ""))[:100])
            console.print(table)
            if topics:
                console.print(f"[dim magenta]Topics covered: {', '.join(topics[:6])}[/dim magenta]")

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
            if gesture == "ROCK_ON":
                return
            if gesture.startswith("GESTURE_TOGGLE"):
                if ":PAUSED" in gesture:
                    console.print("\n[bold yellow][GESTURES] Tracking PAUSED (Rock On / ILoveYou hold 1s). Other gestures disabled.[/bold yellow]")
                elif ":RESUMED" in gesture:
                    console.print("\n[bold green][GESTURES] Tracking RESUMED (Rock On / ILoveYou hold 1s). Gestures active.[/bold green]")
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
                {"gesture": gesture, "confidence": conf, "source": self.client_id},
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
            try:
                loop = self._loop or (asyncio.get_running_loop() if asyncio.get_event_loop().is_running() else None)
                if loop and loop.is_running():
                    loop.create_task(self._gesture_worker.stop())
            except Exception:
                pass
            self._gesture_worker = None
        if self._gesture_task:
            self._gesture_task.cancel()
            self._gesture_task = None
        console.print("[yellow][GESTURES] Disarmed touchless hand tracking (camera released).[/yellow]")

    def stop(self) -> None:
        """Synchronous emergency teardown for signals and quick shutdown."""
        self.is_running = False
        self.stop_gestures()
        self.stop_wakeword()
        if self._current_tts_proc:
            try:
                self._current_tts_proc.terminate()
            except Exception:
                pass
            self._current_tts_proc = None
        if self._voice_duck_state is not None:
            try:
                _unduck_background_audio(self._voice_duck_state)
            except Exception:
                pass
            self._voice_duck_state = None
        if self._call_duck_state is not None:
            try:
                _unduck_background_audio(self._call_duck_state)
            except Exception:
                pass
            self._call_duck_state = None
        if self._tts_duck_state is not None:
            try:
                _unduck_background_audio(self._tts_duck_state)
            except Exception:
                pass
            self._tts_duck_state = None
        _restore_all_ducked_audio()

    async def disconnect(self) -> None:
        """Closes websocket connection, releases camera/mic peripherals, and cancels tasks cleanly."""
        self.is_running = False
        self.stop_wakeword()
        if self._gesture_worker:
            try:
                await self._gesture_worker.stop()
            except Exception:
                pass
            self._gesture_worker = None
        if self._gesture_task:
            self._gesture_task.cancel()
            self._gesture_task = None
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
        if self._current_tts_proc:
            try:
                self._current_tts_proc.terminate()
            except Exception:
                pass
            self._current_tts_proc = None
        if self._voice_watchdog_task and not self._voice_watchdog_task.done():
            self._voice_watchdog_task.cancel()
        if self._call_watchdog_task and not self._call_watchdog_task.done():
            self._call_watchdog_task.cancel()
        if self._voice_duck_state is not None:
            try:
                _unduck_background_audio(self._voice_duck_state)
            except Exception:
                pass
            self._voice_duck_state = None
        if self._call_duck_state is not None:
            try:
                _unduck_background_audio(self._call_duck_state)
            except Exception:
                pass
            self._call_duck_state = None
        if self._tts_duck_state is not None:
            try:
                _unduck_background_audio(self._tts_duck_state)
            except Exception:
                pass
            self._tts_duck_state = None
        _restore_all_ducked_audio()
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        for t in self._bg_tasks:
            t.cancel()
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
        self.websocket = None

    async def _play_tts_response(self, text: str) -> None:
        """Synthesizes and plays Alfred's speech response through host speakers."""
        if not text or not text.strip():
            return

        async with self._tts_lock:
            if self._wakeword_listener:
                self._wakeword_listener.pause()

            temp_audio_path = None
            call_duck_active = self._call_duck_state is not None
            voice_duck_active = self._voice_duck_state is not None
            if not call_duck_active and not voice_duck_active:
                self._tts_duck_state = await asyncio.to_thread(_duck_background_audio, 20)
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
                if self._voice_watchdog_task and not self._voice_watchdog_task.done():
                    self._voice_watchdog_task.cancel()
                if self._tts_duck_state is not None:
                    await asyncio.to_thread(_unduck_background_audio, self._tts_duck_state)
                    self._tts_duck_state = None
                if self._voice_duck_state is not None and not call_duck_active:
                    await asyncio.to_thread(_unduck_background_audio, self._voice_duck_state)
                    self._voice_duck_state = None
                # Unconditionally sweep all streams to restore normal volume!
                await asyncio.to_thread(_restore_all_ducked_audio)
                if temp_audio_path:
                    try:
                        os.unlink(temp_audio_path)
                    except Exception:
                        pass
                if self._wakeword_listener and self.is_running:
                    # Echo dissipation cooldown (500ms) before resuming mic listener
                    await asyncio.sleep(0.5)
                    if self._wakeword_listener and self.is_running and not self._is_handling_voice:
                        self._wakeword_listener.resume()

    def _on_wake_detected(self, event: Any) -> None:
        """Invoked on the main asyncio thread when a wake word is detected."""
        console.print(f"\n[bold green][WAKE DETECTED][/bold green] ('{event.wake_word}', conf={event.confidence:.2f})")
        console.print("[dim cyan]Alfred is listening... (speak your command)[/dim cyan]")

        # Immediately duck background audio so the microphone can cleanly capture the user's speech
        if self._voice_duck_state is None and self._call_duck_state is None:
            async def _duck_on_wake():
                self._voice_duck_state = await asyncio.to_thread(_duck_background_audio, 20)
            asyncio.create_task(_duck_on_wake())

        # Arm a 30s voice interaction watchdog to prevent audio staying ducked if user says nothing or speech pipeline errors
        if self._voice_watchdog_task and not self._voice_watchdog_task.done():
            self._voice_watchdog_task.cancel()

        async def _voice_timeout_watchdog():
            try:
                await asyncio.sleep(30.0)
                if self._voice_duck_state and self._call_duck_state is None:
                    await asyncio.to_thread(_unduck_background_audio, self._voice_duck_state)
                    self._voice_duck_state = None
            except asyncio.CancelledError:
                pass

        self._voice_watchdog_task = asyncio.create_task(_voice_timeout_watchdog())

        if self.websocket:
            asyncio.create_task(
                self.send_envelope(
                    Channel.VOICE,
                    EventType.WAKE_WORD_DETECTED,
                    {
                        "wake_word": str(getattr(event, "wake_word", "hey alfred")),
                        "confidence": float(getattr(event, "confidence", 1.0)),
                        "state": "LISTENING",
                        "source": self.client_id,
                    },
                )
            )

    async def _on_utterance_recorded(self, pcm_bytes: bytes) -> None:
        """Invoked on the main asyncio thread when the user's spoken command is captured."""
        if self._is_handling_voice:
            return
        self._is_handling_voice = True

        # Immediately pause wake word listener so it does not self-trigger while thinking/speaking
        if self._wakeword_listener:
            self._wakeword_listener.pause()

        command_sent = False
        try:
            from backend.voice.audio_utils import pack_pcm_to_wav
            from backend.voice.stt import GroqSpeechToText

            wav_bytes = pack_pcm_to_wav(pcm_bytes, sample_rate=16000)
            stt = GroqSpeechToText()
            transcript = await stt.transcribe_wav(wav_bytes)

            hallucination_phrases = {
                "thank you.", "thank you", "thank you!", "thank you very much.",
                "thanks for watching!", "thanks for watching.", "please subscribe.",
                "you", "bye.", "bye", "thank you so much.", "thank you so much",
                "[music]", "[applause]", "subtitles by", "translated by",
            }
            clean_text = transcript.strip()
            if clean_text and clean_text.lower() not in hallucination_phrases:
                console.print(f'[bold green]You (Voice):[/bold green] "{clean_text}"')
                await self.send_envelope(Channel.VOICE, EventType.VOICE_COMMAND, {"command": clean_text})
                command_sent = True
            else:
                if clean_text:
                    logger.info(f"[Voice] Suppressed ambient silence hallucination: \"{clean_text}\"")
                else:
                    console.print("[dim yellow][Voice] Could not decipher speech.[/dim yellow]")
        except Exception as e:
            console.print(f"[dim red][Voice Error] {e}[/dim red]")
        finally:
            self._is_handling_voice = False
            # If no command was dispatched (silence or hallucination), restore ducked audio and re-arm listener
            if not command_sent:
                if self._voice_duck_state is not None and self._call_duck_state is None:
                    if self._voice_watchdog_task and not self._voice_watchdog_task.done():
                        self._voice_watchdog_task.cancel()
                    asyncio.create_task(asyncio.to_thread(_unduck_background_audio, self._voice_duck_state))
                    self._voice_duck_state = None
                asyncio.create_task(asyncio.to_thread(_restore_all_ducked_audio))

                if self._wakeword_listener and self.is_running:
                    async def _unpause():
                        await asyncio.sleep(0.3)
                        if self._wakeword_listener and self.is_running and not self._is_handling_voice:
                            self._wakeword_listener.resume()
                    asyncio.create_task(_unpause())
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
        console.print("[bold green][WAKE WORD] Armed 'Alfred' and 'Jarvis' continuous listeners.[/bold green]")

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
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._reconnect_task = asyncio.create_task(self._reconnect_supervisor())
        self._bg_tasks.extend([self._receive_task, self._heartbeat_task, self._reconnect_task])

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
                try:
                    r, _, _ = select.select([sys.stdin], [], [], 0.1)
                except (InterruptedError, select.error, OSError):
                    if not self.is_running:
                        return None
                    continue
                if r:
                    try:
                        line = sys.stdin.readline()
                        if not line:
                            return None
                        return line.rstrip("\r\n")
                    except (EOFError, KeyboardInterrupt, OSError):
                        return None
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

            except (EOFError, KeyboardInterrupt, InterruptedError):
                break

        await self.disconnect()

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
        table.add_row("/gesture <NAME>", "Emulate gesture (PEACE_SIGN [zen mode], THREE_FINGERS [media play/pause], CLOSED_FIST [mute], OPEN_PALM [unmute], GUN_RIGHT [next], GUN_LEFT [prev])")
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
    parser.add_argument("--desktop", action="store_true", help="Launch the Tauri v2 Desktop GUI companion alongside background services")
    parser.add_argument("--with-gestures", action="store_true", help="Also arm live webcam touchless gesture tracker")
    parser.add_argument("--with-wakeword", action="store_true", help="Also arm live microphone 'Hey Alfred' wake word listener")
    args = parser.parse_args()

    supervisor = ServiceSupervisor()
    active_hud: Optional[TerminalDesktopHUD] = None

    def signal_handler(sig, frame):
        if active_hud:
            try:
                active_hud.stop()
            except Exception:
                pass
        try:
            _restore_all_ducked_audio()
        except Exception:
            pass
        if not args.client_only:
            supervisor.stop_all()
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def _run():
        nonlocal active_hud
        if not args.client_only:
            ok = await supervisor.start_all()
            if not ok:
                console.print("[bold red]Failed to boot core services. Exiting.[/bold red]")
                return

        if args.services_only:
            # If peripheral daemons (gestures or wake word) are requested, arm them via background gateway link
            peripheral_hud = None
            if args.with_gestures or args.with_wakeword:
                peripheral_hud = TerminalDesktopHUD()
                active_hud = peripheral_hud
                console.print("[dim]Connecting peripheral daemons to Gateway WebSocket...[/dim]")
                connected = await peripheral_hud.connect()
                if connected:
                    peripheral_hud._loop = asyncio.get_running_loop()
                    peripheral_hud._receive_task = asyncio.create_task(peripheral_hud._receive_loop())
                    peripheral_hud._heartbeat_task = asyncio.create_task(peripheral_hud._heartbeat_loop())
                    peripheral_hud._bg_tasks.extend([peripheral_hud._receive_task, peripheral_hud._heartbeat_task])
                    if args.with_gestures:
                        peripheral_hud.start_gestures()
                    if args.with_wakeword:
                        peripheral_hud.start_wakeword()
                else:
                    console.print("[bold red]Failed to connect peripheral daemons to Gateway.[/bold red]")

            console.print("[bold green]VESPER services and peripheral daemons running in background. Press Ctrl+C to stop.[/bold green]")
            try:
                while True:
                    await asyncio.sleep(1.0)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                if peripheral_hud:
                    await peripheral_hud.disconnect()
                if not args.client_only:
                    supervisor.stop_all()
            return

        if args.desktop:
            desktop_dir = PROJECT_ROOT / "desktop"
            console.print("[bold cyan]Launching VESPER Desktop HUD companion...[/bold cyan]")
            desktop_cmd = ["npm", "run", "tauri", "dev"]
            console.print(f"[dim]Spawning desktop process: {' '.join(desktop_cmd)} in {desktop_dir}[/dim]")
            desktop_proc = await asyncio.create_subprocess_exec(
                *desktop_cmd,
                cwd=str(desktop_dir),
            )
            try:
                await desktop_proc.wait()
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                if desktop_proc.returncode is None:
                    try:
                        desktop_proc.terminate()
                        await asyncio.sleep(0.5)
                        if desktop_proc.returncode is None:
                            desktop_proc.kill()
                    except Exception:
                        pass
                if not args.client_only:
                    supervisor.stop_all()
            return

        # Launch Terminal Desktop HUD
        hud = TerminalDesktopHUD()
        active_hud = hud
        console.print(f"[dim]Connecting to Gateway at {GATEWAY_WS_URL}...[/dim]")
        connected = await hud.connect()
        if not connected:
            console.print("[bold red]Failed to connect to Gateway WebSocket. Exiting.[/bold red]")
            if not args.client_only:
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
        pass
    finally:
        try:
            _restore_all_ducked_audio()
        except Exception:
            pass
        if not args.client_only:
            supervisor.stop_all()
    sys.exit(0)


if __name__ == "__main__":
    main()
