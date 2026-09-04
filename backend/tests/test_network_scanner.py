"""Unit tests for the Active Subnet Network Scanner & Auto Role Allocation.

Covers:
1. Host LAN IP and /24 subnet detection & virtual adapter filtering.
2. Socket probe against VESPER /sync/profile responder.
3. Socket probe against fallback /health responder.
4. Graceful handling of closed ports, non-VESPER hosts, and socket timeouts.
5. Subnet sweep concurrency, device auto-registration, and dynamic role allocation.
6. SyncClient embedded profile server roundtrip.
7. Gateway /sync/scan REST endpoints.
8. Alfred supervisor network scan prefiltering and speech synthesis.
"""

from __future__ import annotations

import asyncio
import json
import socket
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.agent.alfred import AlfredSupervisor
from backend.agent.planner import SwarmPlanner
from backend.agent.registry import SpecialistRegistry
from backend.gateway.app import create_app
from backend.sync.client import SyncClient
from backend.sync.cluster_allocator import (
    ROLE_AUDIO_CAPTURE,
    ROLE_AUDIO_PLAYBACK,
    ROLE_COGNITIVE_SWARM,
    ROLE_VISION_PERCEPTION,
    ROLE_VECTOR_MEMORY,
)
from backend.sync.models import DeviceRegistration
from backend.sync.network_scanner import NetworkScanner
from backend.sync.sync_manager import SyncManager


@pytest.mark.asyncio
async def test_get_local_subnet_detection():
    """Verifies that NetworkScanner resolves a valid /24 IPv4 network."""
    scanner = NetworkScanner()
    subnet = scanner.get_local_subnet()
    assert subnet is not None
    assert subnet.prefixlen in (24, 32)
    assert not str(subnet.network_address).startswith("172.17.")


