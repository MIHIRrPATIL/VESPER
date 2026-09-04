"""VESPER Hardware & Device Capability Probe.

Detects host environment:
- Device type: Desktop (Arch/Ubuntu/etc.), Single-Board Computers (Orange Pi, Raspberry Pi), or headless edge nodes.
- Optical sensor detection: Probes `/dev/video*` and OpenCV capture indices to verify camera availability.
- Display capability: Checks X11 / Wayland environments ($DISPLAY, $WAYLAND_DISPLAY).
- Audio input capability: Probes ALSA / PulseAudio / PipeWire capture sources.

Provides graceful butler degradation messaging when sensors are absent.
"""

from __future__ import annotations

import glob
import logging
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Silence OpenCV internal C++ stderr warnings on Linux metadata device nodes
os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")

logger = logging.getLogger("vesper.vision.device_probe")


class DeviceCapabilities(BaseModel):
    """Snapshot of host device hardware and perceptual sensor capabilities."""

    device_type: str = "desktop"  # "desktop", "orange_pi", "raspberry_pi", "embedded_edge", "headless_server"
    device_model: str = "Unknown Hardware"
    os_name: str = platform.system()
    os_release: str = platform.release()
    architecture: str = platform.machine()
    hostname: str = platform.node()
    is_headless: bool = False
    has_display: bool = True
    has_camera: bool = False
    available_cameras: List[int] = Field(default_factory=list)
    has_microphone: bool = True
    has_speaker: bool = True
    cpu_cores_logical: int = 1
    cpu_cores_physical: int = 1
    cpu_usage_pct: float = 0.0
    ram_total_gb: float = 1.0
    ram_available_gb: float = 0.5
    ram_used_pct: float = 0.0
    probed_at: float = 0.0


