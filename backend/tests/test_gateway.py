"""Automated Test Suite for the VESPER API Gateway.

Tests WebSocket connection handshakes, channel multiplexing, heartbeats,
and instant out-of-band barge-in cancellation.
"""

from __future__ import annotations

import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from backend.gateway.app import create_app
from backend.shared.events import (
    Channel,
    ClientEnvelope,
    ClientType,
    EventType,
)


@pytest.fixture
def client():
    """Creates a TestClient using the Gateway FastAPI app."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


# ── 1. HTTP Endpoint Tests ────────────────────────────────────────────────

def test_health_check(client: TestClient):
    """Verifies that the /health REST endpoint reports ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "vesper-gateway"
    assert "active_clients" in data
    assert "uptime_seconds" in data


def test_list_clients_empty(client: TestClient):
    """Verifies /clients returns empty list when no clients are connected."""
    response = client.get("/clients")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["clients"] == []


# ── 2. WebSocket Handshake Tests ──────────────────────────────────────────

def test_websocket_successful_handshake(client: TestClient):
    """Tests clean CLIENT_HELLO -> SERVER_HELLO handshake."""
    with client.websocket_connect("/ws") as ws:
        # Send CLIENT_HELLO
        hello_msg = {
            "uuid": "test-hello-01",
            "channel": Channel.CONTROL.value,
            "type": EventType.CLIENT_HELLO.value,
            "payload": {
                "client_id": "test-desk-hud",
                "client_type": ClientType.DESK_HUD.value,
                "version": "2.0.0",
                "capabilities": ["audio_stream", "gestures"],
            },
        }
        ws.send_text(json.dumps(hello_msg))

        # Receive SERVER_HELLO
        raw_resp = ws.receive_text()
        resp = json.loads(raw_resp)

        assert resp["channel"] == Channel.CONTROL.value
        assert resp["type"] == EventType.SERVER_HELLO.value
        assert resp["status"] == "ok"
        assert resp["payload"]["status"] == "authenticated"
        assert "sess_" in resp["payload"]["session_id"]


def test_websocket_rejects_non_hello_first_frame(client: TestClient):
    """Tests that sending an event other than CLIENT_HELLO first closes the socket."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws") as ws:
            bad_msg = {
                "uuid": "test-bad-01",
                "channel": Channel.VOICE.value,
                "type": EventType.VOICE_COMMAND.value,
                "payload": {"command": "hello"},
            }
            ws.send_text(json.dumps(bad_msg))
            ws.receive_text()  # Should close socket


# ── 3. Multiplexed Channel Tests ──────────────────────────────────────────

def test_voice_command_roundtrip(client: TestClient):
    """Tests sending a VOICE_COMMAND and receiving the processed response."""
    with client.websocket_connect("/ws") as ws:
        # 1. Handshake
        ws.send_text(json.dumps({
            "uuid": "h1",
            "channel": Channel.CONTROL.value,
            "type": EventType.CLIENT_HELLO.value,
            "payload": {"client_id": "test-user", "client_type": ClientType.DEV_TEST.value},
        }))
        ws.receive_text()  # SERVER_HELLO

        # 2. Send Voice Command
        cmd_uuid = "voice-req-123"
        ws.send_text(json.dumps({
            "uuid": cmd_uuid,
            "channel": Channel.VOICE.value,
            "type": EventType.VOICE_COMMAND.value,
            "payload": {"command": "What time is it?", "is_final": True},
        }))

        # 3. Receive Agent Response
        raw_resp = ws.receive_text()
        resp = json.loads(raw_resp)

        assert resp["uuid"] == cmd_uuid
        assert resp["channel"] == Channel.VOICE.value
        assert resp["type"] == EventType.AGENT_RESPONSE.value
        assert len(resp["payload"]["response"]) > 0


def test_gesture_event_broadcast(client: TestClient):
    """Tests sending a GESTURE_EVENT (TOGGLE_ZEN) and receiving broadcast."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_text(json.dumps({
            "uuid": "h2",
            "channel": Channel.CONTROL.value,
            "type": EventType.CLIENT_HELLO.value,
            "payload": {"client_id": "test-desk", "client_type": ClientType.DESK_HUD.value},
        }))
        ws.receive_text()

        # Send Gesture
        ws.send_text(json.dumps({
            "uuid": "g-01",
            "channel": Channel.GESTURE.value,
            "type": EventType.GESTURE_EVENT.value,
            "payload": {"gesture": "TOGGLE_ZEN"},
        }))

        # Receive Broadcast
        raw_resp = ws.receive_text()
        resp = json.loads(raw_resp)

        assert resp["channel"] == Channel.SYSTEM.value
        assert resp["type"] == EventType.ZEN_MODE_STATE.value
        assert resp["payload"]["toggle"] is True


