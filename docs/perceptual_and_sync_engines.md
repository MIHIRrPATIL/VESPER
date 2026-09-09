# VESPER Perceptual & Synchronization Engines Reference

This document provides in-depth technical specifications for the sensory and convergence engines of the VESPER ecosystem:
1. **Low-Power Wake Word Engine (`backend/voice/wakeword/`)**
2. **Vision Perception & Decoupled Gestures (`backend/vision/`)**
3. **Cross-Device State Sync Engine (`backend/sync/`)**

---

## 1. Low-Power Wake Word Engine

Located in [`backend/voice/wakeword/`](file:///home/mihir/Codes/VESPER/backend/voice/wakeword/):
Continuous, local, low-latency wake word detection for `"Hey Alfred"` and `"Alfred"`.

### 1.1 Two-Tier Detection Architecture

```
 Audio In (16kHz PCM) ──► [Tier 1: WebRTC VAD]
                                │
               ┌────────────────┴────────────────┐
               │ Silence                         │ Speech Detected
               ▼                                 ▼
      [Drop Frame (<0.1% CPU)]        [Tier 2: Circular Buffer (1.5s)]
                                                 │
                                                 ▼
                                     [Acoustic Model Classifier]
                                                 │
                                                 ▼
                                        Confidence >= 0.6?
                                        ├── Yes ──► Trigger Wake Event
                                        └── No  ──► Continue Listening
```

- **Tier 1 (WebRTC VAD Pre-Gating)**:
  - Audio is framed into 20ms slices (320 samples / 640 bytes at 16kHz 16-bit mono).
  - Evaluated with WebRTC VAD mode `2` (aggressive speech discrimination).
  - In a quiet room, **>98% of frames are dropped before acoustic inference**, keeping background CPU consumption at **<0.5% CPU**.
- **Tier 2 (Acoustic Buffer & Classification)**:
  - When speech is present, frames enter a sliding circular buffer holding up to 1.5 seconds of audio (48,000 bytes).
  - Evaluated against openWakeWord ONNX acoustic templates with robust spectral energy heuristics fallback.

### 1.2 Self-Trigger Protection During TTS Playback

To prevent Alfred from triggering himself while reading a long response aloud:
```python
# Before starting TTS playback:
listener.pause()

# Stream TTS audio to speakers...

# When playback completes or user interrupts:
listener.resume()
```
- `pause()`: Sets internal flag and clears the audio buffer. Any incoming microphone frames during playback are safely ignored.
- `resume()`: Flushes residual audio and re-arms detection immediately.

---

## 2. Vision Perception Suite & Decoupled Gestures

Located in [`backend/vision/`](file:///home/mihir/Codes/VESPER/backend/vision/):
Integrates webcam-first OCR, multimodal VLLM reasoning, screen capture, and touchless gesture tracking.

### 2.1 Hardware Probe & Graceful Edge Degradation (`DeviceProbe`)

SBC edge nodes (such as an Orange Pi or headless micro-server) often run without cameras or display servers attached.
- **Probe Logic** ([`backend/vision/device_probe.py`](file:///home/mihir/Codes/VESPER/backend/vision/device_probe.py)):
  - Inspects `/proc/device-tree/model` and `/sys/class/dmi/id/` to classify device type (`orange_pi`, `raspberry_pi`, `embedded_edge`, `desktop`).
  - Scans `/dev/video*` nodes and tests OpenCV capture availability.
  - Checks graphical display environment (`$DISPLAY`, `$WAYLAND_DISPLAY`).
- **Graceful Butler Degradation (No Crashes)**:
  - If a user asks visual questions on a camera-less node, Alfred returns an articulate butler explanation instead of crashing:
    > *"I am currently operating on an edge node (Orange Pi 5 Plus) with no optical camera sensors detected, sir. If you wish me to analyze objects, documents, or your physical surroundings, please attach a USB optical sensor or relay the visual feed via the companion mobile HUD."*

### 2.2 Webcam-First Perception vs. Screen Perception

- **Webcam-First (Primary)**:
  - Default visual perception actions query the **physical webcam** at `/dev/video0`:
    - `inspect_webcam(query)`: Reads optical frame, encodes Base64 JPEG, and queries Groq Multimodal Vision LPU (`llama-3.2-11b-vision-preview`, 100% free).
    - `ocr_webcam(focus_hint)`: Transcribes physical books, receipts, printed code, and handwritten notes held up to the camera.
- **Screen Perception (Secondary)**:
  - `inspect_screen(query)`: Captures desktop monitor via `mss` / `PIL` when user explicitly asks about their screen, IDE errors, or terminal logs.
  - `ocr_screen(focus_hint)`: Extracts text directly from desktop application windows.

### 2.3 Decoupled Touchless Gesture Perception (`GestureWorker`)

Continuous 60 FPS video tracking can saturate single-board computers. The `GestureWorker` runs decoupled:
- **Throttled Sampling (5–8 FPS)**: Reduces CPU utilization by **~80%** while maintaining responsive gesture latency (~150ms).
- **Zero-CPU Standby**: If `has_camera` is false, the worker idles in a 5-second sleep loop, consuming 0% CPU.
- **Gesture Vocabulary**:
  - `CLOSED_FIST`: Instant Mute / Pause playback.
  - `OPEN_PALM`: Resume playback / Unmute.
  - `VOLUME_DIAL:<level>`: Proportional volume slider.
  - `PEACE_SIGN`: Toggle Zen Mode on desk HUD.
  - `THUMB_UP` / `THUMB_DOWN`: Instant confirm or reject staged proactive recommendations.

### 2.4 Display Sentry & Presence Session Locking (`backend/vision/display_sentry.py`)

The Display Sentry subsystem monitors desk occupancy, enforces session security via Hyprland, and manages display power cycles without interrupting touchless gesture tracking:
- **BlazeFace CPU Presence Detection (`BlazeFaceDetector`)**:
  - Executes offline face detection using Google MediaPipe Tasks API (`blaze_face_short_range.tflite`).
  - Evaluates webcam frames in <5ms entirely on CPU with confidence threshold >= 0.35.
  - Shared V4L2 Device Pipeline: Taps into `GestureService` frames directly, eliminating device contention on `/dev/video0`.
- **Absence Session Locking & DPMS Sleep**:
  - Tracks consecutive absent frames (default threshold: 10 frames / ~15–20s).
  - When user absence is confirmed, spawns `hyprlock` and powers off displays via `hyprctl dispatch dpms off` across all active outputs (`eDP-1`, `DP-3`).
- **Display Wake & Caelestia Shell Recovery**:
  - Displays are powered back on upon return detection, wake word invocation, or any touchless gesture.
  - **DRM Settle Barrier**: Waits 0.8s for kernel DRM/KMS handshaking to complete before querying compositor heads.
  - **Layer Surface Health Audit (`is_caelestia_shell_healthy`)**: Interrogates `hyprctl layers` to verify that `caelestia-drawers`, `caelestia-background`, and `caelestia-border-exclusion` are actively attached to outputs.
  - **Graceful Quickshell Recovery**: Dispatches `qs -c caelestia kill`, cleans stale runtime sockets in `$XDG_RUNTIME_DIR/quickshell/`, and relaunches `caelestia shell -d`.
  - **Resizer Synchronization & Tiling Barrier**: Waits for `caelestia-border-exclusion` layer surfaces to appear in Hyprland before restarting `caelestia resizer -d`, preventing window margin corruption and tiling distortion.

---

## 3. Cross-Device State Sync Engine

Located in [`backend/sync/`](file:///home/mihir/Codes/VESPER/backend/sync/):
Coordinates real-time state synchronization across Arch Linux desktop, Orange Pi edge nodes, and mobile companions.

### 3.1 Synchronized Cluster Schemas

#### `SynchronizedState`
```python
class SynchronizedState(BaseModel):
    master_volume: int = 60
    zen_mode: bool = False
    focus_mode: bool = False
    active_tasks_count: int = 0
    current_media: Dict[str, Any]  # track_title, artist, is_playing
    last_speech_summary: str = ""
    active_devices: Dict[str, DeviceRegistration]
    version: int = 1
    updated_at: float
```

#### `DeviceRegistration`
```python
class DeviceRegistration(BaseModel):
    device_id: str
    device_type: str  # desktop | orange_pi | mobile_hud | edge_node
    device_name: str
    hostname: str
    os_name: str
    architecture: str
    is_headless: bool
    has_camera: bool
    has_display: bool
    has_microphone: bool
    is_online: bool
    last_heartbeat: float
```

### 3.2 Convergence Workflows

1. **Edge Node Registration**:
   - When an Orange Pi boots, [`SyncClient`](file:///home/mihir/Codes/VESPER/backend/sync/client.py) probes local capabilities (`has_camera=False`, `is_headless=True`).
   - Sends a `DEVICE_REGISTER` frame via WebSocket or `POST /sync/devices/register`.
   - The central [`SyncManager`](file:///home/mihir/Codes/VESPER/backend/sync/sync_manager.py) responds with the full cluster state snapshot and announces the new node to the cluster.
2. **State Diff Propagation**:
   - When master volume or Zen Mode changes on any node, a state diff is submitted.
   - `SyncManager` validates changes, increments the cluster `version`, and broadcasts a `STATE_SYNC` event to all subscribers.
3. **Heartbeat & Disconnect Pruning**:
   - Nodes pulse heartbeats every 10 seconds.
   - If a node fails to heartbeat within 30 seconds, `prune_stale_devices()` marks the device offline and notifies all clients.
