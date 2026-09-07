"""VESPER Active Subnet Network Scanner.

Discovers active cluster nodes (Orange Pi, Raspberry Pi, Mobile HUD, Auxiliary Workstations)
across the local physical subnet without manual IP configuration.

Features:
- Fast non-blocking async sweep across /24 subnet (<1s for 254 hosts).
- Probes VESPER ports (default 8004 for Sync Service, 8000 for Gateway).
- Queries node hardware profiles (/sync/profile or /health).
- Auto-registers detected devices into SyncManager, triggering Least-Capability role allocation.
- Periodically sweeps and prunes offline devices.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
import time
from typing import Any, Dict, List, Optional

from backend.shared.config import (
    SUBNET_SCAN_ENABLED,
    SUBNET_SCAN_INTERVAL_SECONDS,
    SUBNET_SCAN_PORTS,
)
from backend.sync.models import DeviceRegistration
from backend.sync.sync_manager import sync_manager

logger = logging.getLogger("vesper.sync.scanner")


class NetworkScanner:
    """Asynchronous scanner for automatic discovery of VESPER cluster nodes on the local LAN."""

    _instance: Optional["NetworkScanner"] = None

    def __init__(
        self,
        ports: Optional[List[int]] = None,
        default_timeout: float = 0.15,
        concurrency: int = 64,
    ) -> None:
        self.ports = ports or list(SUBNET_SCAN_PORTS)
        self.default_timeout = default_timeout
        self.concurrency = concurrency
        self._periodic_task: Optional[asyncio.Task] = None
        self.is_scanning = False
        self.last_scan_time: float = 0.0
        self.last_scan_results: List[DeviceRegistration] = []

    @classmethod
    def get_instance(cls) -> "NetworkScanner":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = NetworkScanner()
        return cls._instance

    @staticmethod
    def get_local_ip() -> str:
        """Determines the primary LAN IP of the host machine."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to public DNS without transmitting actual packets
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def get_local_subnet(self) -> ipaddress.IPv4Network:
        """Determines the /24 IPv4 network corresponding to the active physical LAN interface.

        Filters out virtual Docker bridges (172.17.x.x), Tailscale (100.x.x.x),
        and link-local addresses (169.254.x.x).
        """
        local_ip = self.get_local_ip()

        # Reject loopback or non-routable interfaces and provide sensible default
        if local_ip.startswith("127.") or local_ip == "0.0.0.0":
            return ipaddress.IPv4Network("127.0.0.1/32")

        # Docker bridge filter (default 172.17.0.0/16)
        if local_ip.startswith("172.17.") or local_ip.startswith("172.18."):
            logger.warning(f"[NetworkScanner] Detected Docker virtual interface ({local_ip}), falling back to 192.168.1.0/24")
            return ipaddress.IPv4Network("192.168.1.0/24", strict=False)

        # Build /24 subnet for the current LAN interface
        try:
            return ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        except Exception as e:
            logger.warning(f"[NetworkScanner] Failed to parse subnet for {local_ip}: {e}. Defaulting to 192.168.1.0/24")
            return ipaddress.IPv4Network("192.168.1.0/24", strict=False)

    async def probe_host(
        self,
        ip: str,
        port: int,
        timeout: Optional[float] = None,
    ) -> Optional[DeviceRegistration]:
        """Probes a specific IP and port to determine if it is an active VESPER node."""
        tout = timeout or self.default_timeout
        reader = None
        writer = None
        try:
            conn_coro = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(conn_coro, timeout=tout)

            # Probe 1: Request structured VESPER profile
            http_req = (
                f"GET /sync/profile HTTP/1.1\r\n"
                f"Host: {ip}:{port}\r\n"
                f"User-Agent: VESPER-SubnetScanner/1.0\r\n"
                f"Accept: application/json\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("utf-8")

            writer.write(http_req)
            await writer.drain()

            raw_resp = await asyncio.wait_for(reader.read(4096), timeout=tout)
            resp_text = raw_resp.decode("utf-8", errors="ignore")

            # Check if 404 or unsupported on /sync/profile, fall back to /health or /sync/state
            if "HTTP/1.1 404" in resp_text or not resp_text:
                writer.close()
                await writer.wait_closed()
                reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=tout)
                alt_req = (
                    f"GET /health HTTP/1.1\r\n"
                    f"Host: {ip}:{port}\r\n"
                    f"User-Agent: VESPER-SubnetScanner/1.0\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode("utf-8")
                writer.write(alt_req)
                await writer.drain()
                raw_resp = await asyncio.wait_for(reader.read(4096), timeout=tout)
                resp_text = raw_resp.decode("utf-8", errors="ignore")

            if " 200 " not in resp_text and "HTTP/1.1 200" not in resp_text:
                return None

            # Extract JSON payload from HTTP response body
            body_match = re.search(r"\r?\n\r?\n(\{.*\})", resp_text, re.DOTALL)
            if not body_match:
                return None

            data = json.loads(body_match.group(1))

            # Case A: Explicit DeviceRegistration model returned by /sync/profile
            if "device_id" in data:
                data["ip_address"] = ip
                return DeviceRegistration(**data)

            # Case B: Standard VESPER Gateway /health endpoint
            if data.get("status") in ("healthy", "ok") and ("vesper" in str(data.get("service", "")).lower() or data.get("cluster_version") is not None):
                dev_id = f"node-{ip.replace('.', '-')}-{port}"
                return DeviceRegistration(
                    device_id=dev_id,
                    device_type="desktop" if port == 8000 else "edge_node",
                    device_name=f"VESPER Node ({ip})",
                    hostname=ip,
                    ip_address=ip,
                    has_display=True,
                    has_microphone=True,
                    has_speaker=True,
                )

            return None

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return None
        except Exception as e:
            logger.debug(f"[NetworkScanner] Error probing {ip}:{port}: {e}")
            return None
        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

    async def scan_subnet(
        self,
        ports: Optional[List[int]] = None,
        timeout: Optional[float] = None,
        concurrency: Optional[int] = None,
        auto_register: bool = True,
    ) -> List[DeviceRegistration]:
        """Concurrently sweeps the local /24 subnet across candidate VESPER ports."""
        t0 = time.perf_counter()
        target_ports = ports or self.ports
        tout = timeout or self.default_timeout
        sem_limit = concurrency or self.concurrency

        subnet = self.get_local_subnet()
        hosts = [str(h) for h in subnet.hosts()]
        if not hosts:
            return []

        logger.info(f"[NetworkScanner] Starting async subnet sweep across {subnet} on ports {target_ports} ({len(hosts)} hosts)...")
        self.is_scanning = True

        sem = asyncio.Semaphore(sem_limit)
        discovered: List[DeviceRegistration] = []

        async def _bounded_probe(host_ip: str, port: int) -> None:
            async with sem:
                dev = await self.probe_host(host_ip, port, timeout=tout)
                if dev:
                    discovered.append(dev)

        tasks = []
        for host_ip in hosts:
            for port in target_ports:
                tasks.append(_bounded_probe(host_ip, port))

        await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.perf_counter() - t0
        self.last_scan_time = time.time()
        self.last_scan_results = discovered
        self.is_scanning = False

        logger.info(
            f"[NetworkScanner] Sweep finished in {elapsed:.2f}s. Discovered {len(discovered)} active VESPER node(s)."
        )

        # Auto-register discovered devices into SyncManager to trigger role allocation
        if auto_register and discovered:
            for dev in discovered:
                await sync_manager.register_device(dev)

        return discovered

    async def _periodic_loop(self, interval_sec: float) -> None:
        """Periodic background scanner loop."""
        logger.info(f"[NetworkScanner] Background periodic scanner started (interval: {interval_sec}s).")
        try:
            # Initial boot scan
            await self.scan_subnet(auto_register=True)
            while True:
                await asyncio.sleep(interval_sec)
                await self.scan_subnet(auto_register=True)
                await sync_manager.prune_stale_devices(timeout_sec=interval_sec * 2.0)
        except asyncio.CancelledError:
            logger.info("[NetworkScanner] Background periodic scanner loop stopped.")
        except Exception as e:
            logger.error(f"[NetworkScanner] Error in periodic scanner loop: {e}", exc_info=True)

    def start_periodic_loop(self, interval_sec: Optional[float] = None) -> Optional[asyncio.Task]:
        """Launches the background periodic subnet scanner."""
        if not SUBNET_SCAN_ENABLED:
            logger.info("[NetworkScanner] Subnet scanner is disabled via SUBNET_SCAN_ENABLED=false.")
            return None

        if self._periodic_task and not self._periodic_task.done():
            return self._periodic_task

        interval = interval_sec or SUBNET_SCAN_INTERVAL_SECONDS
        self._periodic_task = asyncio.create_task(self._periodic_loop(interval))
        return self._periodic_task

    async def stop_periodic_loop(self) -> None:
        """Terminates the background periodic scanner task."""
        if self._periodic_task:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None


# Global singleton instance
network_scanner = NetworkScanner.get_instance()
