"""VESPER Frame Capture & Vision Pipeline Utility.

Captures optical frames from:
1. Primary Webcam (/dev/video0 or OpenCV index 0): The PRIMARY sensor for OCR, objects, and VLLM questions.
2. Screen Display (Desktop Monitor / Active Window): The SECONDARY sensor when the user explicitly queries their monitor.

Provides base64 JPEG encoding and dimension metadata.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time
from typing import Optional, Tuple
from pydantic import BaseModel, Field

from backend.vision.device_probe import DeviceProbe

logger = logging.getLogger("vesper.vision.camera_stream")


class FrameCaptureResult(BaseModel):
    """Encapsulates a captured visual frame."""

    success: bool = True
    source: str = "webcam"  # "webcam" | "screen"
    image_base64: str = ""
    width: int = 0
    height: int = 0
    timestamp: float = Field(default_factory=time.time)
    error: Optional[str] = None


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
        try:
            # Try specified camera_index or fallback through available indices
            indices_to_try = [camera_index] + [i for i in caps.available_cameras if i != camera_index]
            frame = None
            used_idx = camera_index

            for idx in indices_to_try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
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

            b64_str = base64.b64encode(encoded_img.tobytes()).decode("utf-8")
            h, w = frame.shape[:2]

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


class ScreenCapture:
    """Handles desktop screen capture with headless and multi-monitor awareness."""

    @staticmethod
    def capture_screen(monitor_index: int = 1) -> FrameCaptureResult:
        """Captures a screenshot of the specified monitor (1 = primary display)."""
        caps = DeviceProbe.get_capabilities()
        if caps.is_headless or not caps.has_display:
            return FrameCaptureResult(
                success=False,
                source="screen",
                error="The host device is running in headless mode with no graphical display attached, sir.",
            )

        # Attempt MSS capture first (ultra-fast cross-platform)
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
                mon_idx = monitor_index if monitor_index < len(monitors) else 0
                sct_img = sct.grab(monitors[mon_idx])

                # Convert to PIL Image for lightweight JPEG encoding
                from PIL import Image
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                # Resize if high-res 4K to conserve VLLM tokens
                if img.width > 1920:
                    ratio = 1920 / img.width
                    img = img.resize((1920, int(img.height * ratio)), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

                return FrameCaptureResult(
                    success=True,
                    source="screen",
                    image_base64=b64_str,
                    width=img.width,
                    height=img.height,
                    timestamp=time.time(),
                )
        except Exception as mss_err:
            logger.warning(f"[ScreenCapture] MSS capture failed ({mss_err}), attempting PIL fallback.")

        # Fallback to PIL ImageGrab if available
        try:
            from PIL import ImageGrab, Image
            img = ImageGrab.grab()
            if img:
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
                    width=img.width,
                    height=img.height,
                    timestamp=time.time(),
                )
        except Exception as pil_err:
            logger.error(f"[ScreenCapture] Both MSS and PIL screen captures failed: {pil_err}")

        return FrameCaptureResult(
            success=False,
            source="screen",
            error="Unable to access the graphical display server for screen perception, sir.",
        )