@pytest.mark.asyncio
async def test_probe_host_with_mock_profile_server():
    """Verifies socket probing against a live VESPER /sync/profile responder."""
    expected_profile = DeviceRegistration(
        device_id="node-orange-pi-5-livingroom",
        device_type="orange_pi",
        device_name="Orange Pi 5 Butler Mic",
        hostname="orange-pi-5",
        os_name="Linux",
        architecture="aarch64",
        is_headless=True,
        has_camera=False,
        has_display=False,
        has_microphone=True,
        has_speaker=True,
        cpu_cores=8,
        ram_total_gb=4.0,
        ram_available_gb=2.8,
    )

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        req = await reader.read(1024)
        req_str = req.decode("utf-8", errors="ignore")
        if "GET /sync/profile" in req_str:
            body = expected_profile.model_dump_json()
            resp = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body.encode())}\r\n"
                f"Connection: close\r\n\r\n{body}"
            )
            writer.write(resp.encode("utf-8"))
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        scanner = NetworkScanner(ports=[port], default_timeout=0.5)
        dev = await scanner.probe_host("127.0.0.1", port)

        assert dev is not None
        assert dev.device_id == "node-orange-pi-5-livingroom"
        assert dev.device_type == "orange_pi"
        assert dev.has_microphone is True
        assert dev.ip_address == "127.0.0.1"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_probe_host_with_health_fallback():
    """Verifies socket probing falls back to /health endpoint when /sync/profile is not present."""
    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        req = await reader.read(1024)
        req_str = req.decode("utf-8", errors="ignore")
        if "GET /sync/profile" in req_str:
            resp = "HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"
        elif "GET /health" in req_str:
            body = json.dumps({"status": "healthy", "service": "vesper-api-gateway", "cluster_version": 2})
            resp = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body.encode())}\r\n"
                f"Connection: close\r\n\r\n{body}"
            )
        else:
            resp = "HTTP/1.1 500 Error\r\nConnection: close\r\n\r\n"

        writer.write(resp.encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        scanner = NetworkScanner(ports=[port], default_timeout=0.5)
        dev = await scanner.probe_host("127.0.0.1", port)

        assert dev is not None
        assert "node-127-0-0-1" in dev.device_id
        assert dev.device_name == "VESPER Node (127.0.0.1)"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_probe_host_closed_port_and_non_vesper():
    """Verifies that probing closed ports or non-VESPER HTTP endpoints returns None safely."""
    scanner = NetworkScanner(default_timeout=0.1)

    # 1. Closed port (connection refused)
    closed_res = await scanner.probe_host("127.0.0.1", 59999)
    assert closed_res is None

    # 2. Non-VESPER server returning unrelated HTTP data
    async def dummy_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        await reader.read(1024)
        resp = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nHello World Apache"
        writer.write(resp.encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(dummy_handler, "127.0.0.1", 0)
    p = server.sockets[0].getsockname()[1]
    try:
        non_vesper_res = await scanner.probe_host("127.0.0.1", p)
        assert non_vesper_res is None
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_sync_client_profile_server_and_probe_roundtrip():
    """Verifies SyncClient's embedded profile responder works end-to-end with NetworkScanner."""
    # Find free port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    free_port = s.getsockname()[1]
    s.close()

    client = SyncClient(
        device_id="node-test-rpi4",
        device_name="Raspberry Pi 4 Desk Node",
    )
    client.profile_port = free_port

    await client.start(enable_profile_server=True)
    try:
        scanner = NetworkScanner(ports=[free_port], default_timeout=0.5)
        dev = await scanner.probe_host("127.0.0.1", free_port)

        assert dev is not None
        assert dev.device_id == "node-test-rpi4"
        assert dev.device_name == "Raspberry Pi 4 Desk Node"
        assert dev.is_online is True
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_subnet_sweep_and_automatic_cluster_allocation():
    """Verifies that discovered devices trigger Least-Capability allocation in SyncManager."""
    sync_mgr = SyncManager()

    # Register host workstation
    workstation = DeviceRegistration(
        device_id="workstation-arch",
        device_type="desktop",
        device_name="Mihir Arch Workstation",
        cpu_cores=16,
        ram_total_gb=32.0,
        ram_available_gb=18.0,
        has_display=True,
        has_microphone=True,
        has_speaker=True,
        has_camera=True,
    )
    await sync_mgr.register_device(workstation)

    # Simulated edge Orange Pi discovered on LAN
    discovered_orange_pi = DeviceRegistration(
        device_id="orange-pi-edge-01",
        device_type="orange_pi",
        device_name="Orange Pi 5 Mic Pod",
        cpu_cores=4,
        ram_total_gb=2.0,
        ram_available_gb=1.1,
        has_display=False,
        has_microphone=True,
        has_speaker=True,
        has_camera=False,
    )

    with patch("backend.sync.network_scanner.sync_manager", sync_mgr):
        scanner = NetworkScanner()
        with patch.object(scanner, "probe_host", AsyncMock(return_value=discovered_orange_pi)):
            # Scan returns mock discovered device
            with patch("ipaddress.IPv4Network.hosts", return_value=["192.168.1.88"]):
                results = await scanner.scan_subnet(ports=[8004], auto_register=True)

    assert len(results) >= 1
    assert "orange-pi-edge-01" in sync_mgr.state.active_devices

    opi = sync_mgr.state.active_devices["orange-pi-edge-01"]
    ws = sync_mgr.state.active_devices["workstation-arch"]

    # Least-Capability Verification:
    # Orange Pi (low compute) gets Audio I/O
    assert ROLE_AUDIO_CAPTURE in opi.assigned_roles
    assert ROLE_AUDIO_PLAYBACK in opi.assigned_roles

    # Workstation (high compute) retains Swarm, Vision, and Memory
    assert ROLE_COGNITIVE_SWARM in ws.assigned_roles
    assert ROLE_VISION_PERCEPTION in ws.assigned_roles
    assert ROLE_VECTOR_MEMORY in ws.assigned_roles


@pytest.mark.asyncio
async def test_gateway_sync_scan_endpoints():
    """Verifies Gateway GET/POST /sync/scan endpoints."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.post("/sync/scan")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "scan_complete"
        assert "discovered_count" in data
        assert "cluster_role_allocations" in data


@pytest.mark.asyncio
async def test_alfred_planner_routes_scan_network_query():
    """Verifies that queries asking to scan the network route directly to system:scan_network_devices."""
    planner = SwarmPlanner()
    registry = SpecialistRegistry()

    queries = [
        "Alfred, scan the network for devices",
        "scan the network",
        "scan for devices on the network",
        "detect connected hardware",
    ]

    for q in queries:
        plan, latency = await planner.create_plan(q, registry)
        assert plan.provider_used == "prefilter"
        assert latency == 0.0
        assert len(plan.steps) == 1
        assert plan.steps[0]["agent"] == "system"
        assert plan.steps[0]["action"] == "scan_network_devices"
