"""VESPER Gateway Connection Manager.

Manages persistent WebSocket sessions, targeted multicasting,
and the periodic heartbeat liveness supervisor.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from backend.shared.config import (
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_TIMEOUT_SECONDS,
)
from backend.shared.events import (
    Channel,
    ClientHelloPayload,
    ClientType,
    EventType,
    PingPayload,
    ServerEnvelope,
    ServerHelloPayload,
)

logger = logging.getLogger("vesper.gateway.connection")


@dataclass
class ClientSession:
    """Represents an active, authenticated client session."""
    websocket: WebSocket
    session_id: str
    client_id: str
    client_type: ClientType
    capabilities: list[str] = field(default_factory=list)
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    authenticated: bool = False
    pending_ping: bool = False


class ConnectionManager:
    """Manages all active WebSocket connections and their lifecycle."""

    def __init__(self) -> None:
        self._sessions: dict[str, ClientSession] = {}
        self._supervisor_task: Optional[asyncio.Task] = None
        self._running: bool = False

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def register(
        self,
        websocket: WebSocket,
        hello_payload: ClientHelloPayload,
    ) -> ClientSession:
        """Registers a newly authenticated client session."""
        session_id = f"sess_{uuid.uuid4().hex[:8]}_{hello_payload.client_id}"
        session = ClientSession(
            websocket=websocket,
            session_id=session_id,
            client_id=hello_payload.client_id,
            client_type=hello_payload.client_type,
            capabilities=hello_payload.capabilities,
            connected_at=time.time(),
            last_heartbeat=time.time(),
            authenticated=True,
        )
        self._sessions[session_id] = session
        logger.info(
            f"[GATEWAY] Registered client '{session.client_id}' "
            f"(type={session.client_type.value}, session={session_id})"
        )
        return session

    async def unregister(self, session_id: str) -> Optional[ClientSession]:
        """Removes a client session and cleans up resources."""
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info(f"[GATEWAY] Unregistered session '{session_id}' (client={session.client_id})")
            try:
                await session.websocket.close()
            except Exception:
                pass
        return session

    def record_pong(self, session_id: str) -> bool:
        """Records a successful PONG response from a client."""
        session = self._sessions.get(session_id)
        if session:
            session.last_heartbeat = time.time()
            session.pending_ping = False
            return True
        return False

    async def send_envelope(self, session_id: str, envelope: ServerEnvelope) -> bool:
        """Sends a structured ServerEnvelope to a specific client session."""
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[GATEWAY] Cannot send to unknown session '{session_id}'")
            return False

        try:
            raw_text = envelope.model_dump_json()
            await session.websocket.send_text(raw_text)
            return True
        except (WebSocketDisconnect, RuntimeError, Exception) as err:
            logger.warning(f"[GATEWAY] Failed to send envelope to '{session_id}': {err}")
            await self.unregister(session_id)
            return False

    async def broadcast(
        self,
        envelope: ServerEnvelope,
        target_client_types: Optional[list[ClientType]] = None,
    ) -> int:
        """Broadcasts an envelope to all or filtered client types. Returns count of recipients."""
        target_sessions = [
            s for s in self._sessions.values()
            if target_client_types is None or s.client_type in target_client_types
        ]

        if not target_sessions:
            return 0

        raw_text = envelope.model_dump_json()
        deliveries = []

        async def _safe_send(sess: ClientSession):
            try:
                await sess.websocket.send_text(raw_text)
                return True
            except Exception as err:
                logger.warning(f"[GATEWAY] Broadcast failed for '{sess.session_id}': {err}")
                await self.unregister(sess.session_id)
                return False

        results = await asyncio.gather(*[_safe_send(s) for s in target_sessions])
        return sum(1 for r in results if r)

    def start_heartbeat_supervisor(self) -> None:
        """Starts the background loop that monitors connection liveness."""
        if self._supervisor_task is None or self._supervisor_task.done():
            self._running = True
            self._supervisor_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("[GATEWAY] Heartbeat supervisor started.")

    async def stop_heartbeat_supervisor(self) -> None:
        """Stops the heartbeat supervisor gracefully."""
        self._running = False
        if self._supervisor_task:
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass
            self._supervisor_task = None
            logger.info("[GATEWAY] Heartbeat supervisor stopped.")

    async def _heartbeat_loop(self) -> None:
        """Periodically sends PING frames and evicts stale connections."""
        while self._running:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                now = time.time()
                stale_sessions: list[str] = []

                for session_id, session in list(self._sessions.items()):
                    # If a ping was already sent and no pong arrived within timeout
                    time_since_last = now - session.last_heartbeat
                    if session.pending_ping and (time_since_last > (HEARTBEAT_INTERVAL_SECONDS + HEARTBEAT_TIMEOUT_SECONDS)):
                        logger.warning(
                            f"[GATEWAY] Evicting dead client '{session.client_id}' "
                            f"(no pong for {time_since_last:.1f}s)"
                        )
                        stale_sessions.append(session_id)
                        continue

                    # Send Ping
                    session.pending_ping = True
                    ping_envelope = ServerEnvelope(
                        channel=Channel.CONTROL,
                        type=EventType.PING,
                        payload=PingPayload(server_time=now).model_dump(),
                    )
                    await self.send_envelope(session_id, ping_envelope)

                for sid in stale_sessions:
                    await self.unregister(sid)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[GATEWAY] Unexpected error in heartbeat loop: {e}", exc_info=True)

    def get_sessions_info(self) -> list[dict]:
        """Returns sanitized metadata for all currently connected clients."""
        now = time.time()
        return [
            {
                "session_id": s.session_id,
                "client_id": s.client_id,
                "client_type": s.client_type.value,
                "capabilities": s.capabilities,
                "uptime_seconds": round(now - s.connected_at, 1),
                "last_heartbeat_seconds_ago": round(now - s.last_heartbeat, 1),
            }
            for s in self._sessions.values()
        ]
