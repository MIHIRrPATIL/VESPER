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
   - NEXT_TRACK / SWIPE_RIGHT: Skip to Next Media Track
   - PREV_TRACK / SWIPE_LEFT: Return to Previous Media Track
   - PEACE_SIGN: Toggle Ambient Zen Mode
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
import time
from pathlib import Path
from typing import Any, Callable, Deque, Optional, Tuple
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
    """Sets the real system audio volume via wpctl (PipeWire) or pactl (PulseAudio)."""
    percent = max(0, min(100, percent))
    frac = percent / 100.0
    try:
        wpctl = shutil.which("wpctl")
        if wpctl:
            subprocess.run(
                [wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", f"{frac:.2f}"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        pactl = shutil.which("pactl")
        if pactl:
            subprocess.run(
                [pactl, "set-sink-volume", "@DEFAULT_SINK", f"{percent}%"],
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
        logger.debug(f"[VolumeCtrl] Failed to set system volume: {e}")


def _get_system_volume() -> int:
    """Reads the current real system volume (0-100)."""
    try:
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
    except Exception:
        pass
    return 60


def _set_system_mute(muted: bool) -> None:
    """Mutes or unmutes the system audio sink."""
    try:
        wpctl = shutil.which("wpctl")
        if wpctl:
            subprocess.run(
                [wpctl, "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if muted else "0"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        pactl = shutil.which("pactl")
        if pactl:
            subprocess.run(
                [pactl, "set-sink-mute", "@DEFAULT_SINK", "1" if muted else "0"],
                timeout=2, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        logger.debug(f"[VolumeCtrl] Failed to set mute: {e}")


def _control_media_player(action: str) -> None:
    """Controls running media players (Spotify, browsers, MPRIS) via playerctl."""
    playerctl = shutil.which("playerctl")
    if not playerctl:
        return
    try:
        subprocess.run(
            [playerctl, action],
            timeout=2, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.debug(f"[MediaCtrl] playerctl {action} failed: {e}")


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

        # Deliberate lock tracking (Rock On 🤟 / ILoveYou hold 1.0s)
        self._toggle_gesture_start: float = 0.0
        self._toggle_gesture_fired: bool = False
        self._toggle_lockout_until: float = 0.0
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
                        logger.warning(f"[GestureWorker] Failed to open camera index {desired_camera_idx}.")
                        cap = None
                        await asyncio.sleep(2.0)
                        continue
                    try:
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    except Exception:
                        pass
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

                # 2. Acquire raw frame directly from open device
                try:
                    def _read_frame(c):
                        return c.read()

                    ret, frame_bgr = await asyncio.to_thread(_read_frame, cap)
                    if not ret or frame_bgr is None:
                        await asyncio.sleep(self.interval)
                        continue

                    # If tracking is paused, still read frames (keep camera warm)
                    # but only look for the deliberate lock toggle (Rock On 🤟 hold 1.0s) to re-enable
                    if self.state.tracking_paused:
                        toggle_gesture, toggle_conf = self._check_toggle_gesture_only(frame_bgr)
                        if toggle_gesture.startswith("GESTURE_TOGGLE"):
                            self.state.tracking_paused = False
                            self._toggle_gesture_start = 0.0
                            self._toggle_gesture_fired = False
                            self._open_palm_start = 0.0
                            self._open_palm_toggle_fired = False
                            logger.info("[GestureWorker] Tracking RESUMED via Rock On 🤟 hold")
                            await self._dispatch_gesture("GESTURE_TOGGLE:RESUMED", toggle_conf)
                        await asyncio.sleep(self.interval)
                        continue

                    # 3. Detect gesture from numpy array
                    detected_gesture, confidence = self._evaluate_gesture_heuristic(frame_bgr)

                    now = time.time()
                    if detected_gesture != "NONE" and confidence >= 0.50:
                        # Volume dial gets faster cooldown for smooth feel
                        is_volume_dial = detected_gesture.startswith("VOLUME_DIAL:")
                        effective_cooldown = volume_dial_cooldown if is_volume_dial else cooldown_sec

                        if detected_gesture != last_emitted_gesture or (now - last_emit_time) > effective_cooldown:
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

                            last_emitted_gesture = detected_gesture
                            last_emit_time = now
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
        """When tracking is paused, only check for deliberate lock gesture (Rock On 🤟) to resume."""
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

            if result.gestures and len(result.gestures) > 0:
                top = result.gestures[0][0]
                category = top.category_name
                score = float(top.score)
                # Rock On (ILoveYou 🤟) held for 1.0s toggles gesture lock state
                if category == "ILoveYou" and score >= 0.50:
                    if self._toggle_gesture_start == 0.0:
                        self._toggle_gesture_start = now
                    elif (now - self._toggle_gesture_start) >= 1.0 and not self._toggle_gesture_fired:
                        self._toggle_gesture_fired = True
                        self._toggle_lockout_until = now + 2.0
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

    def _evaluate_gesture_heuristic(self, frame: Any) -> Tuple[str, float]:
        """Evaluates hand gestures using MediaPipe GestureRecognizer and trajectory heuristics.

        Priority order:
        1. Deliberate lock hold: Rock On (ILoveYou 🤟) held for 1.0s -> GESTURE_TOGGLE:PAUSED
        2. Pinch + Rotate -> VOLUME_DIAL:XX (ReflectOS-style, inverted to match natural turn)
        3. Horizontal swipe -> NEXT_TRACK / PREV_TRACK (mirrored, suppresses static play/pause while moving)
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

            # ── 1. Check for Deliberate Lock Gesture (Rock On 🤟 hold 1.0s) ─────
            if result.gestures and len(result.gestures) > 0:
                top_gesture = result.gestures[0][0]
                category = top_gesture.category_name
                score = float(top_gesture.score)

                if category == "ILoveYou" and score >= 0.50:
                    if now >= self._toggle_lockout_until and not is_hand_moving:
                        if self._toggle_gesture_start == 0.0:
                            self._toggle_gesture_start = now
                        elif (now - self._toggle_gesture_start) >= 1.0 and not self._toggle_gesture_fired:
                            self._toggle_gesture_fired = True
                            self._toggle_lockout_until = now + 2.0
                            self._wrist_history.clear()
                            self._pinch_streak = 0
                            return "GESTURE_TOGGLE:PAUSED", score
                else:
                    if self._toggle_gesture_start > 0.0 and category != "ILoveYou":
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

                # ── 2b. Horizontal Swipe Trajectory → NEXT/PREV TRACK ─────
                # Evaluates displacement across recent wrist points
                if len(self._wrist_history) >= 2:
                    for past_t, past_x, past_y in list(self._wrist_history)[:-1]:
                        dt = now - past_t
                        if 0.08 <= dt <= 0.85:
                            dx = mirrored_x - past_x
                            dy = wrist_y - past_y
                            if abs(dx) >= 0.06 and abs(dx) > 1.20 * abs(dy):
                                self._wrist_history.clear()
                                self._toggle_gesture_start = 0.0
                                gesture = "NEXT_TRACK" if dx > 0 else "PREV_TRACK"
                                return gesture, 0.88

            else:
                self._pinch_streak = 0

            # ── 3. Static Poses from MediaPipe Tasks ──────────────────────
            if result.gestures and len(result.gestures) > 0:
                top_gesture = result.gestures[0][0]
                category = top_gesture.category_name
                score = float(top_gesture.score)

                if score >= 0.50:
                    # If hand is in active horizontal motion (swiping), suppress static play/mute poses!
                    if is_hand_moving and category in ("Open_Palm", "Closed_Fist"):
                        return "NONE", 0.0

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
                # Real system effect: mute + pause running media player
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
                # Real system effect: unmute + restore volume + resume media player
                await asyncio.to_thread(_set_system_mute, False)
                await asyncio.to_thread(_set_system_volume, restore_vol)
                await asyncio.to_thread(_control_media_player, "play")

            elif gesture in ("NEXT_TRACK", "SWIPE_RIGHT"):
                logger.info("[GestureWorker] Dispatched NEXT_TRACK media action")
                await asyncio.to_thread(_control_media_player, "next")

            elif gesture in ("PREV_TRACK", "PREVIOUS_TRACK", "SWIPE_LEFT"):
                logger.info("[GestureWorker] Dispatched PREV_TRACK media action")
                await asyncio.to_thread(_control_media_player, "previous")

            elif gesture in ("THUMB_UP", "VOLUME_UP"):
                # Step volume up +10% (real system + state)
                sys_vol = _get_system_volume()
                new_vol = min(100, sys_vol + 10)
                await sync_manager.update_state(
                    {"master_volume": new_vol},
                    source_device_id="gesture_worker",
                )
                await asyncio.to_thread(_set_system_volume, new_vol)

            elif gesture in ("THUMB_DOWN", "VOLUME_DOWN"):
                # Step volume down -10% (real system + state)
                sys_vol = _get_system_volume()
                new_vol = max(0, sys_vol - 10)
                await sync_manager.update_state(
                    {"master_volume": new_vol},
                    source_device_id="gesture_worker",
                )
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

            elif gesture in ("PEACE_SIGN", "TOGGLE_ZEN"):
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

            elif gesture.startswith("GESTURE_TOGGLE"):
                # Explicit state assignment prevents toggle flapping
                if ":PAUSED" in gesture:
                    self.state.tracking_paused = True
                elif ":RESUMED" in gesture:
                    self.state.tracking_paused = False
                else:
                    self.state.tracking_paused = not self.state.tracking_paused
                status = "PAUSED" if self.state.tracking_paused else "RESUMED"
                logger.info(f"[GestureWorker] Gesture tracking {status}")

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
