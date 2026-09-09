# VESPER v2 System Implementation and Agent Guide

This document provides a comprehensive technical reference for the architecture, subsystems, event lifecycles, and agent orchestration patterns implemented in VESPER v2.

---

## 1. Executive Summary and Architecture Overview

VESPER is a multimodal, distributed desk companion assistant designed around local-first inference, touchless perceptual interaction, and bi-directional cross-device state synchronization.

```
+-------------------------------------------------------------------------+
|                        VESPER ECOSYSTEM TOPOLOGY                        |
+-------------------------------------------------------------------------+
|                                                                         |
|  +--------------------+        +--------------------+                   |
|  |  Android Companion |        |    Desktop Shell   |                   |
|  | (Kotlin + Expo Go) |        | (Tauri v2 + React) |                   |
|  +---------+----------+        +---------+----------+                   |
|            |                             |                              |
|            |   Multiplexed WebSockets    |                              |
|            +--------------+--------------+                              |
|                           |                                             |
|                           v                                             |
|             +----------------------------+                              |
|             |    FastAPI Gateway Hub     | <---+ UDP Beacon Discovery   |
|             |  (Port 8000 / Router Core) |                              |
|             +-------------+--------------+                              |
|                           |                                             |
|           +---------------+---------------+                             |
|           |                               |                             |
|           v                               v                             |
|  +------------------+           +--------------------+                  |
|  | Swarm Planner &  |           | Perceptual & Voice |                  |
|  | Specialist Swarm |           | Audio Subsystems   |                  |
|  | (10 Specialists) |           | (Piper, OpenWake)  |                  |
|  +------------------+           +--------------------+                  |
|                                                                         |
+-------------------------------------------------------------------------+
```

### Core Tenets
1. **Zero-Cloud Latency for Primary Controls**: Wake-word detection, audio ducking, local TTS speech generation, and continuous touchless gesture tracking run offline on host hardware.
2. **Three-Tier Semantic Routing**: User queries are resolved deterministically (Tier 1 regex/prefilter: 0 tokens), through embedding classification (Tier 2 SemanticRouter), or via LLM Swarm Planning (Tier 3 fallback).
3. **Bi-directional Cross-Device Continuity**: The desk assistant and mobile companion mirror state, notification digests, and battery telemetry in real-time.

---

## 2. Mobile Companion and Android Native Infrastructure

The mobile subsystem resides in `mobile/` and pairs an Expo React Native frontend with a custom native Kotlin module: `alfred-service`.

### 2.1 Native Architecture (`modules/alfred-service`)
- **`AlfredNotificationListener.kt`**: Extends Android's `NotificationListenerService`. Hooks into system-level status bar notifications, extracting package names, titles, notification text, timestamp, and unique notification keys.
- **`AlfredForegroundService.kt`**: Runs as a persistent Android foreground service with a persistent notification (`VESPER Mobile Companion Running`), preventing the Android OS from killing background sockets or telephony listeners.
- **`AlfredServiceModule.kt`**: Bridges native Kotlin events (`onNotificationReceived`, `onNotificationRemoved`, `onCallStateChanged`) directly into React Native JavaScript callbacks.

### 2.2 Telephony State Detection
Using Android's `TelephonyManager` and `TelephonyCallback` (with fallback to `PhoneStateListener` on older API levels), the companion broadcasts real-time telephony state transitions:
- **`CALL_INCOMING`**: Emitted when phone rings, containing the caller identifier if available.
- **`CALL_ANSWERED`**: Emitted when call transitions to active off-hook state.
- **`CALL_ENDED`**: Emitted when call is disconnected.
- **`CALL_MISSED`**: Emitted when incoming ringing stops without an off-hook transition.

### 2.3 Intelligent Notification Ingestion (`backend/sync/notification_service.py`)
Incoming mobile notifications are triaged through a multi-stage filtering pipeline:
- **Noise Suppression**: Discards blank notifications and filters blacklisted system packages (e.g. system download managers, Android OS battery prompts).
- **Persistent Keepalive Filtering**: Media playback status updates (e.g. Spotify `Spotify is trying to play...`) are identified and suppressed from creating interruptive alerts.
- **In-Place Mutation**: Dynamic notifications (e.g. file download progress bars) update existing records in-place rather than flooding the HUD digest.
- **Priority Scoring**: Heuristically scores notifications into `URGENT`, `HIGH`, `NORMAL`, or `LOW` based on keywords and app category.

