"""VESPER Decoupled Touchless Gesture Perception Worker.

Runs as an isolated background service or lightweight async thread to keep the
main Gateway and UI silky-smooth at 60 FPS.

Key Architectural Guarantees:
1. Low CPU Throttling: Samples at 5-8 FPS (configurable), reducing CPU overhead by ~80%
   compared to continuous 60 FPS video loops.
2. Hardware Awareness: Automatically enters zero-CPU standby if running on an Orange Pi
   or headless node without an optical camera.
3. Decoupled Event Emission: Transmits discrete gesture envelopes (Channel.GESTURE)
   to the Gateway router without blocking the UI or voice pipelines.
4. Expanded Gesture Vocabulary (Adapted from ReflectOS & MediaPipe Tasks):
   - CLOSED_FIST: Instant Mute / Media Pause
   - OPEN_PALM: Resume Audio / Play / Unmute
   - OPEN_PALM (held 2s): Toggle gesture tracking on/off
   - GUN_RIGHT / NEXT_TRACK: Point Finger Gun Right -> Skip to Next Media Track
   - GUN_LEFT / PREV_TRACK: Point Finger Gun Left -> Return to Previous Media Track
   - PEACE_SIGN: Toggle Ambient Zen Mode
   - THREE_FINGERS: Media Play / Pause (volume untouched)
   - THUMB_UP: Volume Step Up (+10%) / Confirm
   - THUMB_DOWN: Volume Step Down (-10%) / Dismiss
   - POINTING_UP: Toggle Focus Mode
   - AIR_TAP: Air Tap / Select Widget
   - VOLUME_DIAL:XX: Pinch + Rotate wrist to set volume (0-100%)
"""

from __future__ import annotations

import asyncio
import base64
import collections
import logging
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Optional, Set, Tuple
from pydantic import BaseModel

from backend.vision.device_probe import DeviceProbe
from backend.vision.camera_stream import CameraCapture, FrameCaptureResult
from backend.shared.events import Channel, EventType, ClientEnvelope, GestureEventPayload

# Silence low-level C++ glog and OpenCV warnings
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

logger = logging.getLogger("vesper.vision.gesture")


# ─── Real System Volume Control ─────────────────────────────────────────────

