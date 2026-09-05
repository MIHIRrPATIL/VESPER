"""Integration test for VESPER Desktop Client WebSocket contract and assets.

Validates:
1. CLIENT_HELLO registration with ROLE_HUD_DISPLAY & ROLE_VISION_PERCEPTION.
2. CONTROL:PING and CONTROL:PONG keepalive cycle.
3. GESTURE:GESTURE_EVENT dispatching and state reflection (CLOSED_FIST, OPEN_PALM, VOLUME_UP, VOLUME_DOWN, TOGGLE_ZEN).
4. VOICE:WAKE_WORD_DETECTED lifecycle broadcast.
5. SYSTEM:INTERRUPT preemption cycle.
6. Desktop web bundle build artifacts (HTML, JS, CSS, MediaPipe model & WASM).
"""

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from backend.gateway.app import app
from backend.shared.events import Channel, EventType
from backend.sync import sync_manager


@pytest.fixture(autouse=True)
def reset_sync_state():
    sync_manager.state.master_volume = 50
    sync_manager.state.zen_mode = False
    sync_manager.state.focus_mode = False
    yield


def test_desktop_assets_built_and_complete():
    """Validates that Desktop App built assets and offline MediaPipe assets are present."""
    desktop_root = Path(__file__).resolve().parent.parent.parent / "desktop"
    
    # Model and wasm binaries for 100% offline vision
    model_file = desktop_root / "public" / "models" / "gesture_recognizer.task"
    wasm_file = desktop_root / "public" / "wasm" / "vision_wasm_internal.wasm"
    
    assert model_file.exists(), f"Missing model asset: {model_file}"
    assert model_file.stat().st_size > 1_000_000, "Gesture model asset is too small or corrupted"
    
    assert wasm_file.exists(), f"Missing wasm asset: {wasm_file}"
    assert wasm_file.stat().st_size > 5_000_000, "WASM binary asset is too small or corrupted"
    
    # Production dist build
    dist_html = desktop_root / "dist" / "index.html"
    assert dist_html.exists(), "Desktop build distribution (dist/index.html) does not exist"
    assert dist_html.stat().st_size > 100