### 2.4 Zero-Configuration Dynamic UDP Beacon Discovery
To eliminate hardcoded IP addresses when moving between Wi-Fi networks:
- **Gateway Beacon (`backend/gateway/beacon.py`)**: The Gateway broadcasts a UDP beacon packet on port `38400` every 3 seconds:
  ```json
  {
    "service": "vesper-gateway",
    "version": "2.0.0",
    "http_url": "http://192.168.1.50:8000",
    "ws_url": "ws://192.168.1.50:8000/ws"
  }
  ```
- **Mobile Discovery Client (`mobile/src/services/discovery.ts`)**: Listens on UDP socket `38400` on startup. When a beacon packet is received, it automatically configures `API_URL` and initiates the WebSocket handshake.

---

## 3. Touchless Perceptual Gesture Engine

The vision pipeline in `backend/vision/gesture_service.py` provides optical interaction via the host webcam (`/dev/video0`).

```
+--------------------------------------------------------------------------+
|                         TOUCHLESS GESTURE SUITE                          |
+-------------------+------------------------------------------------------+
| Gesture           | Action / System Response                             |
+-------------------+------------------------------------------------------+
| AIR_TAP           | Trigger / Select active item                         |
| CLOSED_FIST       | Instant Barge-In Interrupt: halts TTS & agent steps  |
| OPEN_PALM         | Play / Pause media playback                          |
| PINCH             | Volume Knob continuous adjustment (0% to 100%)       |
| GUN_RIGHT         | Next Track / Forward navigation                      |
| GUN_LEFT          | Previous Track / Backward navigation                 |
| THUMB_UP          | Confirm staged proposal / Upvote                     |
| THUMB_DOWN        | Reject staged proposal / Downvote                    |
| ROCK_ON           | 1-second hold toggles gesture tracking pause/resume  |
+-------------------+------------------------------------------------------+
```

### Emergency Barge-In Gesture Interruption
Whenever the user performs `CLOSED_FIST`:
1. `GestureWorker` detects the pose with confidence > 0.70 across 2 consecutive frames.
2. The Gateway receives `EventType.INTERRUPT`.
3. The running TTS process (`mpv` / `ffplay`) is immediately killed (`SIGTERM`).
4. Active agent planner execution tasks are cancelled.
5. Audio volume is restored, and state transitions to `AGENT_IDLE`.

---

## 4. Voice Subsystem and Acoustic Pipeline

### 4.1 Dual Wake Word Detection (`backend/voice/wakeword/`)
- **"Hey Jarvis"**: Powered by OpenWakeWord's official pre-trained ONNX model (`hey_jarvis_v0.1.onnx`).
- **"Alfred" / "Hey Alfred"**: Evaluated via OpenWakeWord Google Speech Embeddings passed into a trained acoustic verifier (`alfred_verifier.joblib`).
- **Continuous Ingestion**: Uses WebRTC VAD (`vad_mode=1`) to eliminate background noise while continuously streaming 80ms PCM slices to OpenWakeWord's feature accumulator without dropping soft unvoiced initial consonants.
- **Activation Threshold**: Tuned to `0.32` for balanced sensitivity at normal desktop distance.

### 4.2 Local Piper Neural TTS (`backend/voice/tts/piper_tts.py`)
- High-speed, local neural speech engine running on ONNX Runtime.
- **Dynamic Multi-Voice Switching**: Supports on-the-fly voice assignment via `set_voice(name)`:
  - `alan` / `alan_medium`: Paced, crisp British butler (default Alfred persona).
  - `cori` / `cori_high`: Clear, high-fidelity female voice.
  - `ryan` / `ryan_high`: Crisp American male voice.
  - `semaine`: Expressive conversational models.
- **Studio DSP Mastering Filter**: Applies an 80Hz high-pass filter, a 3.2kHz peaking presence boost (+2.5dB), and soft-knee saturation for studio-grade vocal warmth.

### 4.3 Intelligent Audio Ducking Engine
Background system audio (e.g. Spotify, media players) is dynamically ducked:
1. **On Wake Word Detection**: Immediately drops volume to 20% so the user can speak without acoustic competition.
2. **On Incoming Calls**: Automatically ducks volume to 20% on `CALL_INCOMING` and restores it when the call terminates.
3. **During TTS Speech**: Keeps audio ducked while Alfred responds, restoring volume with a 500ms echo dissipation cooldown before microphone reactivation.
4. **Safety Watchdog**: A 30-second watchdog timer automatically un-ducks audio if speech recognition times out or user stays silent.