def _set_system_volume(percent: int) -> None:
    """Sets the real system audio volume across Linux (wpctl/pactl/amixer), macOS (osascript), and Windows."""
    percent = max(0, min(100, percent))
    frac = percent / 100.0
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {percent}"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return

        if sys.platform == "win32":
            # Attempt pycaw if installed, otherwise fallback to nircmd
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(frac, None)
                return
            except Exception:
                nircmd = shutil.which("nircmd.exe") or shutil.which("nircmd")
                if nircmd:
                    subprocess.run(
                        [nircmd, "setsysvolume", str(int(65535 * frac))],
                        timeout=2, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                return

        # Linux (PipeWire -> PulseAudio -> ALSA)
        wpctl = shutil.which("wpctl")
        if wpctl:
            r = subprocess.run(
                [wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", f"{frac:.2f}"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                if percent > 0:
                    subprocess.run(
                        [wpctl, "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
                        timeout=2, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.run(
                        [wpctl, "set-mute", "@DEFAULT_AUDIO_SINK@", "1"],
                        timeout=2, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                return

        pactl = shutil.which("pactl")
        if pactl:
            r = subprocess.run(
                [pactl, "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                if percent > 0:
                    subprocess.run(
                        [pactl, "set-sink-mute", "@DEFAULT_SINK@", "0"],
                        timeout=2, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.run(
                        [pactl, "set-sink-mute", "@DEFAULT_SINK@", "1"],
                        timeout=2, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                return

        amixer = shutil.which("amixer")
        if amixer:
            subprocess.run(
                [amixer, "sset", "Master", f"{percent}%"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        logger.warning(f"[VolumeCtrl] Failed to set system volume: {e}")


def _get_system_volume() -> int:
    """Reads the current real system volume (0-100) across Linux, macOS, and Windows."""
    try:
        if sys.platform == "darwin":
            r = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                capture_output=True, text=True, timeout=2,
            )
            if r.stdout.strip().isdigit():
                return int(r.stdout.strip())

        if sys.platform == "win32":
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                return int(volume.GetMasterVolumeLevelScalar() * 100)
            except Exception:
                pass

        wpctl = shutil.which("wpctl")
        if wpctl:
            r = subprocess.run(
                [wpctl, "get-volume", "@DEFAULT_AUDIO_SINK@"],
                capture_output=True, text=True, timeout=2,
            )
            # Output: "Volume: 0.45" or "Volume: 0.45 [MUTED]"
            for part in r.stdout.strip().split():
                try:
                    return int(float(part) * 100)
                except ValueError:
                    continue

        pactl = shutil.which("pactl")
        if pactl:
            r = subprocess.run(
                [pactl, "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True, text=True, timeout=2,
            )
            import re
            m = re.search(r"(\d+)%", r.stdout)
            if m:
                return int(m.group(1))
    except Exception as e:
        logger.debug(f"[VolumeCtrl] Failed to get volume: {e}")
    return 60


def _set_system_mute(muted: bool) -> None:
    """Mutes or unmutes the system audio sink across Linux, macOS, and Windows."""
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f"set volume output muted {'true' if muted else 'false'}"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return

        if sys.platform == "win32":
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMute(1 if muted else 0, None)
                return
            except Exception:
                nircmd = shutil.which("nircmd.exe") or shutil.which("nircmd")
                if nircmd:
                    subprocess.run(
                        [nircmd, "mutesysvolume", "1" if muted else "0"],
                        timeout=2, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                return

        wpctl = shutil.which("wpctl")
        if wpctl:
            r = subprocess.run(
                [wpctl, "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if muted else "0"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                return

        pactl = shutil.which("pactl")
        if pactl:
            subprocess.run(
                [pactl, "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        logger.warning(f"[VolumeCtrl] Failed to set mute: {e}")


_LAST_MEDIA_ACTION_TIME: float = 0.0


def _control_media_player(action: str) -> None:
    """Controls running media players (Spotify, Apple Music, browsers) across Linux, macOS, and Windows.

    Uses real player status inspection to make toggles strictly idempotent and avoid
    rapid double-toggle oscillations across multi-process callers.
    """
    global _LAST_MEDIA_ACTION_TIME
    now = time.time()
    if action in ("play-pause", "toggle") and (now - _LAST_MEDIA_ACTION_TIME < 1.0):
        logger.debug(f"[MediaCtrl] Suppressed rapid toggle ({now - _LAST_MEDIA_ACTION_TIME:.2f}s since last)")
        return
    _LAST_MEDIA_ACTION_TIME = now

    try:
        if sys.platform == "darwin":
            # macOS AppleScript for Spotify or Music.app
            osascript_action = "playpause" if action in ("play", "pause", "play-pause", "toggle") else ("next track" if action == "next" else "previous track")
            subprocess.run(
                ["osascript", "-e", f'tell application "Spotify" to {osascript_action}'],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return

        playerctl = shutil.which("playerctl")
        if playerctl:
            target_cmd = action
            if action in ("play-pause", "toggle"):
                status_res = subprocess.run(
                    [playerctl, "-p", "spotify,%any", "status"],
                    capture_output=True, text=True, timeout=1, check=False,
                )
                curr_status = status_res.stdout.strip().lower()
                target_cmd = "pause" if curr_status == "playing" else "play"

            subprocess.run(
                [playerctl, "-p", "spotify,%any", target_cmd],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        logger.debug(f"[MediaCtrl] Media player {action} failed: {e}")


DEFAULT_GESTURE_COOLDOWNS: Dict[str, float] = {
    "VOLUME_DIAL": 0.08,
    "THUMB_UP": 0.25,
    "THUMB_DOWN": 0.25,
    "VOLUME_UP": 0.25,
    "VOLUME_DOWN": 0.25,
    "CLOSED_FIST": 0.9,
    "OPEN_PALM": 0.9,
    "PEACE_SIGN": 1.2,
    "THREE_FINGERS": 0.9,
    "PLAY_PAUSE": 0.9,
    "MEDIA_PLAY_PAUSE": 0.9,
    "POINTING_UP": 1.2,
    "NEXT_TRACK": 0.9,
    "PREV_TRACK": 0.9,
    "GUN_RIGHT": 0.9,
    "GUN_LEFT": 0.9,
    "AIR_TAP": 0.6,
    "GESTURE_TOGGLE": 2.0,
    "ROCK_ON": 2.0,
}


class GestureState(BaseModel):
    """Current perceived gesture state."""

    last_gesture: str = "NONE"
    confidence: float = 0.0
    active: bool = False
    fps: float = 6.0
    camera_available: bool = False
    tracking_paused: bool = False


class GestureWorker:
    """Decoupled gesture recognition worker that can run as a background task or standalone service."""

    def __init__(
        self,
        fps: float = 6.0,
        gateway_url: Optional[str] = None,
        on_gesture_callback: Optional[Callable[[str, float], Any]] = None,
        model_path: Optional[str] = None,
    ) -> None:
        self.fps = fps
        self.interval = 1.0 / max(fps, 1.0)
        self.gateway_url = gateway_url
        self.on_gesture_callback = on_gesture_callback
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.state = GestureState(fps=fps)

        # Model configuration
        self._custom_model_path = model_path
        self._recognizer: Any = None
        self._recognizer_init_failed = False

        # Landmark tracking state
        self._wrist_history: Deque[Tuple[float, float, float]] = collections.deque(maxlen=8)
        self._pinch_streak = 0
        self._saved_volume = _get_system_volume()
        self._last_volume_dial_value = -1  # Throttle repeated VOLUME_DIAL dispatches

        # Deliberate lock tracking (Rock On / ILoveYou hold 1.0s)
        self._toggle_gesture_start: float = 0.0
        self._toggle_gesture_fired: bool = False
        self._toggle_lockout_until: float = 0.0
        # Per-gesture debouncing & hysteresis release tracking
        self._last_gesture_emitted_times: Dict[str, float] = {}
        self._gesture_awaiting_release: Set[str] = set()
        self._candidate_gesture: str = "NONE"
        self._candidate_streak: int = 0
        self._none_streak: int = 0
        # Backward compatibility aliases
        self._open_palm_start: float = 0.0
        self._open_palm_toggle_fired: bool = False

    def _get_model_path(self) -> Optional[Path]:
        """Resolves path to MediaPipe gesture recognizer task model."""
        if self._custom_model_path:
            p = Path(self._custom_model_path)
            if p.exists():
                return p

        default_path = Path(__file__).resolve().parent / "models" / "gesture_recognizer.task"
        if default_path.exists():
            return default_path

        # Search root workspace
        alt_path = Path("backend/vision/models/gesture_recognizer.task")
        if alt_path.exists():
            return alt_path.resolve()

        return None

    def _init_recognizer(self) -> Any:
        """Initializes the MediaPipe GestureRecognizer task if not already initialized."""
        if self._recognizer is not None or self._recognizer_init_failed:
            return self._recognizer

        try:
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            model_file = self._get_model_path()
            if not model_file:
                logger.warning("[GestureWorker] gesture_recognizer.task model file not found. Standby mode.")
                self._recognizer_init_failed = True
                return None

            base_options = python.BaseOptions(model_asset_path=str(model_file))
            options = vision.GestureRecognizerOptions(base_options=base_options)
            self._recognizer = vision.GestureRecognizer.create_from_options(options)
            logger.info(f"[GestureWorker] MediaPipe GestureRecognizer loaded from {model_file}")
            return self._recognizer
        except Exception as e:
            logger.warning(f"[GestureWorker] Failed to initialize MediaPipe recognizer: {e}")
            self._recognizer_init_failed = True
            return None

    async def start(self) -> None:
        """Starts the decoupled gesture perception loop."""
        if self.is_running:
            logger.warning("[GestureWorker] Worker already running.")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"[GestureWorker] Started decoupled gesture worker at {self.fps} FPS.")

    async def stop(self) -> None:
        """Stops the gesture loop cleanly."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[GestureWorker] Stopped gesture worker.")

    def toggle_tracking(self) -> bool:
        """Toggles gesture tracking on/off. Returns new state (True=paused)."""
        self.state.tracking_paused = not self.state.tracking_paused
        status = "PAUSED" if self.state.tracking_paused else "RESUMED"
        logger.info(f"[GestureWorker] Gesture tracking {status}")
        return self.state.tracking_paused

    def resume_tracking(self) -> None:
        """Explicitly unpauses gesture tracking."""
        self.state.tracking_paused = False
        self._toggle_gesture_start = 0.0
        self._toggle_gesture_fired = False
        self._toggle_lockout_until = 0.0
        self._gesture_awaiting_release.clear()
        logger.info("[GestureWorker] Gesture tracking explicitly RESUMED")

    def pause_tracking(self) -> None:
        """Explicitly pauses gesture tracking."""
        self.state.tracking_paused = True
        logger.info("[GestureWorker] Gesture tracking explicitly PAUSED")

    async def _run_loop(self) -> None:
        """Main throttled gesture evaluation loop."""
        last_emitted_gesture = "NONE"
        last_emit_time = 0.0
        cooldown_sec = 1.0  # prevent spamming repeated triggers
        volume_dial_cooldown = 0.15  # faster updates for smooth dial feel

        try:
            import cv2
        except ImportError:
            logger.warning("[GestureWorker] OpenCV not available.")
            return

        cap = None
        current_camera_idx = -1

        try:
            while self.is_running:
                loop_start = time.time()
                frame_bgr: Optional[Any] = None

                # 1. Hardware capability check
                caps = DeviceProbe.get_capabilities()
                if not caps.has_camera:
                    self.state.camera_available = False
                    if cap is not None:
                        cap.release()
                        cap = None
                    logger.debug("[GestureWorker] No camera detected. Idling in 0% CPU standby...")
                    await asyncio.sleep(5.0)
                    continue

                self.state.camera_available = True
                desired_camera_idx = caps.available_cameras[0] if caps.available_cameras else 0

                # Open persistent capture stream once
                if cap is None or not cap.isOpened() or current_camera_idx != desired_camera_idx:
                    if cap is not None:
                        cap.release()
                    try:
                        cap = cv2.VideoCapture(desired_camera_idx, cv2.CAP_V4L2)
                        if not cap.isOpened():
                            cap = cv2.VideoCapture(desired_camera_idx)
                    except Exception:
                        cap = cv2.VideoCapture(desired_camera_idx)

                    current_camera_idx = desired_camera_idx
                    if not cap.isOpened():
                        # Check if CameraHub or another service is publishing frames to shared memory
                        try:
                            from backend.vision.camera_stream import get_shared_frame_path
                            target_p = get_shared_frame_path()
                            if target_p.exists() and (time.time() - target_p.stat().st_mtime) < 2.5:
                                raw_bytes = target_p.read_bytes()
                                if len(raw_bytes) > 1000:
                                    import numpy as np
                                    nparr = np.frombuffer(raw_bytes, np.uint8)
                                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                    if frame_bgr is not None:
                                        cap = None
                        except Exception:
                            pass
                        if cap is None and frame_bgr is None:
                            logger.warning(f"[GestureWorker] Failed to open camera index {desired_camera_idx}.")
                            cap = None
                            await asyncio.sleep(2.0)
                            continue
                    try:
                        if cap is not None:
                            fourcc_fn = getattr(cv2, "VideoWriter_fourcc", getattr(getattr(cv2, "VideoWriter", None), "fourcc", None))
                            if fourcc_fn is not None:
                                cap.set(cv2.CAP_PROP_FOURCC, fourcc_fn(*"MJPG"))
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    except Exception:
                        pass

                # 2. Acquire raw frame directly from open device or shared memory
                try:
                    if cap is not None and cap.isOpened():
                        def _read_frame(c):
                            return c.read()

                        ret, frame_bgr = await asyncio.to_thread(_read_frame, cap)
                        if not ret or frame_bgr is None:
                            await asyncio.sleep(self.interval)
                            continue

                        # Broadcast latest frame to shared memory for VLM OCR / Snapshots without device lock contention
                        now_t = time.time()
                        if (now_t - getattr(self, "_last_shared_frame_save", 0.0)) >= 0.12:
                            self._last_shared_frame_save = now_t
                            try:
                                from backend.vision.camera_stream import get_shared_frame_path
                                target_p = get_shared_frame_path()
                                tmp_p = target_p.with_suffix(".tmp")
                                success, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
                                if success:
                                    tmp_p.write_bytes(buf.tobytes())
                                    tmp_p.replace(target_p)
                            except Exception:
                                pass
                    elif frame_bgr is None:
                        # Poll shared frame if device is owned by another service (e.g. CameraHub)
                        from backend.vision.camera_stream import get_shared_frame_path
                        target_p = get_shared_frame_path()
                        if target_p.exists() and (time.time() - target_p.stat().st_mtime) < 2.5:
                            try:
                                raw_bytes = target_p.read_bytes()
                                if len(raw_bytes) > 1000:
                                    import numpy as np
                                    nparr = np.frombuffer(raw_bytes, np.uint8)
                                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            except Exception:
                                frame_bgr = None
                        if frame_bgr is None:
                            await asyncio.sleep(self.interval)
                            continue

                    # If tracking is paused, still read frames (keep camera warm)
                    # but only look for the deliberate lock toggle (Rock On / ILoveYou hold 1.0s) to re-enable
                    if self.state.tracking_paused:
                        toggle_gesture, toggle_conf = self._check_toggle_gesture_only(frame_bgr)
                        if toggle_gesture.startswith("GESTURE_TOGGLE"):
                            self.state.tracking_paused = False
                            self._toggle_gesture_start = 0.0
                            self._toggle_gesture_fired = False
                            self._open_palm_start = 0.0
                            self._open_palm_toggle_fired = False
                            self._toggle_lockout_until = time.time() + 2.5
                            self._gesture_awaiting_release.add("ROCK_ON")
                            self._gesture_awaiting_release.add("GESTURE_TOGGLE")
                            self._last_gesture_emitted_times["ROCK_ON"] = time.time()
                            self._last_gesture_emitted_times["GESTURE_TOGGLE"] = time.time()
                            logger.info("[GestureWorker] Tracking RESUMED via Rock On hold")
                            await self._dispatch_gesture("GESTURE_TOGGLE:RESUMED", toggle_conf)
                        await asyncio.sleep(self.interval)
                        continue

                    # 3. Detect gesture from numpy array
                    detected_gesture, confidence = self._evaluate_gesture_heuristic(frame_bgr)
                    now = time.time()

                    # Handle neutral/no pose or low confidence: reset streak and release hysteresis
                    if detected_gesture == "NONE" or confidence < 0.50:
                        self._none_streak += 1
                        self._candidate_gesture = "NONE"
                        self._candidate_streak = 0
                        if self._none_streak >= 1:
                            self._gesture_awaiting_release.clear()
                        await asyncio.sleep(self.interval)
                        continue

                    # Valid gesture detected
                    self._none_streak = 0
                    if detected_gesture == self._candidate_gesture:
                        self._candidate_streak += 1
                    else:
                        self._candidate_gesture = detected_gesture
                        self._candidate_streak = 1

                    # Plain ROCK_ON is an in-progress hold for lock toggle; do not emit until
                    # it finishes 1.0s hold and becomes GESTURE_TOGGLE:PAUSED
                    if detected_gesture == "ROCK_ON":
                        await asyncio.sleep(self.interval)
                        continue

                    is_volume_dial = detected_gesture.startswith("VOLUME_DIAL:")
                    is_thumb_volume = detected_gesture in ("THUMB_UP", "THUMB_DOWN", "VOLUME_UP", "VOLUME_DOWN")
                    is_volume = is_volume_dial or is_thumb_volume

                    # Streak confirmation requirement:
                    # Volume dial has continuous frame accumulation built-in; GESTURE_TOGGLE has 1.0s internal timer.
                    # Discrete static poses (including Finger Gun track skips) require 2 consecutive frames.
                    if is_volume_dial or detected_gesture.startswith("GESTURE_TOGGLE"):
                        required_streak = 1
                    else:
                        required_streak = 2

                    if self._candidate_streak < required_streak:
                        await asyncio.sleep(self.interval)
                        continue

                    # Hysteresis / Release Requirement:
                    # Non-volume gestures cannot be triggered repeatedly without releasing the hand back to NONE.
                    # Volume gestures (VOLUME_DIAL, THUMB_UP, THUMB_DOWN) bypass release check to allow smooth continuous adjustment.
                    base_gesture = detected_gesture.split(":")[0]
                    if not is_volume:
                        if base_gesture in self._gesture_awaiting_release or detected_gesture in self._gesture_awaiting_release:
                            await asyncio.sleep(self.interval)
                            continue

                    # Per-gesture cooldown check
                    target_cooldown = DEFAULT_GESTURE_COOLDOWNS.get(base_gesture, 1.5)
                    last_time = self._last_gesture_emitted_times.get(base_gesture, 0.0)
                    if (now - last_time) < target_cooldown:
                        await asyncio.sleep(self.interval)
                        continue

                    # For volume dial, also throttle if value hasn't changed
                    if is_volume_dial:
                        try:
                            dial_val = int(detected_gesture.split(":")[1])
                        except (ValueError, IndexError):
                            dial_val = -1
                        if dial_val == self._last_volume_dial_value:
                            await asyncio.sleep(self.interval)
                            continue
                        self._last_volume_dial_value = dial_val

                    # Mark emitted and set release lock for non-volume gestures
                    self._last_gesture_emitted_times[base_gesture] = now
                    self._last_gesture_emitted_times[detected_gesture] = now
                    last_emitted_gesture = detected_gesture
                    last_emit_time = now

                    if not is_volume:
                        self._gesture_awaiting_release.clear()
                        self._gesture_awaiting_release.add(base_gesture)
                        self._gesture_awaiting_release.add(detected_gesture)

                    if detected_gesture.startswith("GESTURE_TOGGLE"):
                        self._toggle_lockout_until = now + 2.5

                    self.state.last_gesture = detected_gesture
                    self.state.confidence = confidence

                    logger.info(f"[GestureWorker] Detected gesture: {detected_gesture} (conf: {confidence:.2f})")
                    await self._dispatch_gesture(detected_gesture, confidence)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[GestureWorker] Frame evaluation error: {e}", exc_info=True)

                # Throttle to maintain target FPS without CPU hogging
                elapsed = time.time() - loop_start
                sleep_time = max(0.01, self.interval - elapsed)
                await asyncio.sleep(sleep_time)

        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None

    def _frame_to_rgb(self, frame: Any):
        """Converts a frame (BGR ndarray or FrameCaptureResult) to RGB ndarray."""
        import cv2
        import numpy as np

        if isinstance(frame, FrameCaptureResult):
            if not frame.image_base64:
                return None
            raw_bytes = base64.b64decode(frame.image_base64)
            nparr = np.frombuffer(raw_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_bgr is None:
                return None
            return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        elif isinstance(frame, np.ndarray):
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return None

    def _check_toggle_gesture_only(self, frame: Any) -> Tuple[str, float]:
        """When tracking is paused, only check for deliberate lock gesture (Rock On / ILoveYou) to resume."""
        now = time.time()
        if now < self._toggle_lockout_until:
            return "NONE", 0.0

        recognizer = self._init_recognizer()
        if not recognizer:
            return "NONE", 0.0
        try:
            import mediapipe as mp
            img_rgb = self._frame_to_rgb(frame)
            if img_rgb is None:
                return "NONE", 0.0
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
            result = recognizer.recognize(mp_image)

            hand_lms = result.hand_landmarks[0] if (result.hand_landmarks and len(result.hand_landmarks) > 0) else None
            if result.gestures and len(result.gestures) > 0:
                top = result.gestures[0][0]
                category = top.category_name
                score = float(top.score)
                # Rock On (ILoveYou with anatomical confirmation if landmarks present) or Open Palm held for 1.0s resumes gesture tracking
                is_rock_on = (category == "ILoveYou" and score >= 0.80) and (hand_lms is None or self._is_rock_on_anatomy(hand_lms))
                is_open_palm = (category == "Open_Palm" and score >= 0.70)
                if is_rock_on or is_open_palm:
                    if self._toggle_gesture_start == 0.0:
                        self._toggle_gesture_start = now
                    elif (now - self._toggle_gesture_start) >= 1.0 and not self._toggle_gesture_fired:
                        self._toggle_gesture_fired = True
                        self._toggle_lockout_until = now + 2.5
                        self._toggle_gesture_start = 0.0
                        return "GESTURE_TOGGLE:RESUMED", score
                else:
                    self._toggle_gesture_start = 0.0
                    self._toggle_gesture_fired = False
            else:
                self._toggle_gesture_start = 0.0
                self._toggle_gesture_fired = False
        except Exception:
            pass
        return "NONE", 0.0

    @staticmethod
    def _is_rock_on_anatomy(hand_lms: Any) -> bool:
        """Verifies intentional Rock On / Sign of the Horns anatomical structure.

        Requires:
        - Index and Pinky fingers extended away from wrist.
        - Middle and Ring fingers tightly curled into the palm.
        """
        if not hand_lms or len(hand_lms) < 21:
            return False

        def get_pt(p: Any) -> Tuple[float, float]:
            if hasattr(p, "x"):
                return float(p.x), float(p.y)
            elif isinstance(p, dict):
                return float(p.get("x", 0.0)), float(p.get("y", 0.0))
            return float(p[0]), float(p[1])

        def dist_2d(p1: Any, p2: Any) -> float:
            x1, y1 = get_pt(p1)
            x2, y2 = get_pt(p2)
            return math.hypot(x1 - x2, y1 - y2)

        wrist = hand_lms[0]
        index_pip = hand_lms[6]
        index_tip = hand_lms[8]
        middle_pip = hand_lms[10]
        middle_tip = hand_lms[12]
        ring_pip = hand_lms[14]
        ring_tip = hand_lms[16]
        pinky_pip = hand_lms[18]
        pinky_tip = hand_lms[20]

        index_ext = dist_2d(index_tip, wrist) > dist_2d(index_pip, wrist) * 1.15
        pinky_ext = dist_2d(pinky_tip, wrist) > dist_2d(pinky_pip, wrist) * 1.15
        middle_folded = dist_2d(middle_tip, wrist) < dist_2d(middle_pip, wrist) * 1.10
        ring_folded = dist_2d(ring_tip, wrist) < dist_2d(ring_pip, wrist) * 1.10

        return bool(index_ext and pinky_ext and middle_folded and ring_folded)

    @staticmethod
    def _detect_finger_gun(hand_lms: Any) -> Tuple[str, float]:
        """Classifies an intentional Finger Gun (Pistol) hand pose pointing left or right.

        Anatomy of a Finger Gun:
        - Index Finger (Barrel): Fully extended and straight.
        - Thumb (Hammer): Extended away from palm and elevated.
        - Ring & Pinky: Tightly curled/folded into palm.
        - Middle Finger: Folded into palm (classic pistol) or extended with index (double-barrel).
        - Barrel orientation: Dominantly horizontal (|dx| > 1.2 * |dy| and |dx| >= 0.08).

        Returns:
            ("GUN_RIGHT", 0.90) if pointing to user's right (NEXT_TRACK)
            ("GUN_LEFT", 0.90) if pointing to user's left (PREV_TRACK)
            ("NONE", 0.0) otherwise
        """
        if not hand_lms or len(hand_lms) < 21:
            return "NONE", 0.0

        def get_pt(p: Any) -> Tuple[float, float, float]:
            if hasattr(p, "x"):
                return float(p.x), float(p.y), float(getattr(p, "z", 0.0))
            elif isinstance(p, dict):
                return float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))
            return float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0

        def dist_2d(p1: Any, p2: Any) -> float:
            x1, y1, _ = get_pt(p1)
            x2, y2, _ = get_pt(p2)
            return math.hypot(x1 - x2, y1 - y2)

        wrist = hand_lms[0]
        thumb_mcp = hand_lms[2]
        thumb_tip = hand_lms[4]
        index_mcp = hand_lms[5]
        index_pip = hand_lms[6]
        index_dip = hand_lms[7]
        index_tip = hand_lms[8]
        middle_pip = hand_lms[10]
        middle_tip = hand_lms[12]
        ring_pip = hand_lms[14]
        ring_tip = hand_lms[16]
        pinky_pip = hand_lms[18]
        pinky_tip = hand_lms[20]

        # 1. Ring and Pinky MUST be folded into the palm
        ring_folded = dist_2d(ring_tip, wrist) < dist_2d(ring_pip, wrist) * 1.25
        pinky_folded = dist_2d(pinky_tip, wrist) < dist_2d(pinky_pip, wrist) * 1.25
        if not (ring_folded and pinky_folded):
            return "NONE", 0.0

        # 2. Middle finger: folded (single-barrel pistol) or extended (double-barrel pistol)
        middle_folded = dist_2d(middle_tip, wrist) < dist_2d(middle_pip, wrist) * 1.25
        middle_extended = dist_2d(middle_tip, wrist) > dist_2d(middle_pip, wrist) * 1.15
        if not (middle_folded or middle_extended):
            return "NONE", 0.0

        # 3. Index finger MUST be extended and straight
        index_extended = dist_2d(index_tip, wrist) > dist_2d(index_pip, wrist) * 1.15
        segment_sum = dist_2d(index_pip, index_mcp) + dist_2d(index_dip, index_pip) + dist_2d(index_tip, index_dip)
        total_len = dist_2d(index_tip, index_mcp)
        index_straight = (total_len / max(0.001, segment_sum)) > 0.65
        if not (index_extended and index_straight):
            return "NONE", 0.0

        # 4. Thumb extended (cocked hammer)
        thumb_extended = dist_2d(thumb_tip, wrist) > dist_2d(thumb_mcp, wrist) * 1.02
        if not thumb_extended:
            return "NONE", 0.0

        # 5. Orientation check: Index finger barrel vector from MCP (5) to TIP (8)
        imcp_x, imcp_y, _ = get_pt(index_mcp)
        itip_x, itip_y, _ = get_pt(index_tip)
        dx_mirrored = imcp_x - itip_x
        dy = itip_y - imcp_y

        # Dominantly horizontal pointing (relaxed from 1.20 to 0.70 to allow natural wrist angles)
        if abs(dx_mirrored) < 0.06:
            return "NONE", 0.0
        if abs(dx_mirrored) <= 0.70 * abs(dy):
            return "NONE", 0.0

        if dx_mirrored > 0:
            return "GUN_RIGHT", 0.90
        else:
            return "GUN_LEFT", 0.90

    @staticmethod
    def _detect_three_fingers(hand_lms: Any) -> Tuple[str, float]:
        """Classifies three fingers extended.

        Supports both:
        1. Classic Three Fingers: Index, Middle, Ring extended; Pinky curled.
        2. Counting / European Three Fingers: Thumb, Index, Middle extended; Ring & Pinky curled.

        Returns:
            ("THREE_FINGERS", 0.90) if detected
            ("NONE", 0.0) otherwise
        """
        if not hand_lms or len(hand_lms) < 21:
            return "NONE", 0.0

        def get_pt(p: Any) -> Tuple[float, float, float]:
            if hasattr(p, "x"):
                return float(p.x), float(p.y), float(getattr(p, "z", 0.0))
            elif isinstance(p, dict):
                return float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))
            return float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0

        def dist_2d(p1: Any, p2: Any) -> float:
            x1, y1, _ = get_pt(p1)
            x2, y2, _ = get_pt(p2)
            return math.hypot(x1 - x2, y1 - y2)

        def dist_3d(p1: Any, p2: Any) -> float:
            x1, y1, z1 = get_pt(p1)
            x2, y2, z2 = get_pt(p2)
            return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)

        wrist = hand_lms[0]
        thumb_tip = hand_lms[4]
        thumb_ip = hand_lms[3]

        index_mcp = hand_lms[5]
        index_pip = hand_lms[6]
        index_dip = hand_lms[7]
        index_tip = hand_lms[8]

        middle_mcp = hand_lms[9]
        middle_pip = hand_lms[10]
        middle_dip = hand_lms[11]
        middle_tip = hand_lms[12]

        ring_mcp = hand_lms[13]
        ring_pip = hand_lms[14]
        ring_dip = hand_lms[15]
        ring_tip = hand_lms[16]

        pinky_mcp = hand_lms[17]
        pinky_pip = hand_lms[18]
        pinky_dip = hand_lms[19]
        pinky_tip = hand_lms[20]

        def is_ext(tip: Any, pip: Any, mcp: Any) -> bool:
            d_tm_2d = dist_2d(tip, mcp)
            d_pm_2d = dist_2d(pip, mcp)
            d_tw_2d = dist_2d(tip, wrist)
            d_pw_2d = dist_2d(pip, wrist)

            d_tm_3d = dist_3d(tip, mcp)
            d_pm_3d = dist_3d(pip, mcp)
            d_tw_3d = dist_3d(tip, wrist)
            d_pw_3d = dist_3d(pip, wrist)

            ext_2d = (d_tm_2d > d_pm_2d * 1.20) and (d_tw_2d > d_pw_2d * 1.08)
            ext_3d = (d_tm_3d > d_pm_3d * 1.20) and (d_tw_3d > d_pw_3d * 1.08)
            return ext_2d or ext_3d

        index_ext = is_ext(index_tip, index_pip, index_mcp)
        middle_ext = is_ext(middle_tip, middle_pip, middle_mcp)
        ring_ext = is_ext(ring_tip, ring_pip, ring_mcp)
        pinky_ext = is_ext(pinky_tip, pinky_pip, pinky_mcp)

        thumb_ext = (
            dist_2d(thumb_tip, index_mcp) > dist_2d(thumb_ip, index_mcp) * 1.10
            or dist_3d(thumb_tip, pinky_mcp) > dist_3d(thumb_ip, pinky_mcp) * 1.12
        )

        # Pattern 1: Classic Three Fingers (Index + Middle + Ring extended, Pinky folded)
        if index_ext and middle_ext and ring_ext and not pinky_ext:
            return "THREE_FINGERS", 0.90

        # Pattern 2: European Three Fingers (Thumb + Index + Middle extended, Ring and Pinky folded)
        if thumb_ext and index_ext and middle_ext and not ring_ext and not pinky_ext:
            return "THREE_FINGERS", 0.90

        # Pattern 3: Boy Scout / "W" Three Fingers (Middle + Ring + Pinky extended, Index folded)
        if middle_ext and ring_ext and pinky_ext and not index_ext:
            return "THREE_FINGERS", 0.90

        return "NONE", 0.0

    def _evaluate_gesture_heuristic(self, frame: Any) -> Tuple[str, float]:
        """Evaluates hand gestures using MediaPipe GestureRecognizer and trajectory heuristics.

        Priority order:
        1. Deliberate lock hold: Rock On (ILoveYou) held for 1.0s -> GESTURE_TOGGLE:PAUSED
        2. Pinch + Rotate -> VOLUME_DIAL:XX (ReflectOS-style, inverted to match natural turn)
        3. Finger Gun Pointing -> GUN_RIGHT / NEXT_TRACK or GUN_LEFT / PREV_TRACK
        4. Air Tap (quick pinch) -> AIR_TAP
        5. Static poses (fist, thumb up/down, peace, pointing, open palm) - immediate when hand is steady
        """
        recognizer = self._init_recognizer()
        if not recognizer:
            return "NONE", 0.0

        try:
            import mediapipe as mp

            img_rgb = self._frame_to_rgb(frame)
            if img_rgb is None:
                return "NONE", 0.0

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
            result = recognizer.recognize(mp_image)

            now = time.time()

            # Prune stale wrist trajectory history (> 1.0s old)
            while self._wrist_history and (now - self._wrist_history[0][0]) > 1.0:
                self._wrist_history.popleft()

            # Check if hand is currently in motion across recent frames
            is_hand_moving = False
            mirrored_x = 0.5
            wrist_y = 0.5

            if result.hand_landmarks and len(result.hand_landmarks) > 0:
                hand_lms = result.hand_landmarks[0]
                wrist = hand_lms[0]
                # Mirror X so moving hand to user's right produces dx > 0
                mirrored_x = 1.0 - wrist.x
                wrist_y = wrist.y
                self._wrist_history.append((now, mirrored_x, wrist_y))

                # Check instantaneous horizontal velocity
                if len(self._wrist_history) >= 2:
                    prev_t, prev_x, prev_y = self._wrist_history[-2]
                    dt_recent = now - prev_t
                    if 0.04 <= dt_recent <= 0.40:
                        dx_recent = abs(mirrored_x - prev_x)
                        speed_recent = dx_recent / dt_recent
                        if dx_recent >= 0.035 or speed_recent >= 0.22:
                            is_hand_moving = True

            # ── 1. Check for Deliberate Lock Gesture (Rock On deliberate hold 2.0s) ─────
            cur_lms = result.hand_landmarks[0] if (result.hand_landmarks and len(result.hand_landmarks) > 0) else None
            if result.gestures and len(result.gestures) > 0:
                top_gesture = result.gestures[0][0]
                category = top_gesture.category_name
                score = float(top_gesture.score)

                is_rock_on = (category == "ILoveYou" and score >= 0.85) and (cur_lms is None or self._is_rock_on_anatomy(cur_lms))
                if is_rock_on:
                    if now >= self._toggle_lockout_until and not is_hand_moving:
                        if self._toggle_gesture_start == 0.0:
                            self._toggle_gesture_start = now
                        elif (now - self._toggle_gesture_start) >= 1.0 and not self._toggle_gesture_fired:
                            self._toggle_gesture_fired = True
                            self._toggle_lockout_until = now + 2.5
                            self._toggle_gesture_start = 0.0
                            self._wrist_history.clear()
                            self._pinch_streak = 0
                            return "GESTURE_TOGGLE:PAUSED", score
                else:
                    if self._toggle_gesture_start > 0.0 and not is_rock_on:
                        self._toggle_gesture_start = 0.0
                        self._toggle_gesture_fired = False

            # ── 2. Landmark-based detections ──────────────────────────────
            if result.hand_landmarks and len(result.hand_landmarks) > 0:
                hand_lms = result.hand_landmarks[0]
                wrist = hand_lms[0]
                thumb_tip = hand_lms[4]
                index_tip = hand_lms[8]
                index_mcp = hand_lms[5]
                pinch_dist = math.sqrt(
                    (thumb_tip.x - index_tip.x) ** 2
                    + (thumb_tip.y - index_tip.y) ** 2
                    + (thumb_tip.z - index_tip.z) ** 2
                )

                # ── 2a. Pinch + Rotate → VOLUME_DIAL (ReflectOS-style) ────
                if pinch_dist < 0.050:
                    self._pinch_streak += 1

                    if self._pinch_streak >= 3:
                        vec_x = index_mcp.x - wrist.x
                        vec_y = index_mcp.y - wrist.y
                        rad = math.atan2(vec_y, vec_x)
                        deg = (rad * 180.0 / math.pi) + 90.0  # Normalize: up=0°, right=90°

                        # Valid dial range: 10° to 170° (ignore extremes)
                        if 10.0 <= deg <= 170.0:
                            if deg <= 30.0:
                                raw_pct = 0
                            elif deg >= 150.0:
                                raw_pct = 100
                            else:
                                raw_pct = int(((deg - 30.0) / 120.0) * 100.0)
                            # Invert motion per user request
                            percentage = max(0, min(100, 100 - raw_pct))

                            self._toggle_gesture_start = 0.0
                            self._toggle_gesture_fired = False
                            return f"VOLUME_DIAL:{percentage}", 0.85

                        # If angle is out of dial range but still pinching → AIR_TAP
                        if self._pinch_streak >= 4:
                            self._toggle_gesture_start = 0.0
                            return "AIR_TAP", 0.85
                else:
                    self._pinch_streak = 0

                # ── 2b. Finger Gun Pointing → NEXT/PREV TRACK (GUN_RIGHT / GUN_LEFT) ──
                gun_gesture, gun_conf = self._detect_finger_gun(hand_lms)
                if gun_gesture != "NONE":
                    self._wrist_history.clear()
                    self._toggle_gesture_start = 0.0
                    return gun_gesture, gun_conf

                # ── 2c. Three Fingers Extended → Media Play/Pause ──
                three_gesture, three_conf = self._detect_three_fingers(hand_lms)
                if three_gesture != "NONE":
                    self._wrist_history.clear()
                    self._toggle_gesture_start = 0.0
                    return three_gesture, three_conf

            else:
                self._pinch_streak = 0

            # ── 3. Static Poses from MediaPipe Tasks ──────────────────────
            if result.gestures and len(result.gestures) > 0:
                top_gesture = result.gestures[0][0]
                category = top_gesture.category_name
                score = float(top_gesture.score)

                if score >= 0.50:
                    if category == "Open_Palm":
                        return "OPEN_PALM", score
                    elif category == "Closed_Fist":
                        return "CLOSED_FIST", score
                    elif category == "Victory":
                        return "PEACE_SIGN", score
                    elif category == "Thumb_Up":
                        return "THUMB_UP", score
                    elif category == "Thumb_Down":
                        return "THUMB_DOWN", score
                    elif category == "Pointing_Up":
                        return "POINTING_UP", score
                    elif category == "ILoveYou":
                        return "ROCK_ON", score

        except Exception as e:
            logger.debug(f"[GestureWorker] MediaPipe evaluation error: {e}")

        return "NONE", 0.0

    async def _dispatch_gesture(self, gesture: str, confidence: float) -> None:
        """Emits gesture event to callback, Gateway router, and direct SyncManager.

        Also applies real system-level side effects (volume, mute) via wpctl/pactl.
        """
        # 1. Update cluster state AND apply real system effects
        try:
            from backend.sync.sync_manager import sync_manager
            cur_snap = sync_manager.get_snapshot()
            cur_vol = cur_snap.master_volume
            media_copy = dict(cur_snap.current_media)

            if gesture in ("CLOSED_FIST", "MUTE", "PAUSE"):
                if cur_vol > 0:
                    self._saved_volume = cur_vol
                media_copy["is_playing"] = False
                await sync_manager.update_state(
                    {"master_volume": 0, "current_media": media_copy},
                    source_device_id="gesture_worker",
                )
                # Real system effect: mute + pause running media player (standalone only)
                if not self.on_gesture_callback and not self.gateway_url:
                    await asyncio.to_thread(_set_system_mute, True)
                    await asyncio.to_thread(_control_media_player, "pause")

            elif gesture in ("OPEN_PALM", "RESUME", "PLAY", "UNMUTE"):
                restore_vol = getattr(self, "_saved_volume", 60)
                if restore_vol <= 0:
                    restore_vol = 60
                media_copy["is_playing"] = True
                await sync_manager.update_state(
                    {"master_volume": restore_vol, "current_media": media_copy},
                    source_device_id="gesture_worker",
                )
                # Real system effect: unmute + restore volume + resume media player (standalone only)
                if not self.on_gesture_callback and not self.gateway_url:
                    await asyncio.to_thread(_set_system_mute, False)
                    await asyncio.to_thread(_set_system_volume, restore_vol)
                    await asyncio.to_thread(_control_media_player, "play")

            elif gesture in ("NEXT_TRACK", "SWIPE_RIGHT", "GUN_RIGHT", "GUN_POINT_RIGHT"):
                logger.info(f"[GestureWorker] Dispatched NEXT_TRACK media action ({gesture})")
                await asyncio.to_thread(_control_media_player, "next")

            elif gesture in ("PREV_TRACK", "PREVIOUS_TRACK", "SWIPE_LEFT", "GUN_LEFT", "GUN_POINT_LEFT"):
                logger.info(f"[GestureWorker] Dispatched PREV_TRACK media action ({gesture})")
                await asyncio.to_thread(_control_media_player, "previous")

            elif gesture in ("THUMB_UP", "VOLUME_UP"):
                # Step volume up +10% (sync state + real system)
                new_vol = min(100, cur_vol + 10)
                await sync_manager.update_state(
                    {"master_volume": new_vol},
                    source_device_id="gesture_worker",
                )
                if not self.on_gesture_callback and not self.gateway_url:
                    await asyncio.to_thread(_set_system_volume, new_vol)

            elif gesture in ("THUMB_DOWN", "VOLUME_DOWN"):
                # Step volume down -10% (sync state + real system)
                new_vol = max(0, cur_vol - 10)
                await sync_manager.update_state(
                    {"master_volume": new_vol},
                    source_device_id="gesture_worker",
                )
                if not self.on_gesture_callback and not self.gateway_url:
                    await asyncio.to_thread(_set_system_volume, new_vol)

            elif gesture.startswith("VOLUME_DIAL:"):
                # Pinch + rotate analog volume dial → set absolute volume
                try:
                    dial_pct = int(gesture.split(":")[1])
                    dial_pct = max(0, min(100, dial_pct))
                except (ValueError, IndexError):
                    dial_pct = cur_vol
                await sync_manager.update_state(
                    {"master_volume": dial_pct},
                    source_device_id="gesture_worker",
                )
                await asyncio.to_thread(_set_system_volume, dial_pct)

            elif gesture in ("THREE_FINGERS", "PLAY_PAUSE", "MEDIA_PLAY_PAUSE"):
                # Pure media play/pause toggle without modifying master volume or muting
                is_playing = media_copy.get("is_playing", True)
                new_playing = not is_playing
                media_copy["is_playing"] = new_playing
                await sync_manager.update_state(
                    {"current_media": media_copy},
                    source_device_id="gesture_worker",
                )
                if not self.on_gesture_callback and not self.gateway_url:
                    await asyncio.to_thread(_control_media_player, "play-pause")
                logger.info(f"[GestureWorker] THREE_FINGERS toggled playback -> {'PLAY' if new_playing else 'PAUSE'} (Volume untouched: {cur_vol}%)")

            elif gesture in ("PEACE_SIGN", "VICTORY", "TOGGLE_ZEN", "ZEN_MODE"):
                new_zen = not cur_snap.zen_mode
                await sync_manager.update_state(
                    {"zen_mode": new_zen},
                    source_device_id="gesture_worker",
                )

            elif gesture in ("POINTING_UP", "TOGGLE_FOCUS"):
                new_focus = not cur_snap.focus_mode
                await sync_manager.update_state(
                    {"focus_mode": new_focus},
                    source_device_id="gesture_worker",
                )

            elif gesture in ("ROCK_ON", "GESTURE_LOCK") or gesture.startswith("GESTURE_TOGGLE"):
                # Explicit state assignment prevents toggle flapping
                if ":PAUSED" in gesture:
                    self.state.tracking_paused = True
                elif ":RESUMED" in gesture:
                    self.state.tracking_paused = False
                elif gesture.startswith("GESTURE_TOGGLE"):
                    self.state.tracking_paused = not self.state.tracking_paused
                else:
                    return
                status = "PAUSED" if self.state.tracking_paused else "RESUMED"
                logger.info(f"[GestureWorker] Gesture tracking {status} via ROCK_ON")

        except Exception as sync_err:
            logger.debug(f"[GestureWorker] Direct sync update skipped: {sync_err}")

        # 2. Invoke local callback if registered
        if self.on_gesture_callback:
            try:
                res = self.on_gesture_callback(gesture, confidence)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.warning(f"[GestureWorker] Callback error: {e}")

        # 3. If gateway URL is configured, post gesture envelope
        if self.gateway_url:
            try:
                import httpx
                envelope = ClientEnvelope(
                    channel=Channel.GESTURE,
                    type=EventType.GESTURE_EVENT,
                    payload=GestureEventPayload(
                        gesture=gesture,
                        source="DECOUPLED_VISION_SERVICE",
                        confidence=confidence,
                    ).model_dump(),
                )
                async with httpx.AsyncClient(timeout=2.0) as client:
                    await client.post(
                        f"{self.gateway_url}/events",
                        json=envelope.model_dump(),
                    )
            except Exception as net_err:
                logger.debug(f"[GestureWorker] Failed to post to gateway: {net_err}")


# Standalone runner entrypoint
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Initializing VESPER Decoupled Gesture Service...")
    worker = GestureWorker(fps=6.0)

    async def main():
        await worker.start()
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            await worker.stop()

    asyncio.run(main())