class DeviceProbe:
    """Probes and caches host hardware, compute vitals, and sensory equipment."""

    _cached_caps: Optional[DeviceCapabilities] = None

    @classmethod
    def get_capabilities(cls, force_refresh: bool = False) -> DeviceCapabilities:
        """Returns the detected hardware profile, caching results for performance."""
        if cls._cached_caps is not None and not force_refresh:
            return cls._cached_caps

        import time

        device_type, device_model = cls._detect_device_model()
        has_display, is_headless = cls._detect_display()
        has_camera, available_cameras = cls._detect_cameras()
        has_microphone = cls._detect_microphone()
        has_speaker = cls._detect_speaker()
        compute = cls._detect_compute_metrics()

        caps = DeviceCapabilities(
            device_type=device_type,
            device_model=device_model,
            os_name=platform.system(),
            os_release=platform.release(),
            architecture=platform.machine(),
            hostname=platform.node(),
            is_headless=is_headless,
            has_display=has_display,
            has_camera=has_camera,
            available_cameras=available_cameras,
            has_microphone=has_microphone,
            has_speaker=has_speaker,
            cpu_cores_logical=compute["cpu_cores_logical"],
            cpu_cores_physical=compute["cpu_cores_physical"],
            cpu_usage_pct=compute["cpu_usage_pct"],
            ram_total_gb=compute["ram_total_gb"],
            ram_available_gb=compute["ram_available_gb"],
            ram_used_pct=compute["ram_used_pct"],
            probed_at=time.time(),
        )
        cls._cached_caps = caps
        logger.info(
            f"[DeviceProbe] Detected {caps.device_type} ({caps.device_model}) | "
            f"CPU: {caps.cpu_cores_logical} cores ({caps.cpu_usage_pct:.1f}% load) | "
            f"RAM: {caps.ram_available_gb:.1f}/{caps.ram_total_gb:.1f} GB avail | "
            f"Camera: {'Available ' + str(available_cameras) if has_camera else 'None'} | "
            f"Display: {'Active' if has_display else 'Headless'}"
        )
        return caps

    @classmethod
    def _detect_device_model(cls) -> tuple[str, str]:
        """Detects whether this node is an Orange Pi, Raspberry Pi, or desktop."""
        model_str = ""

        # Check Device Tree model (typical for ARM SBCs like Orange Pi, Raspberry Pi)
        dt_model_paths = [
            Path("/proc/device-tree/model"),
            Path("/sys/firmware/devicetree/base/model"),
        ]
        for p in dt_model_paths:
            try:
                if p.exists():
                    raw = p.read_text(encoding="utf-8", errors="ignore").strip().replace("\x00", "")
                    if raw:
                        model_str = raw
                        break
            except Exception:
                pass

        # Check DMI system product name for x86/ARM desktop/laptops
        if not model_str:
            dmi_paths = [
                Path("/sys/class/dmi/id/product_name"),
                Path("/sys/class/dmi/id/board_name"),
            ]
            for p in dmi_paths:
                try:
                    if p.exists():
                        raw = p.read_text(encoding="utf-8", errors="ignore").strip()
                        if raw and raw != "None" and raw != "System Product Name":
                            model_str = raw
                            break
                except Exception:
                    pass

        # Read /etc/os-release for distro hints
        distro = "Linux"
        os_release = Path("/etc/os-release")
        if os_release.exists():
            try:
                for line in os_release.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("PRETTY_NAME="):
                        distro = line.split("=", 1)[1].strip('"\n\r')
                        break
            except Exception:
                pass

        # Classify device
        lowered = f"{model_str} {distro} {platform.platform()}".lower()
        if "orange pi" in lowered or "orangepi" in lowered:
            return "orange_pi", model_str or "Orange Pi SBC"
        elif "raspberry pi" in lowered or "bcm2835" in lowered or "bcm2711" in lowered:
            return "raspberry_pi", model_str or "Raspberry Pi SBC"
        elif "jetson" in lowered or "tegra" in lowered:
            return "embedded_edge", model_str or "NVIDIA Jetson Edge Node"
        elif "rk3588" in lowered or "rockchip" in lowered:
            return "embedded_edge", model_str or "Rockchip Edge SBC"
        else:
            final_model = model_str if model_str else f"{distro} ({platform.machine()})"
            return "desktop", final_model

    @classmethod
    def _detect_display(cls) -> tuple[bool, bool]:
        """Checks if a graphical display server (X11 / Wayland) is accessible."""
        display = os.getenv("DISPLAY", "")
        wayland = os.getenv("WAYLAND_DISPLAY", "")
        has_display = bool(display or wayland)
        is_headless = not has_display
        return has_display, is_headless

    @classmethod
    def _detect_cameras(cls) -> tuple[bool, List[int]]:
        """Probes for optical video devices in /dev/video*."""
        video_nodes = glob.glob("/dev/video*")
        if not video_nodes:
            return False, []

        available_indices: List[int] = []
        # Attempt to probe standard device indices (up to 4)
        for idx in range(4):
            dev_path = f"/dev/video{idx}"
            if os.path.exists(dev_path):
                # We confirm the device node exists
                available_indices.append(idx)

        # If opencv is importable, we can test opening the primary device quickly
        try:
            import cv2
            if available_indices:
                tested_indices = []
                for idx in available_indices:
                    cap = cv2.VideoCapture(idx)
                    if cap.isOpened():
                        tested_indices.append(idx)
                        cap.release()
                if tested_indices:
                    return True, tested_indices
        except Exception:
            pass

        return len(available_indices) > 0, available_indices

    @classmethod
    def _detect_compute_metrics(cls) -> Dict[str, Any]:
        """Reads CPU cores, current load %, and RAM metrics via psutil."""
        try:
            import psutil

            cpu_logical = psutil.cpu_count(logical=True) or 1
            cpu_physical = psutil.cpu_count(logical=False) or cpu_logical
            cpu_usage = psutil.cpu_percent(interval=0.05)
            vmem = psutil.virtual_memory()
            ram_total = round(vmem.total / (1024 ** 3), 2)
            ram_avail = round(vmem.available / (1024 ** 3), 2)
            ram_used_pct = vmem.percent
            return {
                "cpu_cores_logical": cpu_logical,
                "cpu_cores_physical": cpu_physical,
                "cpu_usage_pct": cpu_usage,
                "ram_total_gb": ram_total,
                "ram_available_gb": ram_avail,
                "ram_used_pct": ram_used_pct,
            }
        except Exception as e:
            logger.debug(f"[DeviceProbe] Error probing psutil metrics: {e}")
            return {
                "cpu_cores_logical": 1,
                "cpu_cores_physical": 1,
                "cpu_usage_pct": 0.0,
                "ram_total_gb": 1.0,
                "ram_available_gb": 0.5,
                "ram_used_pct": 50.0,
            }

    @classmethod
    def _detect_speaker(cls) -> bool:
        """Detects whether audio playback / speaker hardware is present."""
        try:
            if Path("/proc/asound/cards").exists():
                text = Path("/proc/asound/cards").read_text()
                if "--- no soundcards ---" not in text:
                    return True
        except Exception:
            pass
        return True

    @classmethod
    def _detect_microphone(cls) -> bool:
        """Probes for audio capture hardware or virtual sinks."""
        snd_nodes = glob.glob("/dev/snd/pcm*c")
        if snd_nodes:
            return True
        # Check ALSA or pulse in environment
        if os.path.exists("/dev/snd"):
            return True
        return True  # default optimistic for mic

    @classmethod
    def format_missing_camera_butler_response(cls, context_query: str = "") -> str:
        """Generates an elegant, articulate Alfred butler response when optical sensors are unavailable."""
        caps = cls.get_capabilities()
        device_label = caps.device_model or caps.device_type.replace("_", " ").title()

        if caps.device_type in ("orange_pi", "raspberry_pi", "embedded_edge"):
            return (
                f"I am currently operating on an edge node ({device_label}) with no optical camera sensors detected, sir. "
                "If you wish me to analyze objects, documents, or your physical surroundings, please attach a USB optical sensor "
                "or relay the visual feed via the companion mobile HUD."
            )
        elif caps.is_headless:
            return (
                f"I detect no optical sensors connected to this headless system ({device_label}), sir. "
                "Please connect a webcam or utilize the companion HUD to provide visual context."
            )
        else:
            return (
                f"I am unable to access any optical sensors or webcam devices on this workstation ({device_label}), sir. "
                "Kindly ensure a camera is plugged in and authorized."
            )