---

## 5. Conversational Multi-Turn Planning and Specialists

The intelligence layer lives in `backend/agent/planner.py` and coordinates 10 specialists.

```
                      +-------------------+
                      |   User Utterance  |
                      +---------+---------+
                                |
                                v
               +---------------------------------+
               | Tier 1: Deterministic Pre-filter| ----> Direct SwarmPlan
               +----------------+----------------+       (0 Tokens)
                                |
                       (Unmatched Query)
                                |
                                v
               +---------------------------------+
               |  Tier 2: Semantic Router        | ----> Fast Specialist Plan
               +----------------+----------------+
                                |
                        (Complex Query)
                                |
                                v
               +---------------------------------+
               |  Tier 3: LLM Swarm Planner      | ----> Multi-step Execution
               +---------------------------------+
```

### 5.1 Multi-Turn Conversational Email Refinement
When drafting an email ("write an email to X"), the assistant stores the staged draft in `session_context["pending_email_draft"]`. The user can iteratively modify the draft across subsequent turns:
- **Domain Merging**: If the user provides a partial email ("seemapatil") and follows up with "@gmail.com" or "gmail.com", the planner automatically merges the recipient.
- **Subject Modification**: Saying "change subject to Meeting Tomorrow [and send it]" updates the draft and dispatches immediately if requested.
- **Body Expansion**: Saying "add saying we will arrive at 5 PM [and send it]" updates the message body.
- **Recipient Domain Guard**: Prevents premature dispatch if an email lacks a top-level domain, prompting the user for the full address.

### 5.2 Staged Action Disambiguation Queue
For proactive tasks (battery replenishment reminders, calendar scheduling):
- The agent stages an action in `ActionQueueManager` with a 15-second conversational confirmation window.
- The user can say "yes do that" or "no dismiss" within 15 seconds to execute or cancel without re-invoking an LLM.
- **Cross-Process Synchronization**: Staged actions are accessible and resolvable across processes via Gateway REST endpoints (`/sync/proactive/actions/active` and `/sync/proactive/actions/{id}/resolve`).

---

## 6. Running and Validating the System

### Primary Startup Command
To launch all services, peripheral sentries, touchless gesture tracking, wake-word listening, and presence-locking display sentry:
```bash
.venv/bin/python scripts/run_vesper_services.py --with-gestures --with-wakeword --with-sentry
```

### Targeted Test Suite Verification
```bash
# Verify Gateway protocol and WebSockets
.venv/bin/pytest backend/tests/test_gateway.py

# Verify Notification Ingestion and Telephony Events
.venv/bin/pytest backend/tests/test_notifications.py

# Verify Mobile Companion Contract
.venv/bin/pytest backend/tests/test_mobile_companion.py

# Verify Display Sentry, Presence Lock, and Caelestia Shell Recovery
.venv/bin/pytest backend/tests/test_display_sentry.py

# Verify Planner Conversational State & Email Refinement
.venv/bin/pytest backend/tests/test_agent.py -k "email_draft"
```

---

## 7. Developer Guide: Building the Next Specialist Agent

Follow this checklist to implement a new specialist agent (e.g. `HomeAutomationSpecialist`):

1. **Define the Specialist Class**:
   - Create `backend/agent/specialists/home_specialist.py` inheriting from `BaseSpecialist`.
   - Implement `get_tools()` returning structured Pydantic tool schemas.
   - Implement `execute_tool(action, params)` to execute the domain logic.
2. **Register in Swarm Planner**:
   - Import and instantiate the specialist in `backend/agent/planner.py`.
   - Add tool signatures to `self.all_tools` and specialist registry in `SwarmPlanner.__init__`.
3. **Add Semantic Intent**:
   - Add new intent enum values in `backend/agent/semantic_router.py`.
   - Provide training exemplar utterances for fast-path routing.
4. **Wire Deterministic Pre-Filters**:
   - If the specialist supports quick actions (e.g. "turn off lights"), add regex detection in `_check_deterministic_prefilter()` to bypass LLM inference (0-token execution).
5. **Add Unit Tests**:
   - Create tests in `backend/tests/test_home_specialist.py` validating tool execution and planner integration.
