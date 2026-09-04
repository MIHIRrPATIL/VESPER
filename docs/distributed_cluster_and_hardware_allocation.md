# Distributed Cluster Topology, Hardware Telemetry & Workload Allocation

This document specifies the distributed multi-device cluster architecture of VESPER: hardware capability probing, compute headroom verification, and the **Least-Capability Workload Allocation Engine**.

---

## 1. Architectural Philosophy: The Least-Capability Principle

VESPER distributes sensory and cognitive workloads across a heterogeneous cluster of desk companion devices:
- **Low-power edge devices** should handle lightweight, continuous tasks (microphone listening, speaker playback) without drawing heavy power or heating up.
- **Dedicated companion screens** should handle user interface display and notifications.
- **High-power compute hosts** should handle heavy cognitive inference (VLLM vision models, OCR, multi-agent swarm planning) without being bogged down by audio streaming loops.

```
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│     Orange Pi Zero 3    │     │   Pixel / Mobile HUD    │     │  ASUS VivoBook / Jetson │
│  (Least-Capability Node)│     │  (Mid-Tier Companion)   │     │  (High-Capability Host) │
├─────────────────────────┤     ├─────────────────────────┤     ├─────────────────────────┤
│ • 4 Cores, 1.0 GB RAM   │     │ • 8 Cores, 12.0 GB RAM  │     │ • 16 Cores, 16.0 GB RAM │
│ • Cap Score: 11.3       │     │ • Cap Score: 65.4       │     │ • Cap Score: 106.6      │
├─────────────────────────┤     ├─────────────────────────┤     ├─────────────────────────┤
│ audio_capture (VAD)   │     │ hud_display           │     │ vision_perception     │
│ audio_playback (TTS)  │     │ notification_relay    │     │ cognitive_swarm       │
│                       │     │                       │     │ vector_memory         │
└────────────┬────────────┘     └────────────┬────────────┘     └────────────┬────────────┘
             │                               │                               │
             └───────────────────────┬───────┴───────────────────────────────┘
                                     ▼
                     FastAPI Async WebSocket Gateway
                      (/ws multiplexed channels)
```

---

## 2. Hardware Telemetry & Safety Gate Probes

Implemented in [`backend/vision/device_probe.py`](file:///home/mihir/Codes/VESPER/backend/vision/device_probe.py):

### Probed Metrics
- **CPU Information**: Physical cores, logical cores, instantaneous CPU load percentage.
- **Memory Information**: Total RAM, available RAM (free + buffers/cache), used RAM.
- **Sensory Availability**: Camera indices (`/dev/video*`), display monitors (`mss`), audio devices.

```python
from backend.vision.device_probe import DeviceProbe

status = DeviceProbe.get_status()
print(f"CPU: {status['cpu_count_logical']} cores @ {status['cpu_usage_pct']}% load")
print(f"RAM: {status['ram_available_gb']:.2f}GB available of {status['ram_total_gb']:.2f}GB")
```

---

## 3. Compute Headroom Safety Gate

Implemented in [`backend/sync/cluster_allocator.py`](file:///home/mihir/Codes/VESPER/backend/sync/cluster_allocator.py):

Before assigning memory-intensive roles (`cognitive_swarm`, `vision_perception`) to any node, the allocator evaluates four strict safety criteria:

| Safety Criterion | Threshold | Rationale |
| :--- | :--- | :--- |
| **Total Physical RAM** | `>= 3.5 GB` | Prevents attempting to load LLM reasoning / vision contexts on SBCs or micro-nodes. |
| **Available Free Buffer** | `>= 1.2 GB` | Protects the operating system against Linux OOM killer invocation during active multitasking. |
| **CPU Physical Cores** | `>= 2 cores` | Ensures multi-threaded concurrency for gateway I/O alongside model inference. |
| **Operating CPU Load** | `<= 88.0%` | Prevents scheduling heavy cognitive tasks on thermally throttled or overloaded CPUs. |

If a device fails any criterion, the allocator flags it as `INSUFFICIENT FOR SWARM` and restricts it to peripheral roles (audio, display).

---

## 4. Workload Allocation Algorithm

### Step 1: Capability Scoring Formula
Each device is assigned a normalized capability score:
$$\text{CapScore} = (\text{RAM}_{\text{total}} \times 4.0) + (\text{RAM}_{\text{available}} \times 2.0) + (\text{Cores} \times 1.5) - (\text{CPULoad} \times 0.2)$$

### Step 2: Sorting and Tier Categorization
Connected devices are sorted in ascending order of capability:
1. **Low-Tier Device** (Lowest CapScore):
   - Assigned `audio_capture` (microphone) and `audio_playback` (speaker).
2. **Mid-Tier Companion**:
   - Assigned `hud_display` (cards, visuals) and `notification_relay`.
3. **High-Tier Workstation**:
   - Assigned `vision_perception` (camera OCR/VLLM), `cognitive_swarm` (Alfred multi-agent planning), and `vector_memory`.

### Step 3: Graceful Failover
If the Orange Pi or Mobile Phone disconnects:
- The allocator dynamically detects the node drop.
- The high-capability host (Laptop) immediately re-assumes `audio_capture`, `audio_playback`, and `hud_display` without dropping active agent state or restarting the gateway.

---

## 5. Inspection CLI (`scripts/cluster_topology.py`)

A developer tool to inspect local host telemetry or simulate cluster allocation:

```bash
# Inspect local host hardware:
.venv/bin/python3 scripts/cluster_topology.py

# Simulate the 3-device heterogeneous cluster:
.venv/bin/python3 scripts/cluster_topology.py --simulate
```

### Simulation Output
```
======================================================================
      VESPER DISTRIBUTED CLUSTER TOPOLOGY & ALLOCATION ENGINE         
======================================================================

[A] VERIFYING CPU & RAM HEADROOM ON CLUSTER CANDIDATES:
  • Orange Pi Zero 3: [INSUFFICIENT FOR SWARM] (Avail RAM: 0.5GB, CPU Load: 15.0%)
  • Pixel 8 Pro (HUD): [SAFE FOR SWARM] (Avail RAM: 4.8GB, CPU Load: 24.0%)
  • ASUS VivoBook Workstation: [SAFE FOR SWARM] (Avail RAM: 5.2GB, CPU Load: 18.5%)

[B] RUNNING LEAST-CAPABILITY WORKLOAD ALLOCATION:
----------------------------------------------------------------------
DEVICE / NODE          CAP SCORE   CPU / RAM          ASSIGNED CLUSTER ROLES
----------------------------------------------------------------------
Orange Pi Zero 3       11.3        4c | 0.5/1.0GB     audio_capture, audio_playback
Pixel 8 Pro (HUD)      65.4        8c | 4.8/12.0GB    hud_display, notification_relay
ASUS VivoBook Workstation 106.6       16c | 5.2/16.0GB   hud_display, notification_relay, vision_perception, cognitive_swarm, vector_memory
----------------------------------------------------------------------
```
