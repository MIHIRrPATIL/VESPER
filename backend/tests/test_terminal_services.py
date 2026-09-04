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
