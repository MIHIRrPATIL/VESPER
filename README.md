# VESPER

**VESPER** is an AI-orchestrated, multimodal desk companion and ambient intelligence platform supervised by **Alfred** (the perceptive AI butler).

Designed from first principles for low latency, zero operating cost, touchless multimodal perception, and continuous cross-device synchronization.

---

## 🌟 Key Features

- **🎙️ Low-Power Continuous Wake Word Detection**:
  - Two-tier engine: WebRTC VAD pre-gating (**<0.5% CPU** when silent) + 1.5s rolling acoustic buffer for `"Hey Alfred"` and `"Alfred"`.
  - Self-trigger protection: Pauses audio input during TTS synthesis so Alfred never triggers himself.

- **👁️ Vision Perception Suite (`VisionSpecialist`)**:
  - **Webcam-First Priority**: Analyzes physical surroundings, hand-held items, books, and receipts via `/dev/video0`.
  - **Webcam OCR**: Verbatim transcription of documents, printed code, serial numbers, and handwritten notes.
  - **Screen Perception**: Secondary inspection of active monitors, IDE errors, and terminal logs.
  - **Hardware & Edge Awareness (`DeviceProbe`)**: Automatically probes host architecture (Desktop, Orange Pi, Raspberry Pi, Jetson). If camera is disconnected or absent on an SBC, provides an articulate butler response instead of crashing.
  - **Decoupled Touchless Gestures (`GestureWorker`)**: Runs at throttled 5–8 FPS (80% CPU savings) with zero-CPU standby on camera-less SBCs (`CLOSED_FIST` $\to$ Mute/Pause, `OPEN_PALM` $\to$ Resume, `PEACE_SIGN` $\to$ Toggle Zen).

- **🔄 Cross-Device State Sync Engine (`backend/sync/`)**:
  - Real-time synchronization of master volume, Zen Mode, Focus Mode, active tasks, and currently playing media across Desktop, Orange Pi edge nodes, and mobile companions.
  - Single-pipe multiplexed WebSocket `Channel.SYNC` and full REST endpoint catalog (`/sync/state`, `/sync/devices`).

- **🧠 8-Specialist Swarm Architecture**:
  1. `TaskSpecialist`: Supabase tasks CRUD, combined daily agenda, Google Calendar v3 OAuth.
  2. `MediaSpecialist`: Spotify Web API playback controls and SerpAPI YouTube video search.
  3. `ResearchSpecialist`: Real-time Tavily search + SerpAPI Google fallback (<500ms).
  4. `CrawlSpecialist`: Headless Crawl4AI scraper with `CacheMode.BYPASS` + Groq LPU page synthesis.
  5. `FinanceSpecialist`: Double-entry ledger in ₹ INR, bill splitting, running tabs, debt tracking, savings goals.
  6. `SystemSpecialist`: Hardware vitals, process resource inspector, PipeWire/PulseAudio volume and mute controls.
  7. `MemorySpecialist`: 4-Tier Shodh Cognitive Memory with contradiction resolution, fact superseding, and 360° user dossiers.
  8. `VisionSpecialist`: Optical webcam VLLM reasoning, webcam OCR, screen perception.

- **⚡ Fast-Path & Real-Time Gateway**:
  - Sub-10ms deterministic fast-path regex and out-of-band barge-in interruption (<30ms) via `TaskRegistry`.
  - 100% Free Operating Tier using Groq LPUs (`qwen/qwen3.8-27b`, `llama-3.2-11b-vision-preview`, Whisper-Large-v3-Turbo) and local Piper TTS.

---

## 🏗️ System Architecture

```
                               ┌────────────────────────────────────────────────┐
                               │               Connected Clients                │
                               │  • Desktop HUD (Tauri v2)  • Orange Pi Node    │
                               │  • Android / iOS Companion • Web Dev Client    │
                               └───────────────────────┬────────────────────────┘
                                                       │ WebSocket /ws
                                                       ▼
                               ┌────────────────────────────────────────────────┐
                               │           VESPER API Gateway (:8000)           │
                               │  • Multiplexed Channels (CONTROL, VOICE, SYNC) │
                               │  • TaskRegistry (<30ms Out-of-band Interruption│
                               │  • Central SyncManager (State & Topology)      │
                               └───────────────────────┬────────────────────────┘
                                                       │
                 ┌─────────────────────────────────────┼─────────────────────────────────────┐
                 ▼                                     ▼                                     ▼
   ┌───────────────────────────┐         ┌───────────────────────────┐         ┌───────────────────────────┐
   │    Voice Service (:8002)  │         │    Agent Swarm (:8001)    │         │    Vision Service (:8003) │
   │ • 2-Tier Wake Word        │         │ • Alfred Supervisor       │         │ • Device Hardware Probe   │
   │ • WebRTC VAD Pre-gating   │         │ • 2-Stage Swarm Planner   │         │ • Webcam-First OCR & VLLM │
   │ • Groq Whisper STT        │         │ • 8 Specialist Sub-Agents │         │ • Decoupled Gestures      │
   │ • Multi-Provider TTS      │         │ • 4-Tier Shodh Memory     │         │ • Desktop Screen Capture  │
   └───────────────────────────┘         └───────────────────────────┘         └───────────────────────────┘
```

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- PipeWire or PulseAudio (for audio controls on Linux)
- A free Groq Cloud API Key (`GROQ_API_KEY`)

### Setup
```bash
# Clone the repository
git clone https://github.com/MIHIRrPATIL/VESPER.git
cd VESPER

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment variables
cp backend/.env.example backend/.env
# Edit backend/.env and add your free GROQ_API_KEY and SUPABASE keys
```

### Running Tests
All 50 unit and integration tests can be verified using pytest:
```bash
pytest backend/tests/ -v
```

### Running Services
```bash
# Start API Gateway (Port 8000)
uvicorn backend.gateway.app:app --host 0.0.0.0 --port 8000 --reload

# Start Cognitive Agent Swarm (Port 8001)
uvicorn backend.agent.app:app --host 0.0.0.0 --port 8001 --reload

# Start Voice Subsystem (Port 8002)
uvicorn backend.voice.app:app --host 0.0.0.0 --port 8002 --reload
```

---

## 📚 Documentation

For exhaustive technical references, see the [`docs/`](docs/) directory:
- [AI Specialists & Tools Reference Manual](docs/agents_and_tools_reference.md)
- [Gateway & Real-Time Networking Reference](docs/gateway_and_networking_reference.md)
- [Perceptual & Synchronization Engines Reference](docs/perceptual_and_sync_engines.md)
- [Backend & Multi-Agent Swarm Architecture](docs/backend_and_multiagent_architecture.md)
- [VESPER Desk Companion Specification](docs/vesper_desk_companion_specification.md)

---

## 📜 License

MIT License. Designed and engineered for the VESPER ambient companion ecosystem.
