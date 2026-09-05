"""VESPER Frame Capture & Vision Pipeline Utility.

Captures optical frames from:
1. Primary Webcam (/dev/video0 or OpenCV index 0): The PRIMARY sensor for OCR, objects, and VLLM questions.
2. Screen Display (Desktop Monitor / Active Window): The SECONDARY sensor when the user explicitly queries their monitor.

Provides base64 JPEG encoding and dimension metadata.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

# Silence OpenCV internal C++ stderr warnings on Linux metadata device nodes
os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")

from backend.vision.device_probe import DeviceProbe

logger = logging.getLogger("vesper.vision.camera_stream")


def get_shared_frame_path() -> Path:
    """Returns the optimal cross-platform shared camera frame path (RAM disk /dev/shm on Linux, tempdir on Windows/macOS)."""
    shm = Path("/dev/shm")
    if shm.exists() and os.access(str(shm), os.W_OK):
        return shm / "vesper_webcam_latest.jpg"
    return Path(tempfile.gettempdir()) / "vesper_webcam_latest.jpg"


class FrameCaptureResult(BaseModel):
    """Encapsulates a captured visual frame."""

    success: bool = True
    source: str = "webcam"  # "webcam" | "screen"
    image_base64: str = ""
    width: int = 0
    height: int = 0
    timestamp: float = Field(default_factory=time.time)
    error: Optional[str] = None
    monitor_index: Optional[int] = None
    monitor_name: Optional[str] = None


class CameraCapture:
    """Handles optical webcam frame acquisition with hardware fault tolerance."""

    @staticmethod
    def capture_frame(camera_index: int = 0, timeout_sec: float = 2.0) -> FrameCaptureResult:
        """Captures a single optical frame from the specified webcam index."""
        caps = DeviceProbe.get_capabilities()
        if not caps.has_camera:
            return FrameCaptureResult(
                success=False,
                source="webcam",
                error=DeviceProbe.format_missing_camera_butler_response(),
            )

        # 1. Non-blocking read from shared RAM disk (written by live GestureWorker or CameraHub)
        shared_p = get_shared_frame_path()
        try:
            if shared_p.exists():
                mtime = shared_p.stat().st_mtime
                if (time.time() - mtime) < 2.5:
                    raw_bytes = shared_p.read_bytes()
                    if len(raw_bytes) > 1000:
                        b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                        w, h = 640, 480
                        try:
                            import cv2
                            import numpy as np
                            nparr = np.frombuffer(raw_bytes, np.uint8)
                            img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
                            if img is not None:
                                h, w = img.shape[:2]
                        except Exception:
                            pass
                        return FrameCaptureResult(
                            success=True,
                            source="webcam_shared",
                            image_base64=b64_str,
                            width=w,
                            height=h,
                            timestamp=mtime,
                        )
        except Exception:
            pass

        # 2. Non-blocking snapshot from Gateway CameraHub
        try:
            from backend.shared.config import GATEWAY_PORT
            import httpx
            gw_url = f"http://127.0.0.1:{GATEWAY_PORT}/api/camera/snapshot?index={camera_index}"
            with httpx.Client(timeout=1.5) as client:
                res = client.get(gw_url)
                if res.status_code == 200 and len(res.content) > 1000:
                    b64_str = base64.b64encode(res.content).decode("utf-8")
                    return FrameCaptureResult(
                        success=True,
                        image_base64=b64_str,
                        source="webcam_gateway",
                        width=640,
                        height=480,
                    )
        except Exception:
            pass

        try:
            import cv2
        except ImportError:
            logger.warning("[CameraCapture] OpenCV not installed in current runtime.")
            return FrameCaptureResult(
                success=False,
                source="webcam",
                error="OpenCV runtime library is not available on this host.",
            )

        cap = None
        used_idx = camera_index
        try:
            # Try specified camera_index or fallback through available indices
            indices_to_try = [camera_index] + [i for i in caps.available_cameras if i != camera_index]
            frame = None

            for idx in indices_to_try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    logger.info(f"[PRIVACY.CAMERA] Optical sensor ACTIVE (hardware index={idx}) - Acquiring visual frame")
                    try:
                        from backend.sync.sync_manager import sync_manager
                        sync_manager.state.optical_sensor_active = True
                    except Exception:
                        pass
                    # Set standard 720p or default resolution
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None:
                        frame = test_frame
                        used_idx = idx
                        break
                    cap.release()
                    cap = None

            if frame is None:
                return FrameCaptureResult(
                    success=False,
                    source="webcam",
                    error="Unable to read an optical frame from the webcam sensor.",
                )

            # Encode frame to JPEG
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, 85]
            success, encoded_img = cv2.imencode(".jpg", frame, encode_param)

            if not success:
                return FrameCaptureResult(
                    success=False,
                    source="webcam",
                    error="Failed to encode webcam frame to JPEG.",
                )

            img_bytes = encoded_img.tobytes()
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            h, w = frame.shape[:2]

            try:
                target_p = get_shared_frame_path()
                tmp_p = target_p.with_suffix(".tmp")
                tmp_p.write_bytes(img_bytes)
                tmp_p.replace(target_p)
            except Exception:
                pass

            return FrameCaptureResult(
                success=True,
                source=f"webcam_{used_idx}",
                image_base64=b64_str,
                width=w,
                height=h,
                timestamp=time.time(),
            )

        except Exception as e:
            logger.error(f"[CameraCapture] Optical capture failed: {e}", exc_info=True)
            return FrameCaptureResult(
                success=False,
                source="webcam",
                error=f"Webcam capture error: {str(e)}",
            )
        finally:
            if cap is not None and hasattr(cap, "release"):
                cap.release()
            logger.info(f"[PRIVACY.CAMERA] Optical sensor INACTIVE (hardware index={used_idx}) - Hardware released")
            try:
                from backend.sync.sync_manager import sync_manager
                sync_manager.state.optical_sensor_active = False
            except Exception:
                pass


class ScreenCapture:
    """Handles desktop screen capture with headless, Wayland, and multi-monitor awareness."""

    @staticmethod
    def _is_blank_frame(img: Any) -> bool:
        """Verifies whether an image is completely black / blank (common Wayland XWayland artifact)."""
        try:
            extrema = img.getextrema()
            if isinstance(extrema, tuple):
                # For RGB/RGBA, inspect the first 3 color channels
                rgb_ext = extrema[:3]
                # If every channel has max value <= 1, the frame is solid black
                if all(isinstance(ch, tuple) and ch[1] <= 1 for ch in rgb_ext):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def list_monitors() -> List[Dict[str, Any]]:
        """Discovers all available physical and virtual monitors on the host system.

        Returns a list of monitor metadata dictionaries:
        - index: 1-indexed monitor sequence
        - name: Hardware/Display name (eDP-1, DP-3, etc.)
        - description: Make/model or human-readable description
        - width: Horizontal pixel dimension
        - height: Vertical pixel dimension
        - is_focused: True if this display currently has active user focus
        - is_primary: True if this is the primary system display
        """
        monitors: List[Dict[str, Any]] = []

        # 1. Wayland Compositor Discovery (Hyprland / Sway)
        if os.getenv("WAYLAND_DISPLAY") or os.getenv("XDG_SESSION_TYPE") == "wayland":
            # 1a. Hyprland JSON query
            try:
                res = subprocess.run(
                    ["hyprctl", "-j", "monitors"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=1.5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    for idx, m in enumerate(data, start=1):
                        monitors.append({
                            "index": idx,
                            "name": m.get("name", f"Display {idx}"),
                            "description": m.get("description") or f"{m.get('make', '')} {m.get('model', '')}".strip(),
                            "width": int(m.get("width", 1920)),
                            "height": int(m.get("height", 1080)),
                            "is_focused": bool(m.get("focused", False)),
                            "is_primary": bool(m.get("id", 0) == 0),
                        })
                    if monitors:
                        return monitors
            except Exception:
                pass

            # 1b. Sway outputs query
            try:
                res = subprocess.run(
                    ["swaymsg", "-t", "get_outputs"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=1.5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    for idx, m in enumerate(data, start=1):
                        mode = m.get("current_mode", {})
                        monitors.append({
                            "index": idx,
                            "name": m.get("name", f"Display {idx}"),
                            "description": f"{m.get('make', '')} {m.get('model', '')}".strip() or m.get("name", ""),
                            "width": int(mode.get("width", 1920)),
                            "height": int(mode.get("height", 1080)),
                            "is_focused": bool(m.get("focused", False)),
                            "is_primary": bool(m.get("primary", idx == 1)),
                        })
                    if monitors:
                        return monitors
            except Exception:
                pass

        # 2. X11 xrandr Discovery
        try:
            res = subprocess.run(
                ["xrandr", "--listmonitors"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=1.5,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    m = re.search(r"^\s*(\d+):\s*([+*])?(\S+)\s+(\d+)/\d+x(\d+)/\d+\+\d+\+\d+\s+(\S+)", line)
                    if m:
                        idx = int(m.group(1)) + 1
                        is_primary = "*" in (m.group(2) or "") or idx == 1
                        w, h = int(m.group(4)), int(m.group(5))
                        name = m.group(6)
                        monitors.append({
                            "index": idx,
                            "name": name,
                            "description": f"{name} display",
                            "width": w,
                            "height": h,
                            "is_focused": False,
                            "is_primary": is_primary,
                        })
                if monitors:
                    return monitors
        except Exception:
            pass

        # 3. MSS Cross-Platform Fallback (X11 / Windows / macOS)
        try:
            import mss
            with mss.mss() as sct:
                for idx, m in enumerate(sct.monitors[1:], start=1):
                    monitors.append({
                        "index": idx,
                        "name": f"Display {idx}",
                        "description": f"Monitor {idx} ({m.get('width', 1920)}x{m.get('height', 1080)})",
                        "width": int(m.get("width", 1920)),
                        "height": int(m.get("height", 1080)),
                        "is_focused": False,
                        "is_primary": idx == 1,
                    })
        except Exception:
            pass

        return monitors

    @classmethod
    def capture_screen(
        cls,
        monitor_index: Optional[int] = None,
        monitor_name: Optional[str] = None,
    ) -> FrameCaptureResult:
        """Captures a screenshot with automatic Wayland, X11, multi-monitor, and anti-blank routing.

        Routing:
        - monitor_index=0: Captures all monitors stitched into a single panoramic image.
        - monitor_index=None: Captures the currently active/focused monitor (or primary).
        - monitor_index=1, 2...: Captures the specified 1-indexed monitor.
        - monitor_name="DP-3" | "eDP-1" | "laptop" | "external": Captures the display matching name.
        """
        caps = DeviceProbe.get_capabilities()
        if caps.is_headless or not caps.has_display:
            return FrameCaptureResult(
                success=False,
                source="screen",
                error="The host device is running in headless mode with no graphical display attached, sir.",
            )

        available_monitors = cls.list_monitors()
        target_name: Optional[str] = None
        target_idx: Optional[int] = monitor_index

        # Resolve target display
        if monitor_name:
            norm_query = monitor_name.lower().strip()
            for m in available_monitors:
                m_name = m["name"].lower()
                m_desc = m.get("description", "").lower()
                if (
                    norm_query in m_name
                    or norm_query in m_desc
                    or ("laptop" in norm_query and "edp" in m_name)
                    or ("external" in norm_query and ("dp" in m_name or "hdmi" in m_name))
                ):
                    target_name = m["name"]
                    target_idx = m["index"]
                    break

        if not target_name and target_idx is not None and target_idx > 0:
            for m in available_monitors:
                if m["index"] == target_idx:
                    target_name = m["name"]
                    break

        # If no specific monitor requested, default to focused monitor (or primary)
        if not target_name and target_idx is None:
            focused = next((m for m in available_monitors if m.get("is_focused")), None)
            if focused:
                target_name = focused["name"]
                target_idx = focused["index"]
            elif available_monitors:
                primary = next((m for m in available_monitors if m.get("is_primary")), available_monitors[0])
                target_name = primary["name"]
                target_idx = primary["index"]
            else:
                target_idx = 1

        is_wayland = bool(os.getenv("WAYLAND_DISPLAY") or os.getenv("XDG_SESSION_TYPE") == "wayland")
        from PIL import Image

        def _encode_img(img: Image.Image, name_tag: Optional[str], idx_tag: Optional[int]) -> FrameCaptureResult:
            orig_w, orig_h = img.size
            if img.width > 1920:
                ratio = 1920 / img.width
                img = img.resize((1920, int(img.height * ratio)), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.convert("RGB").save(buffer, format="JPEG", quality=85)
            b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return FrameCaptureResult(
                success=True,
                source="screen",
                image_base64=b64_str,
                width=orig_w,
                height=orig_h,
                monitor_index=idx_tag,
                monitor_name=name_tag or ("ALL_SCREENS" if idx_tag == 0 else f"Display {idx_tag or 1}"),
                timestamp=time.time(),
            )

        # ── Backend 1: Native Wayland (grim / spectacle / gnome-screenshot) ───
        if is_wayland:
            # 1a. grim (wlroots / Hyprland / Sway)
            if shutil.which("grim"):
                try:
                    cmd = ["grim"]
                    if target_idx == 0:
                        cmd.append("-")
                    elif target_name:
                        cmd.extend(["-o", target_name, "-"])
                    else:
                        cmd.append("-")

                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3.0)
                    if res.returncode == 0 and len(res.stdout) > 500:
                        img = Image.open(io.BytesIO(res.stdout))
                        if not cls._is_blank_frame(img):
                            logger.info(f"[ScreenCapture] Captured via grim (monitor={target_name or 'ALL'}, size={img.size})")
                            return _encode_img(img, target_name, target_idx)
                        else:
                            logger.warning(f"[ScreenCapture] grim captured a blank frame for {target_name}. Trying fallbacks...")
                except Exception as grim_err:
                    logger.warning(f"[ScreenCapture] grim capture error: {grim_err}")

            # 1b. spectacle (KDE Wayland)
            if shutil.which("spectacle"):
                try:
                    res = subprocess.run(
                        ["spectacle", "-b", "-n", "-o", "-"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=4.0,
                    )
                    if res.returncode == 0 and len(res.stdout) > 500:
                        img = Image.open(io.BytesIO(res.stdout))
                        if not cls._is_blank_frame(img):
                            return _encode_img(img, target_name, target_idx)
                except Exception as spec_err:
                    logger.debug(f"[ScreenCapture] spectacle error: {spec_err}")

            # 1c. gnome-screenshot (GNOME Wayland)
            if shutil.which("gnome-screenshot"):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                        tmp_p = Path(tf.name)
                    res = subprocess.run(
                        ["gnome-screenshot", "-f", str(tmp_p)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=4.0,
                    )
                    if res.returncode == 0 and tmp_p.exists() and tmp_p.stat().st_size > 500:
                        img = Image.open(tmp_p)
                        tmp_p.unlink(missing_ok=True)
                        if not cls._is_blank_frame(img):
                            return _encode_img(img, target_name, target_idx)
                except Exception as gnome_err:
                    logger.debug(f"[ScreenCapture] gnome-screenshot error: {gnome_err}")

        # ── Backend 2: MSS (Ultra-fast cross-platform for X11 / Win / macOS) ───
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
                if target_idx == 0:
                    mon_entry = monitors[0]
                elif target_idx is not None and target_idx < len(monitors):
                    mon_entry = monitors[target_idx]
                else:
                    mon_entry = monitors[1] if len(monitors) > 1 else monitors[0]

                sct_img = sct.grab(mon_entry)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                if not cls._is_blank_frame(img):
                    logger.info(f"[ScreenCapture] Captured via MSS (index={target_idx}, size={img.size})")
                    return _encode_img(img, target_name, target_idx)
                else:
                    logger.warning("[ScreenCapture] MSS captured blank frame (XWayland security isolation). Trying fallbacks...")
        except Exception as mss_err:
            logger.warning(f"[ScreenCapture] MSS capture failed ({mss_err}), attempting PIL fallback.")

        # ── Backend 3: PIL ImageGrab ──────────────────────────────────────────
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            if img and not cls._is_blank_frame(img):
                logger.info(f"[ScreenCapture] Captured via PIL.ImageGrab (size={img.size})")
                return _encode_img(img, target_name, target_idx)
        except Exception as pil_err:
            logger.debug(f"[ScreenCapture] PIL ImageGrab failed: {pil_err}")

        # ── Backend 4: X11 CLI Fallback (import / ImageMagick) ────────────────
        if shutil.which("import"):
            try:
                res = subprocess.run(
                    ["import", "-window", "root", "png:-"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=3.0,
                )
                if res.returncode == 0 and len(res.stdout) > 500:
                    img = Image.open(io.BytesIO(res.stdout))
                    if not cls._is_blank_frame(img):
                        return _encode_img(img, target_name, target_idx)
            except Exception:
                pass

        return FrameCaptureResult(
            success=False,
            source="screen",
            error=(
                "Unable to capture non-blank desktop screen image, sir. "
                "On Wayland sessions, please ensure 'grim' is installed."
            ),
        )
