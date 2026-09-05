"""VESPER Gateway Camera Streaming & Preview REST Routes.

Provides high-performance MJPEG live streaming and snapshot capabilities
directly from the system optical camera (/dev/video0 or OpenCV device index 0).
Features a multi-consumer CameraHub that fans out frames without hardware lock
contention, enabling simultaneous preview, gesture recognition, and snapshots.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from backend.vision.device_probe import DeviceProbe

logger = logging.getLogger("vesper.gateway.camera")

router = APIRouter(prefix="/api/camera", tags=["Camera"])


class CameraHub:
    """Singleton managing optical hardware capture and fanning out frames to active subscribers."""

    def __init__(self) -> None:
        self._cap = None
        self._latest_jpeg: Optional[bytes] = None
        self._active_clients: int = 0
        self._lock = asyncio.Lock()
        self._running = False
        self._capture_task: Optional[asyncio.Task] = None
        self._condition = asyncio.Condition()

    def _open_device(self, index: int = 0):
        try:
            import cv2
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                return cap
            cap.release()
        except Exception as e:
            logger.warning(f"[CameraHub] Failed to open OpenCV device {index}: {e}")
        return None

    async def _capture_loop(self, index: int = 0) -> None:
        import cv2
        logger.info(f"[CameraHub] Opening optical hardware device {index}")
        self._cap = await asyncio.to_thread(self._open_device, index)
        if not self._cap:
            logger.error(f"[CameraHub] Unable to acquire hardware device {index}")
            self._running = False
            return

        try:
            from backend.sync.sync_manager import sync_manager
            sync_manager.state.optical_sensor_active = True
        except Exception:
            pass

        encode_param = [cv2.IMWRITE_JPEG_QUALITY, 80]
        target_delay = 1.0 / 25.0

        try:
            while self._running and self._active_clients > 0:
                t0 = time.time()
                ret, frame = await asyncio.to_thread(self._cap.read)
                if ret and frame is not None:
                    success, buffer = await asyncio.to_thread(cv2.imencode, ".jpg", frame, encode_param)
                    if success:
                        frame_bytes = buffer.tobytes()
                        async with self._condition:
                            self._latest_jpeg = frame_bytes
                            self._condition.notify_all()

                        try:
                            from backend.vision.camera_stream import get_shared_frame_path
                            target_p = get_shared_frame_path()
                            tmp_p = target_p.with_suffix(".tmp")
                            tmp_p.write_bytes(frame_bytes)
                            tmp_p.replace(target_p)
                        except Exception:
                            pass

                elapsed = time.time() - t0
                sleep_time = max(0.005, target_delay - elapsed)
                await asyncio.sleep(sleep_time)

        finally:
            logger.info("[CameraHub] Closing optical hardware device")
            if self._cap:
                await asyncio.to_thread(self._cap.release)
                self._cap = None
            self._running = False
            self._capture_task = None
            try:
                from backend.sync.sync_manager import sync_manager
                sync_manager.state.optical_sensor_active = False
            except Exception:
                pass

    async def start(self, index: int = 0) -> None:
        async with self._lock:
            self._active_clients += 1
            if not self._running:
                self._running = True
                self._capture_task = asyncio.create_task(self._capture_loop(index))

    async def stop(self) -> None:
        async with self._lock:
            self._active_clients = max(0, self._active_clients - 1)
            if self._active_clients == 0:
                self._running = False
                if self._capture_task:
                    self._capture_task.cancel()
                    self._capture_task = None

    async def get_latest_frame(self, timeout: float = 1.0) -> Optional[bytes]:
        if self._latest_jpeg:
            return self._latest_jpeg
        try:
            async with self._condition:
                await asyncio.wait_for(self._condition.wait(), timeout=timeout)
                return self._latest_jpeg
        except asyncio.TimeoutError:
            return self._latest_jpeg


# Singleton hub instance
_camera_hub = CameraHub()


@router.get("/status")
async def camera_status() -> dict:
    """Returns the optical hardware availability and capabilities."""
    caps = DeviceProbe.get_capabilities()
    primary = f"/dev/video{caps.available_cameras[0]}" if caps.available_cameras else None
    return {
        "available": caps.has_camera,
        "available_indices": caps.available_cameras,
        "primary_device": primary,
    }


@router.get("/snapshot")
@router.head("/snapshot")
async def camera_snapshot(index: int = 0) -> Response:
    """Captures a single optical JPEG frame from the camera."""
    # 1. Non-blocking check if a live GestureWorker is actively publishing optical frames
    try:
        from backend.vision.camera_stream import get_shared_frame_path
        shared_p = get_shared_frame_path()
        if shared_p.exists() and (time.time() - shared_p.stat().st_mtime) < 2.5:
            raw_bytes = shared_p.read_bytes()
            if len(raw_bytes) > 1000:
                return Response(
                    content=raw_bytes,
                    media_type="image/jpeg",
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "*",
                        "Access-Control-Allow-Headers": "*",
                        "Cache-Control": "no-cache, no-store",
                    },
                )
    except Exception:
        pass

    # 2. Check active CameraHub stream
    frame_bytes = await _camera_hub.get_latest_frame(timeout=0.2)
    if not frame_bytes:
        # Hub not actively running; temporarily start and grab one frame
        await _camera_hub.start(index)
        try:
            frame_bytes = await _camera_hub.get_latest_frame(timeout=2.0)
        finally:
            await _camera_hub.stop()

    if not frame_bytes:
        return Response(status_code=503, content=b"Camera hardware unavailable", media_type="text/plain")

    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "Cache-Control": "no-cache, no-store",
        },
    )


@router.get("/stream")
@router.head("/stream")
async def camera_stream(request: Request, index: int = 0) -> StreamingResponse:
    """Streams live optical frames as a multipart/x-mixed-replace MJPEG video stream."""

    async def _frame_generator() -> AsyncGenerator[bytes, None]:
        await _camera_hub.start(index)
        try:
            while True:
                if await request.is_disconnected():
                    break

                frame_bytes = await _camera_hub.get_latest_frame(timeout=0.5)
                if not frame_bytes:
                    await asyncio.sleep(0.05)
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n"
                    + frame_bytes + b"\r\n"
                )
                await asyncio.sleep(0.03)

        finally:
            await _camera_hub.stop()

    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Expose-Headers": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        },
    )
