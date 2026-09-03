# VESPER Gateway & Real-Time Networking Reference

This document provides the complete networking specification, WebSocket channel multiplexing protocol, REST catalog, and barge-in interruption architecture for the VESPER API Gateway.

---

## 1. Gateway Architecture Overview

The VESPER Gateway runs as an asynchronous FastAPI microservice on port `8000`:
- **Single-Pipe Multiplexing**: All client communications (voice audio chunks, HUD state cards, touchless gestures, mobile notifications, cross-device synchronization, and out-of-band interrupts) travel across a single bidirectional WebSocket connection at `/ws`.
- **Decoupled Asynchronous Tasks**: Incoming client requests are dispatched into background `asyncio.Task` instances tracked by [`TaskRegistry`](file:///home/mihir/Codes/VESPER/backend/gateway/task_registry.py), ensuring that long-running LLM or search queries never block the WebSocket frame loop.
- **Out-of-Band Interruption (<30ms)**: User speech barge-in or UI interrupt events can instantaneously cancel in-flight tasks via `asyncio.Task.cancel()`.

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                   Connected Clients                     │
                    │   • Desktop HUD (Tauri v2)    • Edge Nodes (Orange Pi)  │
                    │   • Android Mobile Companion  • iOS Companion           │
                    └───────────┬─────────────────────────▲───────────────────┘
                                │ JSON ClientEnvelope     │ JSON ServerEnvelope
                                ▼                         │
                    ┌─────────────────────────────────────────────────────────┐
                    │               VESPER FastAPI Gateway (:8000)            │
                    │   • ConnectionManager (Heartbeat Supervisor, Sessions)  │
                    │   • MessageRouter (Demultiplexing to Channel Handlers)  │
                    │   • TaskRegistry (Active Task Tracking & Cancellation)  │
                    └───────────┬─────────────────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┬──────────────────────┐
         ▼                      ▼                      ▼                      ▼
   Channel.CONTROL        Channel.VOICE          Channel.GESTURE        Channel.SYNC
  • Handshake            • Text Command         • Touchless actions    • State Sync
  • Ping/Pong            • Agent Response       • Volume Dials         • Device Topology
```

---

## 2. Universal Message Envelopes

All communication across `/ws` uses standardized Pydantic v2 envelope schemas defined in [`backend/shared/events.py`](file:///home/mihir/Codes/VESPER/backend/shared/events.py):

### ClientEnvelope (Client $\to$ Gateway)
```json
{
  "uuid": "4f9d0c2e-7b1a-4c28-8d34-9d18e9a2b531",
  "channel": "VOICE",
  "type": "VOICE_COMMAND",
  "timestamp": 1725412800.123,
  "payload": {
    "command": "Play Starboy on Spotify",
    "is_final": true
  }
}
```

### ServerEnvelope (Gateway $\to$ Client)
```json
{
  "uuid": "4f9d0c2e-7b1a-4c28-8d34-9d18e9a2b531",
  "channel": "VOICE",
  "type": "AGENT_RESPONSE",
  "timestamp": 1725412800.456,
  "status": "ok",
  "payload": {
    "response": "Playing 'Starboy' by The Weeknd, sir.",
    "hud_cards": [
      {
        "type": "media_card",
        "track": "Starboy",
        "artist": "The Weeknd"
      }
    ]
  }
}
```

---

## 3. Multiplexed Channel Protocol

### 1. `Channel.CONTROL`
Manages connection handshakes and keep-alive health checks.
- **`CLIENT_HELLO`**: First frame sent by client upon connection.
  ```json
  {
    "channel": "CONTROL",
    "type": "CLIENT_HELLO",
    "payload": {
      "client_id": "desktop-workstation",
      "client_type": "DESK_HUD",
      "version": "2.0.0"
    }
  }
  ```
- **`SERVER_HELLO`**: Gateway acknowledgment and session authorization.
- **`PING` / `PONG`**: Automated heartbeat frames exchanged every 15 seconds. If a client fails to respond within 5 seconds, the session is terminated.

### 2. `Channel.VOICE`
Handles user speech transcripts and Alfred's responses.
- **`VOICE_COMMAND`**: Dispatched by the frontend Web Speech API or local wake word pipeline containing transcribed user queries.
- **`AGENT_RESPONSE`**: Contains Alfred's speech summary, markdown body for HUD display, and dynamic card payloads.

### 3. `Channel.GESTURE`
Transmits discrete touchless gestures recognized by the client-side Web Worker or decoupled camera worker:
- **`TOGGLE_ZEN`**: Toggles minimalist Zen Mode on desk HUD.
- **`VOLUME_DIAL:<0-100>`**: Sets system master volume level.
- **`MUTE`**: Instantly mutes active audio sinks.

### 4. `Channel.NOTIFY`
Ingests and relays notifications from the mobile companion app:
- **`NOTIFICATION_RELAY`**: Mobile app relays notification with sender, package name, title, and body.
- **`NOTIFICATION_DIGEST`**: Gateway filters, dedupes, and broadcasts glanceable ambient cards to the desktop HUD.

### 5. `Channel.SYSTEM`
High-priority administrative and hardware control events:
- **`SET_VOLUME`**: Broadcasts master volume changes.
- **`ZEN_MODE_STATE` / `FOCUS_MODE_STATE`**: Replicates UI modes across all connected displays.
- **`INTERRUPT`**: Out-of-band barge-in cancellation signal. Cancels the target task UUID or all in-flight tasks for the session within **<30ms**.

### 6. `Channel.SYNC`
Synchronizes state and hardware topology across multiple devices (Desktop, Orange Pi, Mobile):
- **`DEVICE_REGISTER`**: Registers a device's hardware profile (`has_camera`, `has_display`, `is_headless`, `architecture`).
- **`DEVICE_HEARTBEAT`**: Keeps device status active in the cluster.
- **`STATE_SYNC`**: Broadcasts state diffs (volume, media, tasks, modes) to all connected nodes.
- **`STATE_SNAPSHOT`**: Requests a full snapshot of current cluster state.

---

## 4. REST Endpoints Catalog

In addition to WebSocket streaming, the Gateway exposes HTTP/REST endpoints for health probes, service discovery, and stateless edge devices:

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Gateway status, active client count, and system uptime. |
| `GET` | `/clients` | List of currently connected client sessions. |
| `GET` | `/sync/state` | Returns the full cluster synchronized state snapshot. |
| `POST` | `/sync/state` | Applies a state diff (e.g. `master_volume`, `focus_mode`). |
| `GET` | `/sync/devices` | Lists all online registered devices and hardware capabilities. |
| `POST` | `/sync/devices/register` | Registers an edge device (e.g. Orange Pi) via REST. |
| `POST` | `/sync/devices/heartbeat` | Records a heartbeat pulse for an edge device. |
