"""Tests for the Unified Terminal Service Supervisor and Terminal Desktop HUD."""

import asyncio
import pytest
import httpx
import websockets
import json

from scripts.run_vesper_services import ServiceSupervisor, TerminalDesktopHUD
from backend.shared.events import Channel, ClientEnvelope, EventType, ServerEnvelope


@pytest.mark.asyncio
async def test_supervisor_boot_and_hud_websocket_roundtrip():
    """Verifies that ServiceSupervisor boots Gateway, Agent, Voice, and TerminalDesktopHUD connects and interacts."""
    supervisor = ServiceSupervisor()

    try:
        # 1. Boot core services
        boot_ok = await supervisor.start_all(with_gestures=False, with_wakeword=False)
        assert boot_ok is True, "ServiceSupervisor failed to boot core microservices"

        # 2. Verify /health endpoints on all 3 services
        async with httpx.AsyncClient(timeout=2.0) as client:
            res_gw = await client.get("http://localhost:8000/health")
            assert res_gw.status_code == 200
            assert res_gw.json().get("status") in ("ok", "healthy")

            res_agent = await client.get("http://localhost:8001/health")
            assert res_agent.status_code == 200
            assert res_agent.json().get("status") in ("ok", "healthy")

            res_voice = await client.get("http://localhost:8002/health")
            assert res_voice.status_code == 200
            assert res_voice.json().get("status") in ("ok", "healthy")

        # 3. Connect TerminalDesktopHUD over WebSocket
        hud = TerminalDesktopHUD()
        connected = await hud.connect()
        assert connected is True, "TerminalDesktopHUD failed to connect & handshake with Gateway"
        assert hud.session_id is not None

        # 4. Dispatch a gesture event through the WebSocket
        await hud.send_envelope(
            Channel.GESTURE,
            EventType.GESTURE_EVENT,
            {"gesture": "PEACE_SIGN", "confidence": 1.0},
        )

        # Allow Gateway router to process gesture and broadcast state update
        await asyncio.sleep(0.5)

        # Check that cluster snapshot updated
        async with httpx.AsyncClient(timeout=2.0) as client:
            res_state = await client.get("http://localhost:8000/sync/snapshot")
            assert res_state.status_code == 200
            data = res_state.json()
            assert "zen_mode" in data

        # Clean close HUD websocket
        if hud.websocket:
            await hud.websocket.close()

    finally:
        # 5. Clean teardown of all subprocesses
        supervisor.stop_all()
        await asyncio.sleep(1.0)


@pytest.mark.asyncio
async def test_hud_heartbeat_ping_pong_keeps_alive():
    """Verifies that TerminalDesktopHUD replies to server PING with PONG, preventing eviction."""
    supervisor = ServiceSupervisor()

    try:
        boot_ok = await supervisor.start_all()
        assert boot_ok is True

        hud = TerminalDesktopHUD()
        connected = await hud.connect()
        assert connected is True

        # Start receive loop (which replies to PING with PONG)
        recv_task = asyncio.create_task(hud._receive_loop())

        # Wait 18 seconds to cross Gateway's 15-second heartbeat interval
        await asyncio.sleep(18.0)

        # Connection MUST still be open and active!
        assert hud.websocket is not None
        assert hud.websocket.close_code is None, "WebSocket was prematurely closed or evicted by Gateway!"

        recv_task.cancel()
        await hud.websocket.close()

    finally:
        supervisor.stop_all()
        await asyncio.sleep(1.0)


@pytest.mark.asyncio
async def test_hud_instant_stand_down_on_dismiss_utterance(monkeypatch):
    """Verifies that saying 'Nothing, Jarvis' triggers instant 0ms stand-down, audio restoration, and no TTS delay."""
    from unittest.mock import AsyncMock, patch
    from backend.voice.stt import GroqSpeechToText

    hud = TerminalDesktopHUD()
    hud.is_running = True
    hud.websocket = object()
    hud._voice_duck_state = {"ducked": True}
    sent_envelopes = []

    async def mock_send_envelope(channel, event_type, payload):
        sent_envelopes.append((channel, event_type, payload))

    monkeypatch.setattr(hud, "send_envelope", mock_send_envelope)
    monkeypatch.setattr(GroqSpeechToText, "transcribe_wav", AsyncMock(return_value="Nothing, Jarvis."))

    # Generate mock PCM bytes (16000 samples * 2 bytes = 1s)
    pcm = b"\x00\x00" * 16000
    await hud._on_utterance_recorded(pcm)

    # Voice duck state must be cleared immediately
    assert hud._voice_duck_state is None
    assert hud._is_handling_voice is False
    # Envelope sent must be AGENT_IDLE with STAND_DOWN
    assert len(sent_envelopes) == 1
    ch, ev, payload = sent_envelopes[0]
    assert ch == Channel.VOICE
    assert ev == EventType.AGENT_IDLE
    assert payload.get("reason") == "STAND_DOWN"


