"""VESPER UDP Broadcast Discovery Beacon.

Broadcasts periodic UDP packets across the local Wi-Fi subnet (port 8005)
allowing edge nodes, mobile companion apps, and desktop clients to discover
the VESPER Gateway immediately without brute-force IP scanning.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from typing import Optional

logger = logging.getLogger("vesper.gateway.beacon")


class DiscoveryBeacon:
    """Periodically broadcasts a UDP discovery beacon containing gateway coordinates."""

    _instance: Optional["DiscoveryBeacon"] = None

    def __init__(
        self,
        port: int = 8005,
        broadcast_interval: float = 2.0,
        gateway_port: int = 8000,
    ) -> None:
        self.port = port
        self.broadcast_interval = broadcast_interval
        self.gateway_port = gateway_port
        self._task: Optional[asyncio.Task] = None
        self._running = False

    @classmethod
    def get_instance(cls) -> "DiscoveryBeacon":
        if cls._instance is None:
            cls._instance = DiscoveryBeacon()
        return cls._instance

    def start(self) -> None:
        """Starts the background beacon broadcasting loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info(f"[DiscoveryBeacon] Started UDP broadcast beacon on port {self.port} (interval: {self.broadcast_interval}s)")

    async def stop(self) -> None:
        """Stops the broadcast loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[DiscoveryBeacon] Stopped UDP broadcast beacon.")

    def _get_local_ip(self) -> str:
        """Gets primary LAN IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    async def _broadcast_loop(self) -> None:
        """Asynchronous UDP broadcast loop."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)

        broadcast_dest = ("255.255.255.255", self.port)

        try:
            while self._running:
                local_ip = self._get_local_ip()
                payload = {
                    "service": "vesper-gateway",
                    "version": "2.0.0",
                    "host": local_ip,
                    "port": self.gateway_port,
                    "ws_url": f"ws://{local_ip}:{self.gateway_port}/ws",
                    "http_url": f"http://{local_ip}:{self.gateway_port}",
                    "timestamp": time.time(),
                }
                msg = json.dumps(payload).encode("utf-8")

                try:
                    sock.sendto(msg, broadcast_dest)
                except Exception as e:
                    logger.debug(f"[DiscoveryBeacon] Broadcast sendto failed: {e}")

                await asyncio.sleep(self.broadcast_interval)
        except asyncio.CancelledError:
            pass
        finally:
            sock.close()


discovery_beacon = DiscoveryBeacon.get_instance()
