"""VESPER Cross-Device Synchronization Models.

Defines schemas for device registration, hardware topology, and universal cluster state.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DeviceRegistration(BaseModel):
    """Profile of a registered node (Desktop, Orange Pi, Mobile Companion)."""

    device_id: str
    device_type: str = "desktop"  # "desktop", "orange_pi", "raspberry_pi", "mobile_hud", "edge_node"
    device_name: str = "VESPER Node"
    hostname: str = ""
    os_name: str = "Linux"
    architecture: str = "x86_64"
    is_headless: bool = False
    has_camera: bool = False
    has_display: bool = False
    has_microphone: bool = True
    has_speaker: bool = True
    cpu_cores: int = 1
    cpu_usage_pct: float = 0.0
    ram_total_gb: float = 1.0
    ram_available_gb: float = 0.5
    capability_score: float = 1.0
    assigned_roles: List[str] = Field(default_factory=list)
    resource_status: str = "nominal"  # "nominal", "warning", "overloaded"
    ip_address: Optional[str] = None
    registered_at: float = Field(default_factory=time.time)
    last_heartbeat: float = Field(default_factory=time.time)
    is_online: bool = True


class SynchronizedState(BaseModel):
    """Canonical synchronized state across all active VESPER devices."""

    master_volume: int = 60
    zen_mode: bool = False
    focus_mode: bool = False
    optical_sensor_active: bool = False
    active_tasks_count: int = 0
    current_media: Dict[str, Any] = Field(
        default_factory=lambda: {
            "is_playing": False,
            "track_title": "",
            "artist": "",
            "progress_ms": 0,
        }
    )
    last_speech_summary: str = ""
    active_devices: Dict[str, DeviceRegistration] = Field(default_factory=dict)
    version: int = 1
    updated_at: float = Field(default_factory=time.time)

    def to_snapshot(self) -> Dict[str, Any]:
        """Returns JSON-serializable snapshot of cluster state."""
        return self.model_dump()
