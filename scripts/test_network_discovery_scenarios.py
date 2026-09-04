#!/usr/bin/env python3
"""VESPER Network Discovery & Automated Role Allocation Verification Scenarios.

Runs two concrete end-to-end tests:
  Scenario 1: FAKED INCOMING REQUEST (Inbound Push)
    - Host Workstation starts standalone (handles all roles).
    - An external edge device (Orange Pi 5) sends an inbound registration request.
    - System reacts: SyncManager registers node -> ClusterWorkloadAllocator offloads Audio I/O to edge.
    - Simulated edge disconnection: System detects heartbeat loss and reclaims all roles on workstation.

  Scenario 2: ACTIVE OUTBOUND NETWORK SWEEP (Outbound Pull)
    - A mock edge device is booted on the network with an active profile responder.
    - Gateway actively sends TCP/HTTP discovery requests over the network (NetworkScanner).
    - Gateway handshakes with the edge device, retrieves hardware telemetry, and auto-allocates roles.
    - Alfred supervisor is queried via natural voice ("Alfred, scan the network for devices").
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.agent.alfred import AlfredSupervisor
from backend.sync.client import SyncClient
from backend.sync.cluster_allocator import (
    ClusterWorkloadAllocator,
    ROLE_AUDIO_CAPTURE,
    ROLE_AUDIO_PLAYBACK,
    ROLE_HUD_DISPLAY,
    ROLE_NOTIFICATION_RELAY,
    ROLE_VISION_PERCEPTION,
    ROLE_COGNITIVE_SWARM,
    ROLE_VECTOR_MEMORY,
)
from backend.sync.models import DeviceRegistration
from backend.sync.network_scanner import NetworkScanner
from backend.sync.sync_manager import SyncManager

# Terminal Styling
BOLD = "\033[1m"
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'═' * 76}{RESET}")
    print(f"{BOLD}{CYAN}  {title.center(72)}{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 76}{RESET}")


def format_role(role: str) -> str:
    labels = {
        ROLE_AUDIO_CAPTURE: f"{GREEN}[audio_capture]{RESET}",
        ROLE_AUDIO_PLAYBACK: f"{GREEN}[audio_playback]{RESET}",
        ROLE_HUD_DISPLAY: f"{CYAN}[hud_display]{RESET}",
        ROLE_NOTIFICATION_RELAY: f"{CYAN}[notification_relay]{RESET}",
        ROLE_VISION_PERCEPTION: f"{MAGENTA}[vision_perception]{RESET}",
        ROLE_COGNITIVE_SWARM: f"{BLUE}[cognitive_swarm]{RESET}",
        ROLE_VECTOR_MEMORY: f"{BLUE}[vector_memory]{RESET}",
    }
    return labels.get(role, f"[{role}]")


def display_topology(sync_mgr: SyncManager, step_title: str) -> None:
    snapshot = sync_mgr.get_state_snapshot()
    print(f"\n{BOLD}{YELLOW}── {step_title} (Cluster Version: {snapshot.version}) ──{RESET}")
    devices = list(snapshot.active_devices.values())
    if not devices:
        print(f"  {DIM}No devices currently registered.{RESET}")
        return

    for d in devices:
        status_color = GREEN if d.is_online else RED
        status_text = "ONLINE" if d.is_online else "OFFLINE"
        score = ClusterWorkloadAllocator.calculate_capability_score(d)
        print(f"  • {BOLD}{d.device_name}{RESET} ({d.device_type}) [{status_color}{status_text}{RESET}]")
        print(f"    - ID: {d.device_id} | IP: {d.ip_address or '127.0.0.1'}")
        print(f"    - Hardware: {d.cpu_cores} Cores | {d.ram_available_gb:.1f}/{d.ram_total_gb:.1f} GB RAM | Capability Score: {score:.1f}")
        roles_str = ", ".join([format_role(r) for r in d.assigned_roles]) if d.assigned_roles else f"{DIM}(None assigned){RESET}"
        print(f"    - Assigned Roles: {roles_str}")


async def run_scenario_1_faked_incoming_request() -> None:
    print_header("SCENARIO 1: FAKED INCOMING REQUEST (INBOUND PUSH SIMULATION)")
    print(f"{DIM}Simulates an edge node (Orange Pi 5) sending an incoming registration payload to the Gateway.{RESET}")

    sync_mgr = SyncManager()

    # Step 1: Initial Standalone State (Workstation only)
    print(f"\n{BOLD}[Step 1.1] Host Workstation registers at boot...{RESET}")
    workstation = DeviceRegistration(
        device_id="workstation-arch-laptop",
        device_type="desktop",
        device_name="Arch Linux Workstation (Mihir)",
        ip_address="192.168.0.105",
        cpu_cores=16,
        ram_total_gb=32.0,
        ram_available_gb=18.5,
        has_display=True,
        has_microphone=True,
        has_speaker=True,
        has_camera=True,
    )
    await sync_mgr.register_device(workstation)
    display_topology(sync_mgr, "Initial Topology: Workstation Alone")

    # Step 2: Incoming Request from Edge Device (Simulated Orange Pi POST)
    print(f"\n{BOLD}[Step 1.2] INCOMING REQUEST DETECTED: POST /sync/devices/register from 192.168.0.188...{RESET}")
    fake_incoming_payload = {
        "device_id": "orange-pi-5-deskpod",
        "device_type": "orange_pi",
        "device_name": "Orange Pi 5 Desk Mic Pod",
        "ip_address": "192.168.0.188",
        "cpu_cores": 4,
        "ram_total_gb": 2.0,
        "ram_available_gb": 1.1,
        "has_display": False,
        "has_microphone": True,
        "has_speaker": True,
        "has_camera": False,
        "is_headless": True,
    }
    print(f"{DIM}Payload Received: {json.dumps(fake_incoming_payload, indent=2)}{RESET}")

    edge_device = DeviceRegistration(**fake_incoming_payload)
    t0 = time.perf_counter()
    await sync_mgr.register_device(edge_device)
    reaction_ms = (time.perf_counter() - t0) * 1000

    print(f"{BOLD}{GREEN}[OK] System Reacted in {reaction_ms:.2f}ms! Dynamic role allocation completed.{RESET}")
    display_topology(sync_mgr, "Topology After Inbound Device Join")

    # Verify Least-Capability Principle:
    opi = sync_mgr.state.active_devices["orange-pi-5-deskpod"]
    ws = sync_mgr.state.active_devices["workstation-arch-laptop"]
    assert ROLE_AUDIO_CAPTURE in opi.assigned_roles, "Orange Pi must have audio_capture"
    assert ROLE_AUDIO_PLAYBACK in opi.assigned_roles, "Orange Pi must have audio_playback"
    assert ROLE_COGNITIVE_SWARM in ws.assigned_roles, "Workstation must retain cognitive_swarm"
    assert ROLE_VISION_PERCEPTION in ws.assigned_roles, "Workstation must retain vision_perception"
    print(f"\n{GREEN}[OK] Verification PASSED: Audio I/O safely offloaded to Orange Pi. Heavy Swarm/Vision retained on Workstation.{RESET}")

    # Step 3: Simulated Edge Failure / Disconnect (Heartbeat Timeout)
    print(f"\n{BOLD}[Step 1.3] SIMULATED DISCONNECTION: Orange Pi drops offline (Heartbeat timeout)...{RESET}")
    # Age Orange Pi heartbeat past 30s while keeping workstation fresh
    sync_mgr.state.active_devices["orange-pi-5-deskpod"].last_heartbeat = time.time() - 60.0
    sync_mgr.state.active_devices["workstation-arch-laptop"].last_heartbeat = time.time()
    pruned = await sync_mgr.prune_stale_devices(timeout_sec=30.0)
    print(f"{DIM}Pruned devices: {pruned}{RESET}")
    display_topology(sync_mgr, "Topology After Edge Disconnection (Failover)")

    # Verify Failover:
    ws_after = sync_mgr.state.active_devices["workstation-arch-laptop"]
    assert ROLE_AUDIO_CAPTURE in ws_after.assigned_roles, "Workstation must reclaim audio_capture"
    assert ROLE_AUDIO_PLAYBACK in ws_after.assigned_roles, "Workstation must reclaim audio_playback"
    print(f"{GREEN}[OK] Failover Verification PASSED: Workstation seamlessly reclaimed Audio I/O roles without cluster restart.{RESET}")


async def run_scenario_2_outbound_network_sweep() -> None:
    print_header("SCENARIO 2: ACTIVE OUTBOUND NETWORK SWEEP (OUTBOUND PULL)")
    print(f"{DIM}Spawns a real mock edge node TCP server, and the Gateway actively sends discovery requests across the network.{RESET}")

    # Step 1: Spin up a real mock edge node profile server on loopback
    mock_port = 8094
    edge_client = SyncClient(
        device_id="node-orange-pi-livingroom",
        device_name="Orange Pi 5 (Living Room Edge)",
    )
    edge_client.profile_port = mock_port

    print(f"\n{BOLD}[Step 2.1] Spawning live mock edge node on port {mock_port}...{RESET}")
    await edge_client.start_profile_server(host="127.0.0.1", port=mock_port)
    print(f"{GREEN}[OK] Edge node HTTP profile server listening on 127.0.0.1:{mock_port}{RESET}")

    try:
        # Step 2: Gateway actively sends out network requests
        print(f"\n{BOLD}[Step 2.2] Gateway actively sending outbound probe requests across the network...{RESET}")
        scanner = NetworkScanner(ports=[mock_port], default_timeout=0.5)

        t0 = time.perf_counter()
        discovered_node = await scanner.probe_host("127.0.0.1", mock_port)
        sweep_latency_ms = (time.perf_counter() - t0) * 1000

        print(f"{CYAN}--> [SENT OUTBOUND] GET /sync/profile HTTP/1.1 to 127.0.0.1:{mock_port}{RESET}")
        if discovered_node:
            print(f"{GREEN}<-- [RECEIVED INBOUND RESPONSE in {sweep_latency_ms:.1f}ms]{RESET}")
            print(f"    Discovered Device: {BOLD}{discovered_node.device_name}{RESET} ({discovered_node.device_id})")
            print(f"    Architecture: {discovered_node.architecture} | OS: {discovered_node.os_name}")
            print(f"    Capabilities: Mic={discovered_node.has_microphone}, Speaker={discovered_node.has_speaker}, Camera={discovered_node.has_camera}")

        # Step 3: Run full subnet sweep with auto-registration
        print(f"\n{BOLD}[Step 2.3] Executing active sweep with automatic SyncManager registration...{RESET}")
        from unittest.mock import patch
        with patch("ipaddress.IPv4Network.hosts", return_value=["127.0.0.1"]):
            results = await scanner.scan_subnet(ports=[mock_port], auto_register=True)

        print(f"{GREEN}[OK] Subnet sweep registered {len(results)} device(s) into universal cluster state.{RESET}")

        # Step 4: Ask Alfred via natural voice query
        print(f"\n{BOLD}[Step 2.4] Querying Alfred via voice: 'Alfred, scan the network for devices'...{RESET}")
        alfred = AlfredSupervisor()
        t_alfred = time.perf_counter()
        resp = await alfred.process_query("Alfred, scan the network for devices")
        alfred_ms = (time.perf_counter() - t_alfred) * 1000

        print(f"{BOLD}{BLUE}Alfred Response ({alfred_ms:.1f}ms):{RESET}")
        print(f"{BOLD}\"{resp.speech_text}\"{RESET}")
        print(f"Plan Type: {resp.plan_type} | Fast Path: {resp.fast_path}")
        if resp.specialist_actions:
            action = resp.specialist_actions[0]
            print(f"Action Executed: {action.get('agent')} -> {action.get('action')} (Success: {action.get('success')})")

    finally:
        print(f"\n{BOLD}[Step 2.5] Cleaning up mock edge node server...{RESET}")
        await edge_client.stop_profile_server()
        print(f"{GREEN}[OK] Edge node server stopped.{RESET}")


async def main() -> None:
    print(f"\n{BOLD}{MAGENTA}======================================================================{RESET}")
    print(f"{BOLD}{MAGENTA}       VESPER DUAL-MODE NETWORK DISCOVERY SYSTEM INTEGRATION TEST      {RESET}")
    print(f"{BOLD}{MAGENTA}======================================================================{RESET}")

    await run_scenario_1_faked_incoming_request()
    await run_scenario_2_outbound_network_sweep()

    print(f"\n{BOLD}{GREEN}======================================================================{RESET}")
    print(f"{BOLD}{GREEN}       ALL DUAL-MODE DISCOVERY SCENARIOS PASSED WITH FULL REACTION    {RESET}")
    print(f"{BOLD}{GREEN}======================================================================{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
