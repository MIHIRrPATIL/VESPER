"""VESPER Gateway Unified Multiplexed WebSocket Endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.gateway.connection_manager import ClientSession, ConnectionManager
from backend.gateway.router import MessageRouter
from backend.gateway.task_registry import TaskRegistry
from backend.shared.config import HANDSHAKE_TIMEOUT_SECONDS
from backend.shared.events import (
    Channel,
    ClientEnvelope,
    ClientHelloPayload,
    ClientType,
    EventType,
    ServerEnvelope,
    ServerHelloPayload,
)

logger = logging.getLogger("vesper.gateway.ws")
router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Unified full-duplex WebSocket endpoint multiplexing all channels."""
    await websocket.accept()

    manager: ConnectionManager = websocket.app.state.connection_manager
    tasks: TaskRegistry = websocket.app.state.task_registry
    msg_router: MessageRouter = websocket.app.state.router

    session: ClientSession | None = None

    try:
        # ── 1. Handshake Phase (Enforce CLIENT_HELLO within timeout) ────────
        try:
            raw_hello = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=HANDSHAKE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("[GATEWAY] Handshake timed out: No CLIENT_HELLO received within 5s.")
            await websocket.close(code=4008, reason="Handshake timeout")
            return

        try:
            hello_data = json.loads(raw_hello)
            hello_envelope = ClientEnvelope.model_validate(hello_data)
        except Exception as e:
            logger.warning(f"[GATEWAY] Invalid handshake JSON: {e}")
            await websocket.close(code=4003, reason="Malformed CLIENT_HELLO payload")
            return

        if hello_envelope.type != EventType.CLIENT_HELLO:
            logger.warning(f"[GATEWAY] First frame was not CLIENT_HELLO: '{hello_envelope.type}'")
            await websocket.close(code=4003, reason="Expected CLIENT_HELLO first frame")
            return

        # Parse client details
        try:
            hello_payload = ClientHelloPayload.model_validate(hello_envelope.payload)
        except Exception as e:
            logger.warning(f"[GATEWAY] Invalid CLIENT_HELLO payload details: {e}")
            await websocket.close(code=4003, reason=f"Invalid CLIENT_HELLO details: {e}")
            return

        # Register Session
        session = manager.register(websocket, hello_payload)

        # Emit SERVER_HELLO Acknowledgement
        server_hello = ServerEnvelope(
            uuid=hello_envelope.uuid,
            channel=Channel.CONTROL,
            type=EventType.SERVER_HELLO,
            payload=ServerHelloPayload(
                session_id=session.session_id,
                heartbeat_interval_ms=15000,
                server_version="2.0.0",
            ).model_dump(),
        )
        await manager.send_envelope(session.session_id, server_hello)

        # Trigger proactive executive startup briefing for interactive HUD & Desktop companions
        if "startup_briefing" in session.capabilities or session.client_id in ("vesper-desktop-terminal", "vesper-desktop-companion"):
            from backend.agent.proactive_agent import proactive_agent
            asyncio.create_task(proactive_agent.deliver_startup_briefing(session_id=session.session_id))

        # ── 2. Message Loop Phase ──────────────────────────────────────────
        while True:
            raw_msg = await websocket.receive_text()

            try:
                msg_data = json.loads(raw_msg)
                envelope = ClientEnvelope.model_validate(msg_data)
            except Exception as e:
                logger.warning(f"[GATEWAY] Malformed envelope from '{session.client_id}': {e}")
                err_envelope = ServerEnvelope(
                    channel=Channel.CONTROL,
                    type=EventType.ERROR,
                    status="error",
                    payload={"message": f"Malformed envelope: {str(e)}"},
                )
                await manager.send_envelope(session.session_id, err_envelope)
                continue

            # Route valid envelope
            await msg_router.route(session, envelope)

    except WebSocketDisconnect:
        logger.info(f"[GATEWAY] Client disconnected normally: {session.client_id if session else 'unregistered'}")
    except Exception as e:
        logger.error(f"[GATEWAY] Unexpected socket error: {e}", exc_info=True)
    finally:
        # Cleanup
        if session:
            tasks.cancel_session(session.session_id)
            await manager.unregister(session.session_id)