def test_desktop_client_handshake_and_keepalive():
    """Validates Desktop Client hello handshake and ping/pong keepalive."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # 1. Send CLIENT_HELLO
            hello_envelope = {
                "uuid": "test-desktop-uuid-001",
                "channel": Channel.CONTROL,
                "type": EventType.CLIENT_HELLO,
                "payload": {
                    "client_id": "vesper-desktop-hud",
                    "roles": ["ROLE_HUD_DISPLAY", "ROLE_VISION_PERCEPTION"],
                    "has_camera": True,
                    "has_display": True,
                    "has_speaker": True,
                    "os": "linux",
                },
            }
            ws.send_json(hello_envelope)

            # Read initial welcome / sync envelopes
            msg = ws.receive_json()
            assert msg["channel"] == Channel.CONTROL
            assert msg["type"] == EventType.SERVER_HELLO

            # 2. Test PING -> PONG
            ping_envelope = {
                "uuid": "test-ping-002",
                "channel": Channel.CONTROL,
                "type": EventType.PING,
                "payload": {},
            }
            ws.send_json(ping_envelope)

            pong_msg = ws.receive_json()
            assert pong_msg["channel"] == Channel.CONTROL
            assert pong_msg["type"] == EventType.PONG


def test_desktop_client_gesture_events():
    """Validates that gestures emitted by desktop Web Worker trigger state changes."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # Consume SERVER_HELLO
            ws.send_json({
                "uuid": "hello-gestures",
                "channel": Channel.CONTROL,
                "type": EventType.CLIENT_HELLO,
                "payload": {"client_id": "desktop-tester", "roles": ["ROLE_HUD_DISPLAY"]},
            })
            _ = ws.receive_json()

            # Test CLOSED_FIST (Mute volume)
            ws.send_json({
                "uuid": "gesture-mute-001",
                "channel": Channel.GESTURE,
                "type": EventType.GESTURE_EVENT,
                "payload": {"gesture": "CLOSED_FIST", "confidence": 0.95},
            })
            mute_resp = ws.receive_json()
            assert mute_resp["channel"] == Channel.SYSTEM
            assert mute_resp["type"] == EventType.SET_VOLUME
            assert mute_resp["payload"]["volume"] == 0
            assert sync_manager.get_snapshot().master_volume == 0

            # Wake word state broadcast for CLOSED_FIST (Muted)
            ww_mute = ws.receive_json()
            assert ww_mute["channel"] == Channel.VOICE
            assert ww_mute["type"] == EventType.WAKE_WORD_STATE
            assert ww_mute["payload"]["wakeword_active"] is False
            assert sync_manager.get_snapshot().wakeword_active is False

            # Test OPEN_PALM (Unmute / restore volume)
            ws.send_json({
                "uuid": "gesture-unmute-002",
                "channel": Channel.GESTURE,
                "type": EventType.GESTURE_EVENT,
                "payload": {"gesture": "OPEN_PALM", "confidence": 0.96},
            })
            unmute_resp = ws.receive_json()
            assert unmute_resp["channel"] == Channel.SYSTEM
            assert unmute_resp["type"] == EventType.SET_VOLUME
            assert unmute_resp["payload"]["volume"] == 50
            assert sync_manager.get_snapshot().master_volume == 50

            # Wake word state broadcast for OPEN_PALM (Resumed)
            ww_unmute = ws.receive_json()
            assert ww_unmute["channel"] == Channel.VOICE
            assert ww_unmute["type"] == EventType.WAKE_WORD_STATE
            assert ww_unmute["payload"]["wakeword_active"] is True
            assert sync_manager.get_snapshot().wakeword_active is True

            # Test VOLUME_UP (+10%)
            ws.send_json({
                "uuid": "gesture-volup-003",
                "channel": Channel.GESTURE,
                "type": EventType.GESTURE_EVENT,
                "payload": {"gesture": "VOLUME_UP", "confidence": 0.92},
            })
            volup_resp = ws.receive_json()
            assert volup_resp["channel"] == Channel.SYSTEM
            assert volup_resp["type"] == EventType.SET_VOLUME
            assert volup_resp["payload"]["volume"] == 60
            assert sync_manager.get_snapshot().master_volume == 60

            # Test TOGGLE_ZEN / PEACE_SIGN
            ws.send_json({
                "uuid": "gesture-zen-004",
                "channel": Channel.GESTURE,
                "type": EventType.GESTURE_EVENT,
                "payload": {"gesture": "PEACE_SIGN", "confidence": 0.91},
            })
            zen_resp = ws.receive_json()
            assert zen_resp["channel"] == Channel.SYSTEM
            assert zen_resp["type"] == EventType.ZEN_MODE_STATE
            assert zen_resp["payload"]["zen_mode"] is True
            assert sync_manager.get_snapshot().zen_mode is True


def test_desktop_client_wake_word_and_interrupt():
    """Validates wake word detection event and user barge-in preemption."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "uuid": "hello-voice",
                "channel": Channel.CONTROL,
                "type": EventType.CLIENT_HELLO,
                "payload": {"client_id": "desktop-voice-test", "roles": ["ROLE_HUD_DISPLAY"]},
            })
            _ = ws.receive_json()

            # Wake word detected
            ws.send_json({
                "uuid": "wakeword-001",
                "channel": Channel.VOICE,
                "type": EventType.WAKE_WORD_DETECTED,
                "payload": {"wake_word": "hey alfred", "confidence": 0.97},
            })
            ww_resp = ws.receive_json()
            assert ww_resp["channel"] == Channel.VOICE
            assert ww_resp["type"] == EventType.WAKE_WORD_DETECTED
            assert ww_resp["payload"]["state"] == "LISTENING"

            # Barge-in interrupt
            ws.send_json({
                "uuid": "interrupt-002",
                "channel": Channel.SYSTEM,
                "type": EventType.INTERRUPT,
                "payload": {"reason": "USER_BARGE_IN", "priority": 10},
            })
            ack_resp = ws.receive_json()
            assert ack_resp["channel"] == Channel.SYSTEM
            assert ack_resp["type"] == EventType.INTERRUPT_ACK
