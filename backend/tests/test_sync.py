"""Tests for VESPER Cross-Device State Synchronization Subsystem.

Verifies:
1. SyncManager device registration and topology (Desktop, Orange Pi, Mobile).
2. State diff updates and subscriber notifications.
3. Heartbeat recording and stale node pruning.
4. REST endpoints for cluster state and device registration (/sync/*).
5. Gateway WebSocket Channel.SYNC integration (DEVICE_REGISTER, STATE_SYNC).
"""

from __future__ import annotations

from typing import Any
import pytest
from httpx import ASGITransport, AsyncClient


from backend.gateway.app import app as gateway_app
from backend.shared.events import Channel, ClientEnvelope, EventType, ServerEnvelope
from backend.sync.models import DeviceRegistration, SynchronizedState
from backend.sync.sync_manager import SyncManager


@pytest.fixture
def clean_sync_manager():
    """Provides a fresh SyncManager instance for isolated test execution."""
    mgr = SyncManager()
    return mgr


@pytest.mark.asyncio
async def test_sync_manager_device_registration(clean_sync_manager: SyncManager):
    """Verifies registering heterogeneous devices into the cluster."""
    # Register Arch Linux Desktop
    desktop = DeviceRegistration(
        device_id="desktop-arch",
        device_type="desktop",
        device_name="Arch Workstation",
        has_camera=True,
        has_display=True,
    )
    await clean_sync_manager.register_device(desktop)

    # Register Orange Pi 5 Plus (Edge Node, no camera)
    orange_pi = DeviceRegistration(
        device_id="edge-orange-pi-01",
        device_type="orange_pi",
        device_name="Orange Pi 5 Plus Node",
        has_camera=False,
        has_display=False,
        is_headless=True,
    )
    await clean_sync_manager.register_device(orange_pi)

    active_devices = clean_sync_manager.get_active_devices()
    assert len(active_devices) == 2

    # Verify Orange Pi node topology
    opi_node = clean_sync_manager.state.active_devices["edge-orange-pi-01"]
    assert opi_node.device_type == "orange_pi"
    assert opi_node.has_camera is False
    assert opi_node.is_headless is True


@pytest.mark.asyncio
async def test_sync_manager_state_diff_and_listeners(clean_sync_manager: SyncManager):
    """Verifies applying state diffs and notifying listeners."""
    diff_payloads: list[dict[str, Any]] = []

    def on_change(state: SynchronizedState, diff: dict):
        diff_payloads.append(diff)

    clean_sync_manager.add_listener(on_change)

    # Apply volume and zen mode changes
    updated = await clean_sync_manager.update_state(
        {"master_volume": 75, "zen_mode": True}, source_device_id="desktop-arch"
    )

    assert updated.master_volume == 75
    assert updated.zen_mode is True
    assert len(diff_payloads) == 1
    assert diff_payloads[0]["master_volume"] == 75



@pytest.mark.asyncio
async def test_sync_manager_heartbeat_and_pruning(clean_sync_manager: SyncManager):
    """Verifies node heartbeat tracking and pruning."""
    dev = DeviceRegistration(
        device_id="temp-companion",
        device_type="mobile_hud",
        device_name="Android HUD",
    )
    await clean_sync_manager.register_device(dev)

    # Valid heartbeat
    assert await clean_sync_manager.record_heartbeat("temp-companion") is True
    assert await clean_sync_manager.record_heartbeat("non-existent-device") is False

    # Simulate old heartbeat
    clean_sync_manager.state.active_devices["temp-companion"].last_heartbeat -= 40.0
    pruned = await clean_sync_manager.prune_stale_devices(timeout_sec=30.0)

    assert "temp-companion" in pruned
    assert clean_sync_manager.state.active_devices["temp-companion"].is_online is False


@pytest.mark.asyncio
async def test_sync_rest_endpoints():
    """Verifies REST endpoints for state and device management."""
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get state snapshot
        res = await client.get("/sync/state")
        assert res.status_code == 200
        data = res.json()
        assert "master_volume" in data
        assert "version" in data

        # 2. Update state diff
        update_res = await client.post(
            "/sync/state",
            json={"diff": {"master_volume": 42, "focus_mode": True}, "source_device_id": "test_agent"},
        )
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["master_volume"] == 42
        assert updated_data["focus_mode"] is True

        # 3. Register device via REST
        reg_payload = {
            "device_id": "opi-rest-test",
            "device_type": "orange_pi",
            "device_name": "Orange Pi Zero 3",
            "has_camera": False,
            "has_display": False,
            "is_headless": True,
        }
        reg_res = await client.post("/sync/devices/register", json=reg_payload)
        assert reg_res.status_code == 200
        assert reg_res.json()["status"] == "registered"

        # 4. List devices
        dev_list_res = await client.get("/sync/devices")
        assert dev_list_res.status_code == 200
        dev_ids = [d["device_id"] for d in dev_list_res.json()]
        assert "opi-rest-test" in dev_ids

        # 5. Heartbeat
        hb_res = await client.post("/sync/devices/heartbeat", json={"device_id": "opi-rest-test"})
        assert hb_res.status_code == 200
        assert hb_res.json()["status"] == "ok"


def test_gateway_websocket_sync_channel():
    """Verifies that WebSocket Channel.SYNC messages register devices and synchronize state."""
    import json
    from starlette.testclient import TestClient
    from backend.gateway.app import create_app
    from backend.shared.events import ClientType

    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # 1. Handshake
            ws.send_text(
                json.dumps({
                    "uuid": "h-sync",
                    "channel": Channel.CONTROL.value,
                    "type": EventType.CLIENT_HELLO.value,
                    "payload": {"client_id": "opi-ws-node", "client_type": ClientType.EDGE_ORANGE_PI.value},
                })
            )
            ws.receive_text()  # SERVER_HELLO

            # 2. Register Edge Orange Pi via Channel.SYNC
            reg_uuid = "sync-reg-1"
            ws.send_text(
                json.dumps({
                    "uuid": reg_uuid,
                    "channel": Channel.SYNC.value,
                    "type": EventType.DEVICE_REGISTER.value,
                    "payload": {
                        "device_id": "opi-ws-node",
                        "device_type": "orange_pi",
                        "device_name": "Orange Pi 5 Plus Node",
                        "has_camera": False,
                        "has_display": False,
                        "is_headless": True,
                    },
                })
            )

            # 3. Receive State Snapshot
            raw_resp = ws.receive_text()
            resp = json.loads(raw_resp)
            assert resp["channel"] == Channel.SYNC.value
            assert resp["type"] == EventType.STATE_SNAPSHOT.value
            assert "master_volume" in resp["payload"]


