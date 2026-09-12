"""Tests for VESPER Distributed Workstation Command RPC via WebSocket Envelopes."""

import asyncio
import json
import pytest
from starlette.testclient import TestClient

from backend.gateway.app import create_app
from backend.gateway.router import MessageRouter
from backend.gateway.connection_manager import ConnectionManager, ClientSession
from backend.shared.events import (
    Channel,
    ClientEnvelope,
    ClientHelloPayload,
    ClientType,
    EventType,
    ServerEnvelope,
)


def test_workstation_command_no_client():
    """Verify that workstation command fails gracefully if no DESK_HUD client is connected."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/workstation/command",
            json={"command": "dpms", "params": {"state": "off"}, "timeout": 0.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "No workstation" in data["error"]


def test_workstation_command_websocket_forwarding():
    """Verify that WORKSTATION_COMMAND_REQ is forwarded to connected DESK_HUD client."""
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # 1. Register DESK_HUD
            ws.send_json({
                "uuid": "desk-hello",
                "channel": Channel.CONTROL,
                "type": EventType.CLIENT_HELLO,
                "payload": {
                    "client_id": "arch-hud-01",
                    "client_type": ClientType.DESK_HUD,
                    "roles": ["ROLE_HUD_DISPLAY"],
                },
            })
            _ = ws.receive_json()

            # 2. Emit WORKSTATION_COMMAND_REQ
            req_uuid = "workstation-dpms-test-01"
            ws.send_json({
                "uuid": req_uuid,
                "channel": Channel.CONTROL,
                "type": EventType.WORKSTATION_COMMAND_REQ,
                "payload": {
                    "request_uuid": req_uuid,
                    "command": "dpms",
                    "params": {"state": "off"},
                },
            })

            # 3. DESK_HUD receives WORKSTATION_COMMAND_REQ
            msg = ws.receive_json()
            assert msg["type"] == EventType.WORKSTATION_COMMAND_REQ
            assert msg["payload"]["command"] == "dpms"
            assert msg["payload"]["params"]["state"] == "off"


@pytest.mark.asyncio
async def test_router_execute_workstation_command_roundtrip():
    """Verify execute_workstation_command future resolution when WORKSTATION_COMMAND_RES arrives."""
    from backend.gateway.task_registry import TaskRegistry
    manager = ConnectionManager()
    router = MessageRouter(connection_manager=manager, task_registry=TaskRegistry())

    class DummyWS:
        def __init__(self):
            self.sent_messages = []
        async def send_text(self, text: str):
            self.sent_messages.append(text)

    dummy_ws = DummyWS()
    session = ClientSession(
        websocket=dummy_ws,
        session_id="test-session-01",
        client_id="arch-hud-01",
        client_type=ClientType.DESK_HUD,
        capabilities=["workstation"],
    )
    manager._sessions[session.session_id] = session

    async def _simulate_desktop_reply(req_uuid: str):
        await asyncio.sleep(0.05)
        res_env = ClientEnvelope(
            uuid=req_uuid,
            channel=Channel.CONTROL,
            type=EventType.WORKSTATION_COMMAND_RES,
            payload={
                "request_uuid": req_uuid,
                "command": "dpms",
                "success": True,
                "state": "off",
            },
        )
        await router._handle_workstation_command_res(session, res_env)

    # Spawn workstation dispatcher
    async def _run_command():
        # Schedule response after command starts
        # Find UUID when sent
        task = asyncio.create_task(router.execute_workstation_command("dpms", {"state": "off"}, timeout=2.0))
        await asyncio.sleep(0.02)
        assert len(dummy_ws.sent_messages) == 1
        sent_env = json.loads(dummy_ws.sent_messages[0])
        req_uuid = sent_env["uuid"]
        await _simulate_desktop_reply(req_uuid)
        return await task

    result = await _run_command()
    assert result.get("success") is True
    assert result.get("state") == "off"
