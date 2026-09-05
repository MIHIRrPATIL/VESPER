# Touchless Gesture Perception & Control Architecture

This document details how touchless gestures are captured, evaluated, dispatched, and synchronized across VESPER's distributed system.

---

## 1. High-Level Architectural Overview

In smart desk companions, continuous computer vision pipelines (e.g., 60 FPS hand tracking) can easily saturate CPU and GPU resources, causing audio stuttering or UI frame drops.

VESPER solves this with a **bifurcated, decoupled architecture**:

```
 ┌────────────────────────────────────────────────────────────┐
 │                  Client-Side HUD (Tauri v2)                │
 │  • MediaPipe GestureRecognizer inside Web Worker           │
 │  • Zero main-thread UI jank (UI remains at 60 FPS)         │
 └─────────────────────────────┬──────────────────────────────┘
                               │
                               │ Channel.GESTURE (WebSocket)
                               ▼
 ┌────────────────────────────────────────────────────────────┐
 │                 FastAPI Gateway (`/ws`)                    │
 │  • `_handle_gesture` in `backend/gateway/router.py`        │
 │  • State Sync update in `backend/sync/sync_manager.py`     │
 │  • Real-time broadcast to all connected nodes & HUDs       │
 └─────────────────────────────▲──────────────────────────────┘
                               │
                               │ Channel.GESTURE (POST /events)
 ┌─────────────────────────────┴──────────────────────────────┐
 │             Backend Decoupled `GestureWorker`              │
 │  • `backend/vision/gesture_service.py`                     │
 │  • Throttled sampling at 5–8 FPS (~80% CPU reduction)      │
 │  • Automatic 0% CPU standby on camera-less SBC nodes       │
 └────────────────────────────────────────────────────────────┘
```

---

## 2. Gesture Vocabulary & Action Mapping

VESPER supports an expanded, touchless gesture vocabulary designed for immediate ambient desk interaction without needing to speak a wake word:

| Gesture | Meaning / Intent | Gateway Event Broadcast | Hardware & Cluster State Impact |
| :--- | :--- | :--- | :--- |
| **`CLOSED_FIST`** | **Instant Mute / Pause** | `Channel.SYSTEM` : `SET_VOLUME` (`volume=0, muted=True, media_action="pause"`) | `sync_manager.update_state({"master_volume": 0})`, sets system mute via `wpctl`/`pactl`, pauses media via `playerctl pause` |
| **`OPEN_PALM`** | **Resume / Play / Unmute** | `Channel.SYSTEM` : `SET_VOLUME` (`volume=restore_vol, muted=False, media_action="play"`) | Immediate trigger (no hold delay). Unmutes system volume, restores volume level, resumes media playback via `playerctl play` |
| **`SWIPE_RIGHT` / `NEXT_TRACK`** | **Next Media Track** | `Channel.GESTURE` : `NEXT_TRACK` | Mirrored X displacement tracking; dispatches `playerctl next` |
| **`SWIPE_LEFT` / `PREV_TRACK`** | **Previous Media Track** | `Channel.GESTURE` : `PREV_TRACK` | Mirrored X displacement tracking; dispatches `playerctl previous` |
| **`VOLUME_DIAL:<0-100>`** | **Analog Volume Dial** | `Channel.SYSTEM` : `SET_VOLUME` (`volume=percentage`) | Pinch thumb & index, rotate hand (10°–170°) with natural intuitive orientation to set master volume |
| **`THUMB_UP`** | **Volume Up (+10%)** | `Channel.SYSTEM` : `SET_VOLUME` (`volume=cur+10`) | Increments system master volume by +10% |
| **`THUMB_DOWN`** | **Volume Down (-10%)** | `Channel.SYSTEM` : `SET_VOLUME` (`volume=cur-10`) | Decrements system master volume by -10% |
| **`PEACE_SIGN`** | **Toggle Zen Mode** | `Channel.SYSTEM` : `ZEN_MODE_STATE` (`toggle=True`) | Toggles ambient distraction-free Zen Mode across the cluster |
| **`POINTING_UP`** | **Toggle Focus Mode** | `Channel.SYSTEM` : `FOCUS_MODE_STATE` (`toggle=True`) | Toggles high-productivity Focus Mode across the cluster |
| **`ROCK_ON` (`ILoveYou`)** | **Lock / Unlock Gesture Tracking** | `Channel.GESTURE` : `GESTURE_TOGGLE` (`:PAUSED` / `:RESUMED`) | Deliberate hold for 1.0s locks or unlocks gesture tracking with a 2.0s anti-flapping buffer |
| **`AIR_TAP`** | **Select / Activate Widget** | `Channel.GESTURE` : `AIR_TAP` | Quick pinch tap in the air for desk UI interaction |

