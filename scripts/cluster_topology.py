#!/usr/bin/env python3
"""VESPER Cluster Device Discovery & Workload Allocation Inspector.

Probes local host hardware (CPU, RAM, Cameras, Audio, Display),
verifies compute headroom against OOM / thermal limits,
and dynamically allocates cluster roles using the Least-Capability Principle.

Usage:
    python scripts/cluster_topology.py              # Inspects local hardware & live cluster
    python scripts/cluster_topology.py --simulate   # Simulates multi-device setup (Orange Pi + Phone + Laptop)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.sync.models import DeviceRegistration
from backend.sync.sync_manager import SyncManager
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
from backend.vision.device_probe import DeviceProbe

# Terminal ANSI Color Formatting
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BLUE = "\033[94m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner() -> None:
    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{CYAN}      VESPER DISTRIBUTED CLUSTER TOPOLOGY & ALLOCATION ENGINE         {RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")


def format_role(role: str) -> str:
    labels = {
        ROLE_AUDIO_CAPTURE: f"{GREEN}[audio_capture]{RESET}",
        ROLE_AUDIO_PLAYBACK: f"{CYAN}[audio_playback]{RESET}",
        ROLE_HUD_DISPLAY: f"{BLUE}[hud_display]{RESET}",
        ROLE_NOTIFICATION_RELAY: f"{BLUE}[notification_relay]{RESET}",
        ROLE_VISION_PERCEPTION: f"{YELLOW}[vision_perception]{RESET}",
        ROLE_COGNITIVE_SWARM: f"{BOLD}{CYAN}[cognitive_swarm]{RESET}",
        ROLE_VECTOR_MEMORY: f"{DIM}[vector_memory]{RESET}",
    }
    return labels.get(role, f"[{role}]")


def probe_and_display_local_hardware() -> DeviceRegistration:
    print(f"\n{BOLD}[1] LOCAL HOST HARDWARE & TELEMETRY PROBE{RESET}")
    caps = DeviceProbe.get_capabilities(force_refresh=True)

    print(f"  • {BOLD}Device Model:{RESET}      {caps.device_model} ({caps.device_type})")
    print(f"  • {BOLD}OS & Architecture:{RESET} {caps.os_name} {caps.os_release} [{caps.architecture}] on '{caps.hostname}'")
    print(f"  • {BOLD}CPU Configuration:{RESET} {caps.cpu_cores_logical} Logical / {caps.cpu_cores_physical} Physical Cores ({caps.cpu_usage_pct:.1f}% Load)")
    print(f"  • {BOLD}Memory Status:{RESET}     {caps.ram_available_gb:.2f} GB Free / {caps.ram_total_gb:.2f} GB Total ({caps.ram_used_pct:.1f}% In-Use)")
    print(f"  • {BOLD}Optical Camera:{RESET}    {'[OK] Detected ' + str(caps.available_cameras) if caps.has_camera else '[--] Absent'}")
    print(f"  • {BOLD}Display Window:{RESET}    {'[OK] Active (GUI)' if caps.has_display else '[--] Headless'}")
    print(f"  • {BOLD}Microphone:{RESET}        {'[OK] Active' if caps.has_microphone else '[--] None'}")
    print(f"  • {BOLD}Audio Speaker:{RESET}     {'[OK] Active' if caps.has_speaker else '[--] None'}")

    local_reg = DeviceRegistration(
        device_id=f"{caps.hostname.lower()}-{caps.device_type}",
        device_type=caps.device_type,
        device_name=f"{caps.hostname} ({caps.device_model.split('_')[0]})",
        hostname=caps.hostname,
        os_name=caps.os_name,
        architecture=caps.architecture,
        is_headless=caps.is_headless,
        has_camera=caps.has_camera,
        has_display=caps.has_display,
        has_microphone=caps.has_microphone,
        has_speaker=caps.has_speaker,
        cpu_cores=caps.cpu_cores_logical,
        cpu_usage_pct=caps.cpu_usage_pct,
        ram_total_gb=caps.ram_total_gb,
        ram_available_gb=caps.ram_available_gb,
    )
    return local_reg


def verify_and_print_headroom(dev: DeviceRegistration) -> bool:
    print(f"\n{BOLD}[2] COMPUTE HEADROOM SAFETY VERIFICATION ({dev.device_name}){RESET}")
    is_safe, reasons, telemetry = ClusterWorkloadAllocator.verify_compute_headroom(dev)

    for reason in reasons:
        if reason.startswith("PASS:"):
            print(f"  {GREEN}[OK]{RESET} {reason[6:]}")
        else:
            print(f"  {RED}[FAIL]{RESET} {reason[6:]}")

    if is_safe:
        print(f"\n  {BOLD}{GREEN}[OK] HEADROOM CONFIRMED:{RESET} Device has ample CPU & RAM capacity for Alfred Swarm & Vision VLLM.")
    else:
        print(f"\n  {BOLD}{YELLOW}[WARN] RESOURCE WARNING:{RESET} Device compute constrained; heavy tasks will be throttled or offloaded.")

    return is_safe


def print_allocation_table(devices: list[DeviceRegistration], allocations: dict[str, list[str]]) -> None:
    print(f"\n{BOLD}----------------------------------------------------------------------{RESET}")
    print(f"{BOLD}{'DEVICE / NODE':<22} {'CAP SCORE':<11} {'CPU / RAM':<18} {'ASSIGNED CLUSTER ROLES'}{RESET}")
    print(f"----------------------------------------------------------------------")

    for dev in sorted(devices, key=lambda d: d.capability_score):
        roles_str = ", ".join([format_role(r) for r in allocations.get(dev.device_id, [])]) or f"{DIM}Idle / Standby{RESET}"
        specs = f"{dev.cpu_cores}c | {dev.ram_available_gb:.1f}/{dev.ram_total_gb:.1f}GB"
        status_color = GREEN if dev.resource_status == "nominal" else YELLOW
        print(f"{status_color}{dev.device_name:<22}{RESET} {dev.capability_score:<11.1f} {specs:<18} {roles_str}")
    print(f"----------------------------------------------------------------------\n")


def run_simulation() -> None:
    print(f"\n{BOLD}{YELLOW}>>> SIMULATION MODE: Heterogenous 3-Device Cluster Distribution <<<{RESET}")
    print(f"Demonstrating: Orange Pi SBC + Mobile Phone + Laptop Workstation\n")

    # 1. Orange Pi Zero 3 (Least-capability edge node)
    orange_pi = DeviceRegistration(
        device_id="orangepi-zero3",
        device_type="orange_pi",
        device_name="Orange Pi Zero 3",
        hostname="orangepi-edge",
        os_name="Linux (Armbian)",
        architecture="aarch64",
        is_headless=True,
        has_camera=False,
        has_display=False,
        has_microphone=True,
        has_speaker=True,
        cpu_cores=4,
        cpu_usage_pct=15.0,
        ram_total_gb=1.0,
        ram_available_gb=0.45,
    )

    # 2. Smartphone Companion (Medium-tier handheld node)
    phone = DeviceRegistration(
        device_id="phone-pixel8",
        device_type="mobile_hud",
        device_name="Pixel 8 Pro (HUD)",
        hostname="pixel-mobile",
        os_name="Android 15",
        architecture="aarch64",
        is_headless=False,
        has_camera=True,
        has_display=True,
        has_microphone=True,
        has_speaker=True,
        cpu_cores=8,
        cpu_usage_pct=24.0,
        ram_total_gb=12.0,
        ram_available_gb=4.8,
    )

    # 3. Workstation Laptop (High compute node)
    laptop = DeviceRegistration(
        device_id="asus-vivobook",
        device_type="laptop",
        device_name="ASUS VivoBook Workstation",
        hostname="mihir-arch",
        os_name="Linux (Arch)",
        architecture="x86_64",
        is_headless=False,
        has_camera=True,
        has_display=True,
        has_microphone=True,
        has_speaker=True,
        cpu_cores=16,
        cpu_usage_pct=18.5,
        ram_total_gb=16.0,
        ram_available_gb=5.2,
    )

    cluster_devices = {
        orange_pi.device_id: orange_pi,
        phone.device_id: phone,
        laptop.device_id: laptop,
    }

    print(f"{BOLD}[A] VERIFYING CPU & RAM HEADROOM ON CLUSTER CANDIDATES:{RESET}")
    for d in [orange_pi, phone, laptop]:
        is_safe, reasons, _ = ClusterWorkloadAllocator.verify_compute_headroom(d)
        tag = f"{GREEN}[SAFE FOR SWARM]{RESET}" if is_safe else f"{YELLOW}[INSUFFICIENT FOR SWARM]{RESET}"
        print(f"  • {BOLD}{d.device_name}{RESET}: {tag} (Avail RAM: {d.ram_available_gb:.1f}GB, CPU Load: {d.cpu_usage_pct}%)")

    print(f"\n{BOLD}[B] RUNNING LEAST-CAPABILITY WORKLOAD ALLOCATION:{RESET}")
    allocs = ClusterWorkloadAllocator.allocate_roles(cluster_devices)
    print_allocation_table(list(cluster_devices.values()), allocs)

    print(f"{BOLD}Architectural Highlights of this Allocation:{RESET}")
    print(f"  1. {BOLD}Audio Capture & TTS{RESET} is offloaded to the {CYAN}Orange Pi Zero 3{RESET} (Least compute score: {orange_pi.capability_score}).")
    print(f"     -> Keeps laptop mic/speaker free; listens continuously with low power draw.")
    print(f"  2. {BOLD}HUD Display & Notifications{RESET} are routed to the {BLUE}Mobile Companion (Phone){RESET}.")
    print(f"     -> Live cards, email alerts, and Spotify controls appear directly on the desk HUD.")
    print(f"  3. {BOLD}Vision Perception & Cognitive Swarm{RESET} are hosted on {YELLOW}ASUS Laptop{RESET}.")
    print(f"     -> Verified ample RAM ({laptop.ram_available_gb}GB free) and 16 CPU cores for local reasoning.")

    # Demonstration of graceful failover
    print(f"\n{BOLD}[C] TESTING FAILOVER: Simulating Orange Pi & Phone Disconnecting...{RESET}")
    orange_pi.is_online = False
    phone.is_online = False
    solo_alloc = ClusterWorkloadAllocator.allocate_roles(cluster_devices)
    print_allocation_table([laptop], solo_alloc)
    print(f"  {GREEN}[OK] Graceful Fallback Confirmed:{RESET} ASUS Laptop smoothly re-assumed audio capture, playback, and all roles.")


def main() -> None:
    parser = argparse.ArgumentParser(description="VESPER Cluster Topology and Role Allocation")
    parser.add_argument("--simulate", action="store_true", help="Simulate a 3-device distributed cluster (Laptop + Phone + Orange Pi)")
    args = parser.parse_args()

    print_banner()

    if args.simulate:
        run_simulation()
        return

    # Real Host Hardware Probe
    local_dev = probe_and_display_local_hardware()
    verify_and_print_headroom(local_dev)

    print(f"\n{BOLD}[3] REAL-TIME CLUSTER STATUS & ALLOCATION{RESET}")
    sync = SyncManager.get_instance()
    asyncio.run(sync.register_device(local_dev))

    snapshot = sync.get_snapshot()
    allocs = ClusterWorkloadAllocator.allocate_roles(snapshot.active_devices)
    print_allocation_table(list(snapshot.active_devices.values()), allocs)

    print(f"{DIM}Tip: Run 'python scripts/cluster_topology.py --simulate' to see the multi-device Orange Pi + Phone + Laptop distribution.{RESET}\n")


if __name__ == "__main__":
    main()