def test_gesture_broadcast_closed_fist_and_open_palm(client: TestClient):
    """Tests that CLOSED_FIST mutes/pauses and OPEN_PALM restores volume/playback."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_text(json.dumps({
            "uuid": "h-gest",
            "channel": Channel.CONTROL.value,
            "type": EventType.CLIENT_HELLO.value,
            "payload": {"client_id": "test-gest-hud", "client_type": ClientType.DESK_HUD.value},
        }))
        ws.receive_text()

        # Send CLOSED_FIST (Mute/Pause)
        ws.send_text(json.dumps({
            "uuid": "g-fist",
            "channel": Channel.GESTURE.value,
            "type": EventType.GESTURE_EVENT.value,
            "payload": {"gesture": "CLOSED_FIST"},
        }))
        resp_fist = json.loads(ws.receive_text())
        assert resp_fist["channel"] == Channel.SYSTEM.value
        assert resp_fist["type"] == EventType.SET_VOLUME.value
        assert resp_fist["payload"]["volume"] == 0
        assert resp_fist["payload"]["muted"] is True

        # Send OPEN_PALM (Resume/Play)
        ws.send_text(json.dumps({
            "uuid": "g-palm",
            "channel": Channel.GESTURE.value,
            "type": EventType.GESTURE_EVENT.value,
            "payload": {"gesture": "OPEN_PALM"},
        }))
        resp_palm = json.loads(ws.receive_text())
        assert resp_palm["channel"] == Channel.SYSTEM.value
        assert resp_palm["type"] == EventType.SET_VOLUME.value
        assert resp_palm["payload"]["volume"] > 0
        assert resp_palm["payload"]["muted"] is False

        # Send VOLUME_DIAL:75
        ws.send_text(json.dumps({
            "uuid": "g-dial",
            "channel": Channel.GESTURE.value,
            "type": EventType.GESTURE_EVENT.value,
            "payload": {"gesture": "VOLUME_DIAL:75"},
        }))
        resp_dial = json.loads(ws.receive_text())
        assert resp_dial["channel"] == Channel.SYSTEM.value
        assert resp_dial["type"] == EventType.SET_VOLUME.value
        assert resp_dial["payload"]["volume"] == 75

        # Send NEXT_TRACK
        ws.send_text(json.dumps({
            "uuid": "g-next",
            "channel": Channel.GESTURE.value,
            "type": EventType.GESTURE_EVENT.value,
            "payload": {"gesture": "NEXT_TRACK"},
        }))
        resp_next = json.loads(ws.receive_text())
        assert resp_next["channel"] == Channel.SYSTEM.value
        assert resp_next["type"] == EventType.MEDIA_CONTROL.value
        assert resp_next["payload"]["action"] == "next_track"

        # Send THUMB_UP (+10% volume)
        ws.send_text(json.dumps({
            "uuid": "g-up",
            "channel": Channel.GESTURE.value,
            "type": EventType.GESTURE_EVENT.value,
            "payload": {"gesture": "THUMB_UP"},
        }))
        resp_up = json.loads(ws.receive_text())
        assert resp_up["channel"] == Channel.SYSTEM.value
        assert resp_up["type"] == EventType.SET_VOLUME.value
        assert resp_up["payload"]["volume"] == 85


def test_notification_relay_broadcast(client: TestClient):
    """Tests ingesting a mobile NOTIFICATION_RELAY and receiving ambient digest."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_text(json.dumps({
            "uuid": "h3",
            "channel": Channel.CONTROL.value,
            "type": EventType.CLIENT_HELLO.value,
            "payload": {"client_id": "test-phone", "client_type": ClientType.MOBILE_ANDROID.value},
        }))
        ws.receive_text()

        # Send Mobile Notification
        ws.send_text(json.dumps({
            "uuid": "notif-01",
            "channel": Channel.NOTIFY.value,
            "type": EventType.NOTIFICATION_RELAY.value,
            "payload": {
                "package_name": "com.whatsapp",
                "sender": "Project Lead",
                "title": "Status Update",
                "text": "PR is ready for review",
                "is_priority_contact": True,
            },
        }))

        # Receive Digest Broadcast
        raw_resp = ws.receive_text()
        resp = json.loads(raw_resp)

        assert resp["channel"] == Channel.NOTIFY.value
        assert resp["type"] == EventType.NOTIFICATION_DIGEST.value
        assert resp["payload"]["notification"]["title"] == "Status Update"


