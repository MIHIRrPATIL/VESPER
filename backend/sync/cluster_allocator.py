"""VESPER Distributed Cluster Workload Allocator.

Implements dynamic role distribution across heterogenous devices:
  - Workstation / Laptop (High compute, large RAM, display, optical camera)
  - Mobile Companion HUD (Touchscreen, notifications, camera, portable)
  - Single-Board Computers / Orange Pi / Raspberry Pi (Low compute, microphone, speaker, edge node)

Employs the Least-Capability Assignment Principle:
  - Least capable node (e.g., Orange Pi) handles lightweight I/O:
      * Audio Capture (WebRTC VAD, Wake Word detection)
      * Audio Playback (TTS voice butler synthesis)
  - Mid-tier companion (e.g., Mobile Phone) handles:
      * HUD Display & Visual Cards
      * Notification Relay
  - High-tier node (e.g., Workstation / Laptop) handles:
      * Cognitive Swarm Reasoning (Alfred Planner & Specialists)
      * Multimodal Vision & Optical OCR
      * Vector Memory Embedding Index

CRITICAL SAFETY GATE:
  Before assigning compute-heavy roles (Cognitive Swarm & Vision Perception),
  the allocator evaluates CPU cores, current CPU load %, total RAM, and available RAM headroom
  to ensure the device will not experience thermal throttling or Linux OOM crashes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.shared.config import CLUSTER_ALLOCATION_MODE, STATIC_DEVICE_ROLES
from backend.sync.models import DeviceRegistration

logger = logging.getLogger("vesper.sync.cluster_allocator")

# Canonical Cluster Role Identifiers
ROLE_AUDIO_CAPTURE = "audio_capture"          # Microphone listener / wake word detection
ROLE_AUDIO_PLAYBACK = "audio_playback"        # TTS voice speaker output
ROLE_HUD_DISPLAY = "hud_display"              # Screen GUI, rich visual cards, lyrics
ROLE_NOTIFICATION_RELAY = "notification_relay"# Push alerts, mobile reminders
ROLE_VISION_PERCEPTION = "vision_perception"  # Optical camera inspection, VLLM, OCR
ROLE_COGNITIVE_SWARM = "cognitive_swarm"      # Alfred Stage 1 planning & specialist routing
ROLE_VECTOR_MEMORY = "vector_memory"          # Semantic vector search & embeddings

ALL_ROLES = [
    ROLE_AUDIO_CAPTURE,
    ROLE_AUDIO_PLAYBACK,
    ROLE_HUD_DISPLAY,
    ROLE_NOTIFICATION_RELAY,
    ROLE_VISION_PERCEPTION,
    ROLE_COGNITIVE_SWARM,
    ROLE_VECTOR_MEMORY,
]

# Compute Headroom Thresholds
MIN_RAM_TOTAL_GB_FOR_COMPUTE = 3.5     # At least 4GB physical RAM required
MIN_RAM_AVAILABLE_GB_FOR_COMPUTE = 1.2 # Must have >= 1.2GB free to avoid OOM
MIN_CPU_CORES_FOR_COMPUTE = 2          # At least dual core
MAX_CPU_LOAD_PCT_FOR_COMPUTE = 88.0    # Cannot be thrashing above 88% CPU load


class ClusterWorkloadAllocator:
    """Manages role assignment across connected cluster devices using least-capability distribution."""

    @classmethod
    def calculate_capability_score(cls, dev: DeviceRegistration) -> float:
        """Calculates a normalized capability score reflecting hardware strength.
        
        Lower score = lightweight edge device (Orange Pi, microcontroller).
        Higher score = powerful workstation / compute cluster node.
        """
        # Base type weighting
        type_weights = {
            "orange_pi": 2.0,
            "raspberry_pi": 3.0,
            "embedded_edge": 2.0,
            "edge_node": 2.5,
            "mobile_hud": 15.0,
            "phone": 15.0,
            "tablet": 20.0,
            "desktop": 40.0,
            "laptop": 35.0,
            "workstation": 50.0,
            "server": 60.0,
        }
        base_weight = type_weights.get(dev.device_type.lower(), 25.0)

        cores_score = dev.cpu_cores * 1.5
        ram_total_score = dev.ram_total_gb * 2.0
        # Available RAM is weighted heavily because active headroom dictates multitasking safety
        ram_avail_score = dev.ram_available_gb * 3.0

        score = base_weight + cores_score + ram_total_score + ram_avail_score
        return round(score, 2)

    @classmethod
    def verify_compute_headroom(cls, dev: DeviceRegistration) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Verifies if a node possesses sufficient CPU and RAM headroom to handle compute-heavy workloads.
        
        Returns:
            (is_safe, reasons_list, telemetry_dict)
        """
        reasons = []
        is_safe = True

        telemetry = {
            "device_id": dev.device_id,
            "device_name": dev.device_name,
            "device_type": dev.device_type,
            "cpu_cores": dev.cpu_cores,
            "cpu_usage_pct": dev.cpu_usage_pct,
            "ram_total_gb": dev.ram_total_gb,
            "ram_available_gb": dev.ram_available_gb,
        }

        # Check Total Physical RAM
        if dev.ram_total_gb < MIN_RAM_TOTAL_GB_FOR_COMPUTE:
            is_safe = False
            reasons.append(
                f"FAIL: Total RAM is {dev.ram_total_gb:.1f} GB (< {MIN_RAM_TOTAL_GB_FOR_COMPUTE:.1f} GB required for Swarm/Vision)."
            )
        else:
            reasons.append(f"PASS: Total RAM is {dev.ram_total_gb:.1f} GB (>= {MIN_RAM_TOTAL_GB_FOR_COMPUTE:.1f} GB nominal).")

        # Check Available / Free RAM Headroom
        if dev.ram_available_gb < MIN_RAM_AVAILABLE_GB_FOR_COMPUTE:
            is_safe = False
            reasons.append(
                f"FAIL: Available RAM headroom is {dev.ram_available_gb:.1f} GB (< {MIN_RAM_AVAILABLE_GB_FOR_COMPUTE:.1f} GB safe buffer, risk of OOM)."
            )
        else:
            reasons.append(f"PASS: Available RAM headroom is {dev.ram_available_gb:.1f} GB (>= {MIN_RAM_AVAILABLE_GB_FOR_COMPUTE:.1f} GB buffer).")

        # Check CPU Cores
        if dev.cpu_cores < MIN_CPU_CORES_FOR_COMPUTE:
            is_safe = False
            reasons.append(
                f"FAIL: CPU core count is {dev.cpu_cores} (< {MIN_CPU_CORES_FOR_COMPUTE} cores required)."
            )
        else:
            reasons.append(f"PASS: CPU core count is {dev.cpu_cores} cores.")

        # Check CPU Load Contention
        if dev.cpu_usage_pct > MAX_CPU_LOAD_PCT_FOR_COMPUTE:
            is_safe = False
            reasons.append(
                f"FAIL: CPU load is {dev.cpu_usage_pct:.1f}% (> {MAX_CPU_LOAD_PCT_FOR_COMPUTE:.1f}% saturation threshold, thermal throttle risk)."
            )
        else:
            reasons.append(f"PASS: CPU load is {dev.cpu_usage_pct:.1f}% (<= {MAX_CPU_LOAD_PCT_FOR_COMPUTE:.1f}% operating ceiling).")

        return is_safe, reasons, telemetry

    @classmethod
    def allocate_roles(
        cls,
        devices: Dict[str, DeviceRegistration],
    ) -> Dict[str, List[str]]:
        """Allocates cluster roles across active online devices according to least-capability allocation.
        
        Returns:
            Dict mapping device_id -> List of assigned role names.
        """
        # Filter for online devices
        online_devices = [d for d in devices.values() if d.is_online]
        if not online_devices:
            logger.warning("[ClusterAllocator] No online devices detected in cluster.")
            return {}

        # STATIC ALLOCATION MODE: Minimal-overhead explicit mapping for 1-2 device setups
        if CLUSTER_ALLOCATION_MODE == "static":
            logger.info("[ClusterAllocator] Static allocation mode active (CLUSTER_ALLOCATION_MODE=static)")
            static_map: Dict[str, List[str]] = {}
            explicit_rules: Dict[str, List[str]] = {}
            if STATIC_DEVICE_ROLES:
                for entry in STATIC_DEVICE_ROLES.split(";"):
                    if ":" in entry:
                        dev_id, roles_str = entry.split(":", 1)
                        explicit_rules[dev_id.strip()] = [r.strip() for r in roles_str.split(",") if r.strip()]

            for dev in online_devices:
                if dev.device_id in explicit_rules:
                    assigned = list(explicit_rules[dev.device_id])
                elif dev.device_type in explicit_rules:
                    assigned = list(explicit_rules[dev.device_type])
                else:
                    assigned = []
                    if dev.device_type in ("desktop", "laptop", "workstation", "server"):
                        assigned.extend([ROLE_COGNITIVE_SWARM, ROLE_VECTOR_MEMORY])
                        if dev.has_camera:
                            assigned.append(ROLE_VISION_PERCEPTION)
                        if dev.has_display:
                            assigned.extend([ROLE_HUD_DISPLAY, ROLE_NOTIFICATION_RELAY])
                        if dev.has_microphone and not any(d.device_type in ("orange_pi", "raspberry_pi", "edge_node") for d in online_devices):
                            assigned.append(ROLE_AUDIO_CAPTURE)
                        if dev.has_speaker and not any(d.device_type in ("orange_pi", "raspberry_pi", "edge_node") for d in online_devices):
                            assigned.append(ROLE_AUDIO_PLAYBACK)
                    elif dev.device_type in ("orange_pi", "raspberry_pi", "edge_node", "embedded_edge"):
                        if dev.has_microphone:
                            assigned.append(ROLE_AUDIO_CAPTURE)
                        if dev.has_speaker:
                            assigned.append(ROLE_AUDIO_PLAYBACK)
                    elif dev.device_type in ("mobile_hud", "phone", "tablet"):
                        if dev.has_display:
                            assigned.extend([ROLE_HUD_DISPLAY, ROLE_NOTIFICATION_RELAY])
                        if dev.has_camera and not any(d.device_type in ("desktop", "laptop", "workstation") for d in online_devices):
                            assigned.append(ROLE_VISION_PERCEPTION)
                    else:
                        if dev.has_microphone:
                            assigned.append(ROLE_AUDIO_CAPTURE)
                        if dev.has_speaker:
                            assigned.append(ROLE_AUDIO_PLAYBACK)
                        if dev.has_display:
                            assigned.append(ROLE_HUD_DISPLAY)

                dev.assigned_roles = assigned
                dev.resource_status = "nominal"
                static_map[dev.device_id] = assigned
                logger.info(f"[ClusterAllocator.Static] Device '{dev.device_id}' ({dev.device_type}) assigned: {assigned}")
            return static_map

        # Update capability scores and reset assigned roles
        for dev in online_devices:
            dev.capability_score = cls.calculate_capability_score(dev)
            dev.assigned_roles = []
            dev.resource_status = "nominal"

        # CASE 1: Monolithic Fallback (Single Connected Device)
        # If only one device is connected, it gracefully assumes all roles supported by its sensors
        if len(online_devices) == 1:
            solo = online_devices[0]
            assigned = []

            if solo.has_microphone:
                assigned.append(ROLE_AUDIO_CAPTURE)
            if solo.has_speaker:
                assigned.append(ROLE_AUDIO_PLAYBACK)
            if solo.has_display:
                assigned.append(ROLE_HUD_DISPLAY)
                assigned.append(ROLE_NOTIFICATION_RELAY)

            # Check compute headroom before binding heavy roles
            is_safe, reasons, _ = cls.verify_compute_headroom(solo)
            if is_safe:
                if solo.has_camera:
                    assigned.append(ROLE_VISION_PERCEPTION)
                assigned.append(ROLE_COGNITIVE_SWARM)
                assigned.append(ROLE_VECTOR_MEMORY)
                solo.resource_status = "nominal"
            else:
                solo.resource_status = "warning"
                # Even if constrained, fallback still assigns cognitive swarm with warning if it's the only device
                assigned.append(ROLE_COGNITIVE_SWARM)
                if solo.has_camera:
                    assigned.append(ROLE_VISION_PERCEPTION)
                logger.warning(
                    f"[ClusterAllocator] Solo device '{solo.device_id}' constrained ({reasons}), assigning fallback."
                )

            solo.assigned_roles = assigned
            return {solo.device_id: assigned}

        # CASE 2: Multi-Device Distributed Cluster
        # Sort devices by capability score ascending (least capable to most capable)
        sorted_devices = sorted(online_devices, key=lambda d: d.capability_score)
        allocations: Dict[str, List[str]] = {d.device_id: [] for d in sorted_devices}

        # 1. AUDIO CAPTURE -> Assigned to the LEAST capable device with microphone
        audio_capture_dev = next((d for d in sorted_devices if d.has_microphone), None)
        if audio_capture_dev:
            allocations[audio_capture_dev.device_id].append(ROLE_AUDIO_CAPTURE)
            logger.info(f"[ClusterAllocator] Audio Capture -> '{audio_capture_dev.device_id}' (Score: {audio_capture_dev.capability_score})")

        # 2. AUDIO PLAYBACK -> Assigned to the LEAST capable device with speaker
        audio_playback_dev = next((d for d in sorted_devices if d.has_speaker), None)
        if audio_playback_dev:
            allocations[audio_playback_dev.device_id].append(ROLE_AUDIO_PLAYBACK)
            logger.info(f"[ClusterAllocator] Audio Playback -> '{audio_playback_dev.device_id}' (Score: {audio_playback_dev.capability_score})")

        # 3. HUD DISPLAY & NOTIFICATIONS -> Assigned to devices with active displays (Phones, Tablets, Workstations)
        display_devices = [d for d in sorted_devices if d.has_display]
        # Prefer mobile HUD / phone if present, otherwise desktop
        for disp_dev in display_devices:
            allocations[disp_dev.device_id].append(ROLE_HUD_DISPLAY)
            allocations[disp_dev.device_id].append(ROLE_NOTIFICATION_RELAY)
            logger.info(f"[ClusterAllocator] HUD Display & Notifications -> '{disp_dev.device_id}'")

        # 4. VISION PERCEPTION -> Assigned to the MOST capable device with optical camera and verified headroom
        camera_devices = [d for d in reversed(sorted_devices) if d.has_camera]
        assigned_vision = False
        for cam_dev in camera_devices:
            is_safe, reasons, _ = cls.verify_compute_headroom(cam_dev)
            if is_safe:
                allocations[cam_dev.device_id].append(ROLE_VISION_PERCEPTION)
                assigned_vision = True
                logger.info(f"[ClusterAllocator] Vision Perception -> '{cam_dev.device_id}' (Headroom Verified)")
                break
            else:
                logger.warning(
                    f"[ClusterAllocator] Device '{cam_dev.device_id}' skipped for vision due to resource constraints: {reasons}"
                )

        if not assigned_vision and camera_devices:
            # Fallback to first camera device with warning status
            cam_dev = camera_devices[0]
            allocations[cam_dev.device_id].append(ROLE_VISION_PERCEPTION)
            cam_dev.resource_status = "warning"
            logger.warning(f"[ClusterAllocator] Vision assigned to '{cam_dev.device_id}' with resource WARNING.")

        # 5. COGNITIVE SWARM ORCHESTRATOR & VECTOR MEMORY -> Highest compute node with verified headroom
        compute_candidates = list(reversed(sorted_devices))
        assigned_swarm = False
        for node in compute_candidates:
            is_safe, reasons, _ = cls.verify_compute_headroom(node)
            if is_safe:
                allocations[node.device_id].append(ROLE_COGNITIVE_SWARM)
                allocations[node.device_id].append(ROLE_VECTOR_MEMORY)
                node.resource_status = "nominal"
                assigned_swarm = True
                logger.info(f"[ClusterAllocator] Cognitive Swarm & Memory -> '{node.device_id}' (Score: {node.capability_score}, Headroom Verified)")
                break
            else:
                node.resource_status = "warning"

        if not assigned_swarm and compute_candidates:
            # Degraded fallback to highest node
            node = compute_candidates[0]
            allocations[node.device_id].append(ROLE_COGNITIVE_SWARM)
            allocations[node.device_id].append(ROLE_VECTOR_MEMORY)
            node.resource_status = "warning"
            logger.warning(
                f"[ClusterAllocator] No node fully passed compute headroom; assigning Swarm to '{node.device_id}' in degraded mode."
            )

        # Reflect allocations onto device objects
        for dev in sorted_devices:
            dev.assigned_roles = allocations.get(dev.device_id, [])

        return allocations
