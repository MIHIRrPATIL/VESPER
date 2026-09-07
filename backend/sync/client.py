"""VESPER Edge Sync Client.

Runs on edge hardware (Orange Pi, Raspberry Pi, Desk HUD, or companion laptop).
- Automatically probes local sensors & hardware capabilities.
- Registers device presence with the central Gateway / Sync Hub.
- Emits periodic heartbeats.
- Receives state sync broadcasts (Volume, Zen Mode, Focus Mode) and executes local hardware hooks.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import time
import uuid
from typing import Callable, Dict, Optional

from backend.sync.models import DeviceRegistration, SynchronizedState
from backend.vision.device_probe import DeviceProbe
from backend.shared.events import Channel, ClientEnvelope, EventType, ServerEnvelope

logger = logging.getLogger("vesper.sync.client")


class SyncClient:
    """Lightweight sync client that runs on an edge node (e.g., Orange Pi)."""

    def __init__(
        self,
        device_id: Optional[str] = None,
        device_name: Optional[str] = None,
        gateway_ws_url: Optional[str] = None,
        heartbeat_interval_sec: float = 10.0,
    ) -> None:
        self.device_id = device_id or f"node-{platform.node()}-{uuid.uuid4().hex[:6]}"
        self.device_name = device_name or f"VESPER Node ({platform.node()})"
        self.gateway_ws_url = gateway_ws_url
        self.heartbeat_interval = heartbeat_interval_sec

        self.is_running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._server: Optional[asyncio.Server] = None
        self.profile_port: int = 8004
        self.latest_state: Optional[SynchronizedState] = None
        self.on_state_change: Optional[Callable[[SynchronizedState], None]] = None

    def get_registration_profile(self) -> DeviceRegistration:
        """Probes local host hardware and constructs a comprehensive device profile."""
        caps = DeviceProbe.get_capabilities()
        return DeviceRegistration(
            device_id=self.device_id,
            device_type=caps.device_type,
            device_name=self.device_name,
            hostname=caps.hostname,
            os_name=caps.os_name,
            architecture=caps.architecture,
            is_headless=caps.is_headless,
            has_camera=caps.has_camera,
            has_display=caps.has_display,
            has_microphone=caps.has_microphone,
            cpu_cores=caps.cpu_cores_logical,
            cpu_usage_pct=caps.cpu_usage_pct,
            ram_total_gb=caps.ram_total_gb,
            ram_available_gb=caps.ram_available_gb,
            registered_at=time.time(),
            last_heartbeat=time.time(),
            is_online=True,
        )

    async def _handle_profile_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Lightweight HTTP handler for subnet discovery probes."""
        import json
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            req_line = line.decode("utf-8", errors="ignore")
            # Consume remaining HTTP headers
            while True:
                h_line = await asyncio.wait_for(reader.readline(), timeout=1.0)
                if not h_line or h_line in (b"\r\n", b"\n"):
                    break

            if "GET /sync/profile" in req_line:
                body = self.get_registration_profile().model_dump_json()
                resp = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body.encode())}\r\n"
                    f"Connection: close\r\n\r\n{body}"
                )
            elif "GET /health" in req_line:
                body = json.dumps({"status": "healthy", "service": "vesper-edge-sync", "device_id": self.device_id})
                resp = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body.encode())}\r\n"
                    f"Connection: close\r\n\r\n{body}"
                )
            else:
                resp = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

            writer.write(resp.encode("utf-8"))
            await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start_profile_server(self, host: str = "0.0.0.0", port: int = 8004) -> None:
        """Starts a zero-overhead TCP responder so the central Gateway subnet scanner can discover this node."""
        self.profile_port = port
        try:
            self._server = await asyncio.start_server(self._handle_profile_request, host, port)
            logger.info(f"[SyncClient] Profile responder listening on {host}:{port}")
        except Exception as e:
            logger.warning(f"[SyncClient] Could not bind profile server to port {port} ({e})")

    async def stop_profile_server(self) -> None:
        """Closes the profile responder server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def start(self, enable_profile_server: bool = True) -> None:
        """Starts client heartbeat, synchronization loop, and discovery profile responder."""
        if self.is_running:
            return

        self.is_running = True
        logger.info(f"[SyncClient] Starting sync client for device '{self.device_id}'...")
        if enable_profile_server:
            await self.start_profile_server(port=self.profile_port)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stops client heartbeat loop and profile server."""
        self.is_running = False
        await self.stop_profile_server()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        logger.info(f"[SyncClient] Stopped sync client for device '{self.device_id}'.")

    async def _heartbeat_loop(self) -> None:
        """Periodically pulses heartbeats to the central sync hub."""
        from backend.sync.sync_manager import sync_manager

        # Initial registration with local/central manager
        profile = self.get_registration_profile()
        await sync_manager.register_device(profile)

        while self.is_running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await sync_manager.record_heartbeat(self.device_id)
                logger.debug(f"[SyncClient] Heartbeat sent for '{self.device_id}'.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[SyncClient] Heartbeat pulse error: {e}")

    def apply_remote_state(self, state: SynchronizedState) -> None:
        """Applies received cluster state to local node."""
        self.latest_state = state
        logger.info(
            f"[SyncClient] Applied cluster state v{state.version}: "
            f"Volume={state.master_volume}%, Zen={state.zen_mode}"
        )
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception as e:
                logger.error(f"[SyncClient] Error in on_state_change handler: {e}")