@pytest.mark.asyncio
async def test_hud_instant_gesture_cancel_during_voice_interaction(monkeypatch):
    """Verifies that THUMB_DOWN during active voice listening cancels interaction immediately and restores audio."""
    hud = TerminalDesktopHUD()
    hud.is_running = True
    hud.websocket = object()
    hud._voice_duck_state = {"ducked": True}
    sent_envelopes = []

    async def mock_send_envelope(channel, event_type, payload):
        sent_envelopes.append((channel, event_type, payload))

    monkeypatch.setattr(hud, "send_envelope", mock_send_envelope)

    # Initialize gestures with callback
    hud.start_gestures()
    try:
        assert hud._gesture_worker is not None
        callback = hud._gesture_worker.on_gesture_callback
        assert callback is not None

        # Simulate detecting THUMB_DOWN during active voice interaction
        await callback("THUMB_DOWN", 0.92)

        # Voice duck state must be restored immediately
        assert hud._voice_duck_state is None
        assert hud._is_handling_voice is False

        # Must have sent INTERRUPT to Gateway
        assert len(sent_envelopes) == 1
        ch, ev, payload = sent_envelopes[0]
        assert ch == Channel.SYSTEM
        assert ev == EventType.INTERRUPT
        assert payload.get("reason") == "USER_GESTURE_DISMISS"
    finally:
        hud.stop_gestures()


@pytest.mark.asyncio
async def test_hud_sends_agent_idle_on_empty_or_short_pcm(monkeypatch):
    """Verifies that empty or <350ms PCM sends AGENT_IDLE with TIMEOUT_NO_SPEECH."""
    hud = TerminalDesktopHUD()
    hud.is_running = True
    hud.websocket = object()
    hud._voice_duck_state = {"ducked": True}
    sent_envelopes = []

    async def mock_send_envelope(channel, event_type, payload):
        sent_envelopes.append((channel, event_type, payload))

    monkeypatch.setattr(hud, "send_envelope", mock_send_envelope)

    # Short PCM: 100ms (16000 * 2 * 0.10 bytes)
    short_pcm = b"\x00\x00" * 1600
    await hud._on_utterance_recorded(short_pcm)

    # Must emit AGENT_IDLE
    assert len(sent_envelopes) >= 1
    ch, ev, payload = sent_envelopes[0]
    assert ch == Channel.VOICE
    assert ev == EventType.AGENT_IDLE
    assert payload.get("reason") == "TIMEOUT_NO_SPEECH"
    assert hud._voice_duck_state is None
    assert hud._is_handling_voice is False


@pytest.mark.asyncio
async def test_hud_sends_agent_idle_on_suppressed_hallucination(monkeypatch):
    """Verifies that suppressed ambient hallucinations send AGENT_IDLE with UNRECOGNIZED_SPEECH."""
    from unittest.mock import AsyncMock
    from backend.voice.stt import GroqSpeechToText

    hud = TerminalDesktopHUD()
    hud.is_running = True
    hud.websocket = object()
    hud._voice_duck_state = {"ducked": True}
    sent_envelopes = []

    async def mock_send_envelope(channel, event_type, payload):
        sent_envelopes.append((channel, event_type, payload))

    monkeypatch.setattr(hud, "send_envelope", mock_send_envelope)
    # Whisper hallucination on background audio
    monkeypatch.setattr(GroqSpeechToText, "transcribe_wav", AsyncMock(return_value="[Music] Thank you."))

    pcm = b"\x00\x00" * 16000
    await hud._on_utterance_recorded(pcm)

    assert len(sent_envelopes) >= 1
    ch, ev, payload = sent_envelopes[0]
    assert ch == Channel.VOICE
    assert ev == EventType.AGENT_IDLE
    assert payload.get("reason") == "UNRECOGNIZED_SPEECH"
    assert hud._voice_duck_state is None
    assert hud._is_handling_voice is False


@pytest.mark.asyncio
async def test_hud_sends_agent_idle_on_voice_watchdog_timeout(monkeypatch):
    """Verifies that watchdog timeout restores ducked audio and sends AGENT_IDLE."""
    hud = TerminalDesktopHUD()
    hud.is_running = True
    hud.websocket = object()
    hud._voice_duck_state = {"ducked": True}
    sent_envelopes = []

    async def mock_send_envelope(channel, event_type, payload):
        sent_envelopes.append((channel, event_type, payload))

    monkeypatch.setattr(hud, "send_envelope", mock_send_envelope)

    # Run the watchdog timeout coroutine directly (0s timeout for test)
    await hud._voice_timeout_watchdog(timeout_sec=0)

    assert hud._voice_duck_state is None
    assert len(sent_envelopes) >= 1
    ch, ev, payload = sent_envelopes[0]
    assert ch == Channel.VOICE
    assert ev == EventType.AGENT_IDLE
    assert payload.get("reason") == "VOICE_TIMEOUT"


@pytest.mark.asyncio
async def test_tts_ack_preserves_voice_duck_state(monkeypatch):
    """Verifies that an acknowledgement TTS (is_ack=True) does not clear _voice_duck_state."""
    hud = TerminalDesktopHUD()
    hud.is_running = True
    hud._voice_duck_state = {"ducked": True}

    class MockTTSMgr:
        async def stream_speech(self, text):
            # Yield dummy WAV header bytes
            yield b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    hud._tts_mgr = MockTTSMgr()

    # Mock subprocess creation so ffplay is not spawned
    async def mock_create_subprocess_exec(*args, **kwargs):
        class MockProc:
            returncode = 0
            async def communicate(self):
                return b"", b""
            def poll(self):
                return 0
        return MockProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    # Play ack TTS
    await hud._play_tts_response("Looking into that for you, sir.", is_ack=True)

    # Voice duck state MUST be preserved so background audio remains ducked for user speech/processing
    assert hud._voice_duck_state == {"ducked": True}