---

## 3. Perception Layers

### 3.1 Client-Side Perception (Desktop HUD Web Worker)
- **Host**: Tauri v2 desktop application ([`desktop/`](file:///home/mihir/Codes/VESPER/desktop/)).
- **Mechanism**: Spawns an isolated HTML5 Web Worker hosting MediaPipe's `@mediapipe/tasks-vision` `GestureRecognizer`.
- **Advantages**:
  - Processing occurs in the client browser runtime without burdening the Python backend.
  - Video stream stays on the local GPU canvas / worker thread, maintaining a 60 FPS desktop HUD.
  - Upon landmark classification, the Web Worker emits a JSON envelope over the established WebSocket connection to `/ws`.

### 3.2 Backend Perception (`GestureWorker`)
- **Host**: [`backend/vision/gesture_service.py`](file:///home/mihir/Codes/VESPER/backend/vision/gesture_service.py).
- **Sampling Frequency**: Runs at a throttled **5–8 FPS** (interval: ~166ms). Continuous 60 FPS optical capture is intentionally avoided to conserve CPU cycles for voice STT and swarm planning.
- **Hardware Awareness & Zero-CPU Standby**:
  Before each capture cycle, `DeviceProbe.get_capabilities()` checks for camera availability:
  ```python
  caps = DeviceProbe.get_capabilities()
  if not caps.has_camera:
      self.state.camera_available = False
      # Idle in zero-CPU standby mode
      await asyncio.sleep(5.0)
      continue
  ```
  If running on a camera-less edge node (e.g., headless Orange Pi), the worker sleeps with 0% CPU consumption.
- **Off-Thread Frame Capture**: Optical frames are captured using `asyncio.to_thread(CameraCapture.capture_frame, 0)` so the async event loop never blocks.

---

## 4. Transmission Protocol & Event Envelopes

Gestures communicate through the universal typed event envelope over channel `Channel.GESTURE`:

### Client $\to$ Gateway Envelope
```json
{
  "uuid": "g-01-a1b2c3d4",
  "channel": "GESTURE",
  "type": "GESTURE_EVENT",
  "timestamp": 1788438900.123,
  "payload": {
    "gesture": "CLOSED_FIST",
    "source": "CLIENT_WEB_WORKER",
    "confidence": 0.88
  }
}
```

### Gateway $\to$ Cluster Broadcast Envelopes
Upon receiving a valid gesture, the Gateway translates it into a system event broadcast to all connected devices (Desk HUD, mobile app, edge nodes):

#### 1. Volume / Mute Event (`EventType.SET_VOLUME`):
```json
{
  "uuid": "g-01-a1b2c3d4",
  "channel": "SYSTEM",
  "type": "SET_VOLUME",
  "payload": {
    "volume": 0,
    "muted": true,
    "media_action": "pause"
  }
}
```

#### 2. Zen Mode State Event (`EventType.ZEN_MODE_STATE`):
```json
{
  "uuid": "g-01-a1b2c3d4",
  "channel": "SYSTEM",
  "type": "ZEN_MODE_STATE",
  "payload": {
    "toggle": true,
    "zen_mode": true
  }
}
```

---

## 5. False-Positive Suppression & Debounce Mechanics

Hand tracking is susceptible to jitter and flicker when moving hands across the camera frame. The following filters are enforced:

1. **Confidence Threshold Gating**:
   Static poses require `confidence >= 0.50` (or 0.55 for edge poses).
2. **Candidate Streak Requirement**:
   A detected pose must persist for at least $N = 2$ consecutive frames before being considered valid. Single-frame blips and transient hand transitions are discarded.
3. **Release Requirement & Hysteresis Lock (`_gesture_awaiting_release`)**:
   Non-volume gestures (`CLOSED_FIST`, `PEACE_SIGN`, `POINTING_UP`, `ROCK_ON`, `AIR_TAP`) cannot be triggered repeatedly without releasing the hand back to `NONE`. Once emitted, the gesture is placed in `_gesture_awaiting_release`, preventing repetitive firing while the user holds their hand steady.
4. **Volume Repeat Exception**:
   Volume adjustment gestures (`THUMB_UP`, `THUMB_DOWN`, `VOLUME_DIAL`) bypass the release requirement to enable continuous, smooth volume ramping across frames with a shortened 0.35s throttle.
5. **Continuous Volume Dial Tracking**:
   When the thumb tip and index tip pinch together, hand rotation angle (10° to 170°) is mapped linearly to master volume percentage $[0, 100]\%$. Throttles emissions if the dial value has not changed.
6. **Horizontal Velocity Motion Gating (`is_hand_moving`)**:
   When the user's hand is in active lateral motion across frames ($\Delta x \ge 0.035$ or speed $\ge 0.22$), static pose emissions (`OPEN_PALM` and `CLOSED_FIST`) are strictly suppressed. This ensures that swiping left or right never accidentally mutes or resumes playback.
7. **Mirrored Coordinate Geometry**:
   The camera X axis is mirrored (`mirrored_x = 1.0 - wrist.x`) so that moving the physical hand to the user's right produces $\Delta x > 0$ (`NEXT_TRACK`), and moving to the user's left produces $\Delta x < 0$ (`PREV_TRACK`).
8. **Deliberate Lock Toggle (Rock On / `ILoveYou`)**:
   Holding Rock On for 1.0s toggles gesture tracking on or off (`GESTURE_TOGGLE:PAUSED` / `GESTURE_TOGGLE:RESUMED`). A 2.5-second lockout window (`_toggle_lockout_until`) prevents toggle flapping while holding the hand steady.
9. **Zero-CPU Standby & Privacy Hardware Release**:
   On headless SBCs or nodes without optical sensors, the worker enters zero-CPU standby (`asyncio.sleep(5.0)`). When gestures are disabled or cameras are idle, the OpenCV video capture device is immediately released (`cap.release()`), turning off the camera privacy LED.
10. **Real Hardware Player Control (`playerctl`)**:
   Gesture events interface directly with running Linux media sessions via `/usr/bin/playerctl` (`play`, `pause`, `next`, `previous`), controlling Spotify, VLC, and browser tabs with zero desktop UI latency.

---

## 6. Verification & Automated Testing

The gesture perception suite is covered by automated unit tests in [`backend/tests/test_vision.py`](file:///home/mihir/Codes/VESPER/backend/tests/test_vision.py) and [`backend/tests/test_gateway.py`](file:///home/mihir/Codes/VESPER/backend/tests/test_gateway.py):

- `test_gesture_rock_on_lock_toggle_and_open_palm_immediate`: Validates instantaneous `OPEN_PALM` triggers without hold delay, `ILoveYou` 1.0s hold lock/unlock, and paused state resume.
- `test_gesture_worker_toggle_lockout_and_swipes`: Validates lockout suppression and trajectory calculation for mirrored swipes.
- `test_gesture_worker_lifecycle_and_dispatch`: Validates real-time side-effects for mute, volume dial, peace sign (Zen), thumb up/down, and `GESTURE_TOGGLE`.
- `test_gesture_broadcast_closed_fist_and_open_palm`: Validates Gateway WebSocket broadcasting and cluster state sync.
- `test_gesture_repeat_guard_and_volume_repeat_exception`: Validates that non-volume gestures are blocked until hand release, while volume gestures smoothly repeat.