# ── 4. Instant Barge-In Cancellation Test ─────────────────────────────────

def test_interrupt_task_cancellation(client: TestClient):
    """Tests that sending an out-of-band INTERRUPT frame cancels an active task."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_text(json.dumps({
            "uuid": "h4",
            "channel": Channel.CONTROL.value,
            "type": EventType.CLIENT_HELLO.value,
            "payload": {"client_id": "test-desk", "client_type": ClientType.DESK_HUD.value},
        }))
        ws.receive_text()

        # Start a voice command
        target_uuid = "long-running-ai-turn"
        ws.send_text(json.dumps({
            "uuid": target_uuid,
            "channel": Channel.VOICE.value,
            "type": EventType.VOICE_COMMAND.value,
            "payload": {"command": "Explain general relativity in depth"},
        }))

        # Immediately send out-of-band INTERRUPT signal targeting that UUID
        ws.send_text(json.dumps({
            "uuid": "interrupt-01",
            "channel": Channel.SYSTEM.value,
            "type": EventType.INTERRUPT.value,
            "payload": {"target_uuid": target_uuid, "reason": "USER_BARGE_IN_VAD"},
        }))

        # Collect response frames (either the interrupt ack or response)
        frames = []
        for _ in range(2):
            try:
                raw = ws.receive_text()
                frames.append(json.loads(raw))
            except Exception:
                break

        # Verify an INTERRUPT_ACK frame was received
        interrupt_acks = [f for f in frames if f.get("type") == EventType.INTERRUPT_ACK.value]
        assert len(interrupt_acks) >= 1
        ack = interrupt_acks[0]
        assert ack["channel"] == Channel.SYSTEM.value
        assert ack["payload"]["target_uuid"] == target_uuid


# ── 5. Error Resilience Test ──────────────────────────────────────────────

def test_malformed_envelope_returns_error_without_disconnect(client: TestClient):
    """Tests that sending a malformed envelope returns an ERROR frame and keeps socket alive."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_text(json.dumps({
            "uuid": "h5",
            "channel": Channel.CONTROL.value,
            "type": EventType.CLIENT_HELLO.value,
            "payload": {"client_id": "test-desk", "client_type": ClientType.DEV_TEST.value},
        }))
        ws.receive_text()

        # Send invalid envelope (missing required fields)
        ws.send_text(json.dumps({"bad_key": 123}))

        # Gateway should return an ERROR frame, not drop the connection
        raw_resp = ws.receive_text()
        resp = json.loads(raw_resp)

        assert resp["type"] == EventType.ERROR.value
        assert resp["status"] == "error"
        assert "Malformed envelope" in resp["payload"]["message"]

        # Confirm socket is still alive by sending a valid ping
        ws.send_text(json.dumps({
            "uuid": "ping-01",
            "channel": Channel.CONTROL.value,
            "type": EventType.PING.value,
            "payload": {},
        }))
        raw_pong = ws.receive_text()
        pong = json.loads(raw_pong)
        assert pong["type"] == EventType.PONG.value
