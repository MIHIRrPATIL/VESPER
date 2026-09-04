"""Unit Tests for VESPER Cluster Workload Allocator & Headroom Verification."""

import pytest
from backend.sync.models import DeviceRegistration
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


@pytest.fixture
def sample_devices():
    orange_pi = DeviceRegistration(
        device_id="orange-pi-1",
        device_type="orange_pi",
        device_name="Orange Pi Zero 3",
        cpu_cores=4,
        cpu_usage_pct=10.0,
        ram_total_gb=1.0,
        ram_available_gb=0.4,
        has_microphone=True,
        has_speaker=True,
        has_display=False,
        has_camera=False,
    )
    phone = DeviceRegistration(
        device_id="phone-hud",
        device_type="mobile_hud",
        device_name="Pixel Phone HUD",
        cpu_cores=8,
        cpu_usage_pct=20.0,
        ram_total_gb=8.0,
        ram_available_gb=3.5,
        has_microphone=True,
        has_speaker=True,
        has_display=True,
        has_camera=True,
    )
    laptop = DeviceRegistration(
        device_id="workstation-laptop",
        device_type="laptop",
        device_name="ASUS Laptop",
        cpu_cores=16,
        cpu_usage_pct=15.0,
        ram_total_gb=16.0,
        ram_available_gb=5.0,
        has_microphone=True,
        has_speaker=True,
        has_display=True,
        has_camera=True,
    )
    return {"orange_pi": orange_pi, "phone": phone, "laptop": laptop}


def test_calculate_capability_score(sample_devices):
    opi_score = ClusterWorkloadAllocator.calculate_capability_score(sample_devices["orange_pi"])
    phone_score = ClusterWorkloadAllocator.calculate_capability_score(sample_devices["phone"])
    laptop_score = ClusterWorkloadAllocator.calculate_capability_score(sample_devices["laptop"])

    assert opi_score < phone_score < laptop_score
    assert opi_score < 25.0
    assert laptop_score > 80.0


def test_verify_compute_headroom_passing(sample_devices):
    laptop = sample_devices["laptop"]
    is_safe, reasons, telemetry = ClusterWorkloadAllocator.verify_compute_headroom(laptop)

    assert is_safe is True
    assert any("PASS: Total RAM" in r for r in reasons)
    assert any("PASS: Available RAM headroom" in r for r in reasons)
    assert telemetry["cpu_cores"] == 16


def test_verify_compute_headroom_failing_low_ram(sample_devices):
    opi = sample_devices["orange_pi"]
    is_safe, reasons, _ = ClusterWorkloadAllocator.verify_compute_headroom(opi)

    assert is_safe is False
    assert any("FAIL: Total RAM" in r for r in reasons)
    assert any("FAIL: Available RAM headroom" in r for r in reasons)


def test_verify_compute_headroom_failing_high_cpu():
    overloaded = DeviceRegistration(
        device_id="hot-laptop",
        device_type="laptop",
        cpu_cores=16,
        cpu_usage_pct=95.5,
        ram_total_gb=16.0,
        ram_available_gb=4.0,
    )
    is_safe, reasons, _ = ClusterWorkloadAllocator.verify_compute_headroom(overloaded)
    assert is_safe is False
    assert any("FAIL: CPU load" in r for r in reasons)


def test_allocate_roles_single_device(sample_devices):
    laptop = sample_devices["laptop"]
    allocs = ClusterWorkloadAllocator.allocate_roles({laptop.device_id: laptop})

    roles = allocs[laptop.device_id]
    assert ROLE_AUDIO_CAPTURE in roles
    assert ROLE_AUDIO_PLAYBACK in roles
    assert ROLE_HUD_DISPLAY in roles
    assert ROLE_VISION_PERCEPTION in roles
    assert ROLE_COGNITIVE_SWARM in roles
    assert ROLE_VECTOR_MEMORY in roles


def test_least_capability_distribution(sample_devices):
    devices = {d.device_id: d for d in sample_devices.values()}
    allocs = ClusterWorkloadAllocator.allocate_roles(devices)

    opi_roles = allocs["orange-pi-1"]
    phone_roles = allocs["phone-hud"]
    laptop_roles = allocs["workstation-laptop"]

    # 1. Orange Pi (least capable with mic/speaker) assumes audio capture & playback
    assert ROLE_AUDIO_CAPTURE in opi_roles
    assert ROLE_AUDIO_PLAYBACK in opi_roles

    # 2. Phone assumes HUD display and notifications
    assert ROLE_HUD_DISPLAY in phone_roles
    assert ROLE_NOTIFICATION_RELAY in phone_roles

    # 3. Laptop (highest capable with headroom) assumes cognitive swarm & vision
    assert ROLE_COGNITIVE_SWARM in laptop_roles
    assert ROLE_VISION_PERCEPTION in laptop_roles
    assert ROLE_VECTOR_MEMORY in laptop_roles
