# ReflectOS v1: Architecture & Technical Audit Reference

This document provides a comprehensive technical reference for the original **ReflectOS** codebase (located at `/home/mihir/Codes/ReflectOS`). It details the implementation, components, data flows, and the stability/performance bottlenecks identified during auditing, serving as the benchmark and reference for the new desk companion architecture (**VESPER / ReflectOS v2**).

---

## 1. Executive Summary & Original Concept

* **Concept**: Ambient, gesture-driven Smart Mirror / Heads-Up Display (HUD) for room-scale interaction.
* **Primary Inputs**: Expressive two-hand and one-hand gestures via webcam (MediaPipe HandLandmarker in browser) + Voice (Wake word "Alfred" + Web Speech API).
* **Primary Outputs**: Holographic/cyberpunk-style HUD canvas rendered in Next.js + Neural TTS audio responses (`edge-tts` ChristopherNeural / `pyttsx3`).
* **Compute Architecture**: Split between browser (Next.js 16 + React 19) and Python backend (Flask + Eventlet + LangGraph + local SQLite WAL).

---

## 2. Directory Structure & Key Files

```
ReflectOS/
├── ARCHITECTURE.md                  # High-level architecture guide
├── README.md                        # Project overview, setup, gesture guide
├── backend/
│   ├── app.py                       # Flask app + Flask-SocketIO (Eventlet async_mode)
│   ├── download_model.py            # Script to fetch Phi-3-mini-4k GGUF model
│   ├── requirements.txt             # Python dependencies
│   ├── ai/
│   │   ├── core/
│   │   │   ├── config.py            # OpenRouter API keys (keys 1-4) & endpoint settings
│   │   │   ├── local_llm.py         # Llama-cpp-python wrapper for Phi-3 GGUF
│   │   │   └── state.py             # ReflectState TypedDict & state initializers
│   │   ├── graph/
│   │   │   ├── graph.py             # LangGraph workflow definition & compiled app
│   │   │   └── edges.py             # Conditional edge routers
│   │   ├── nodes/
│   │   │   ├── intent_classifier.py # OpenRouter/Phi-3 intent classifier
│   │   │   ├── validator.py         # Guard node for safety and correctness
│   │   │   ├── evaluator.py         # Evaluator with recursive refinement loop
│   │   │   ├── context_manager.py   # State context injection
│   │   │   ├── response_generator.py# Cohesive final natural language synthesis
│   │   │   └── interrupt_handler.py # Interrupt checks and active command invalidation
│   │   └── tools/
│   │       ├── expense_nodes.py     # Personal finance & expense management tool
│   │       ├── spotify_nodes.py     # Spotify playback, queue, device control
│   │       ├── task_nodes.py        # Task/TODO management
│   │       ├── calendar_nodes.py    # Google Calendar v3 events
│   │       ├── weather.py           # Weather and forecast API
│   │       ├── search_nodes.py      # Tavily / SerpAPI search
│   │       ├── composite_nodes.py   # Subtask decomposition for multi-intent inputs
│   │       ├── confirmation_nodes.py# Action confirmation dialogs
│   │       ├── system_control.py    # Master volume control (pactl / pycaw)
│   │       ├── vision_nodes.py      # Vision-language model integration
│   │       └── youtube_nodes.py     # YouTube search & playback
│   ├── core/
│   │   ├── db.py                    # SQLite checkpointer (SqliteSaver), tables & Redis
│   │   └── patches.py               # Eventlet monkeypatching & LangChain shims
│   ├── services/
│   │   ├── ai_service.py            # AIService singleton, graph execution, TTS call
│   │   ├── expense_service.py       # SQL ledger queries (accounts, transactions, debts)
│   │   ├── spotify_service.py       # Spotipy client wrapper
│   │   ├── task_service.py          # SQLite task CRUD
│   │   ├── calendar_service.py      # Google OAuth & Calendar API wrapper
│   │   └── volume_service.py        # OS volume setter and smoother
│   ├── ml/
│   │   ├── object_detects.py        # YOLOv8 object detector (yolov8n-oiv7.pt)
│   │   ├── ocr_model.py             # PaddleOCR integration
│   │   └── outfit_model.py          # Outfit recommendation heuristics
│   └── utils/
│       ├── tts.py                   # edge-tts async generator + pyttsx3 fallback
│       ├── volume_control.py        # pactl (Linux) / pycaw (Windows) volume
│       └── ai_helpers.py            # JSON extraction and markdown stripping
└── frontend/
    ├── app/
    │   ├── layout.tsx               # Root HUD layout, providers, background grid
    │   ├── page.tsx                 # HUD viewport (clock, panels, reticle, agent)
    │   └── globals.css              # Cyberpunk HUD styling, glassmorphism, animations
    ├── components/
    │   ├── VoiceAssistant.tsx       # Dynamic SVG oscilloscope ring, audio playback
    │   ├── GestureFeedback.tsx      # Gesture status, cursor emulation, camera overlay
    │   ├── GestureCamera.tsx        # react-webcam, MediaPipe HandLandmarker lifecycle
    │   ├── TodoPanel.tsx            # HUD tasks panel with timeline line graphics
    │   ├── AccountBalances.tsx      # Bank and cash balances display
    │   ├── ExpensePanel.tsx         # Detailed finance tracking panel
    │   └── YouTubePlayer.tsx        # Embedded YouTube video player
    ├── context/
    │   ├── HUDContext.tsx           # Zen mode and HUD UI state
    │   └── SocketContext.tsx        # WebSocket connection state
    └── lib/
        ├── hooks/
        │   ├── useWakeWord.ts       # Continuous Web Speech API listener for "Alfred"
        │   └── useSpeechToText.ts   # Continuous Web Speech recognition + silence timer
        └── gesture-engine/
            ├── GestureManager.ts    # Gesture state machine, priorities, sticky locks
            ├── HandTracker.ts       # 21 3D landmark extractor, scale & normal vectors
            ├── GestureSocket.ts     # Singleton Socket.io client emitter
            ├── primitives.ts        # Vector math (cross product, distance, normalize)
            ├── Gesture.ts           # Base class for gesture detectors
            └── gestures/
                ├── oneHand.ts       # AirTap, GunTap, VolumeDial, FistMove, etc.
                └── twoHand.ts       # SpreadZoom, WristCross, AirMeasure, AirFrame
```

---

## 3. Detailed Data Flow & Component Architecture

### 3.1 Multiplexed WebSocket Protocol
ReflectOS consolidated network communication onto a single Socket.IO event called `message`:
* **Client to Server Envelope**:
  ```json
  {
    "uuid": "req-uuid-1234",
    "type": "VOICE_COMMAND" | "TOOL_CALL" | "GESTURE" | "INTERRUPT",
    "payload": {
      "command": "Play some jazz",
      "image": "data:image/jpeg;base64,...",
      "gesture": "VOLUME:65",
      "action": "OCR"
    }
  }
  ```
* **Server to Client Envelope**:
  ```json
  {
    "uuid": "req-uuid-1234",
    "type": "RESPONSE",
    "payload": {
      "status": "processed",
      "command": "Play some jazz",
      "response": "Now playing jazz on Spotify.",
      "audio": "data:audio/mp3;base64,...",
      "intent": "PLAY_SPOTIFY",
      "should_listen": false,
      "tool_outputs": { ... }
    }
  }
  ```

### 3.2 LangGraph Execution Pipeline
Every incoming command passed through a sequential multi-node graph:
1. `user_input` → Captures command text and attaches image payload.
2. `interrupt_handler` → Verifies active request UUID; if interrupted, routes directly to response.
3. `intent_classifier` → Calls OpenRouter (or local Phi-3) to map request to one of 20+ `IntentType` enums.
4. `validator` → Guard node. For sensitive intents (`MANAGE_EXPENSES`, `ADD_TASK`), prompts LLM to check safety; rejects or approves.
5. `context_manager` → Flat context enrichment (user preferences, time of day, rolling history) and routes to tool.
6. `skill_nodes` → Invokes external service (`spotify_nodes`, `expense_nodes`, `calendar_nodes`, `weather`, `task_nodes`, `composite_nodes`).
7. `evaluator_node` → Quality gate node. Assesses tool outputs against user intent; triggers up to 2 refinement loops back to `intent_classifier` if unsatisfied.
8. `response_generator` → Final LLM call synthesizing tool outputs into conversational response.
9. `generate_tts_base64` → Sends full text to `edge-tts` to create MP3, encodes to base64, emits to frontend.

### 3.3 Database Layer (`data/memory.db`)
* **SQLite with WAL mode** (`PRAGMA journal_mode=WAL`):
  * `checkpointer`: LangGraph `SqliteSaver` tracking graph state per thread (`user_id_session_id`).
  * `user_memories`: Key-value user preference memory (`user_id`, `key`, `value`, `updated_at`).
  * `tasks`: Todo items (`id`, `user_id`, `title`, `deadline`, `done`, `created_at`).
  * `accounts`: Financial accounts (`id`, `user_id`, `name`, `type`, `balance`).
  * `transactions`: Ledgers (`id`, `user_id`, `type`, `amount`, `category`, `account_id`, `date`).
  * `categories`: Expense/income classification categories.
  * `debts`: Peer debt tracking (`person`, `amount`, `direction: owe/owed`, `settled`).

---

## 4. Key Lessons & Known Technical Debt

An audit of ReflectOS highlighted critical technical bottlenecks that shaped the decision to redesign for v2:

| Component | Root Cause & Mechanism | Impact on ReflectOS v1 | Mitigation for v2 / VESPER |
|---|---|---|---|
| **Gesture Engine History** | `history` map in `GestureManager.ts` appended frames per hand ID without pruning stale IDs. | Memory leak over long sessions; browser tab eventually crash with Out-Of-Memory (OOM). | Drop custom multi-hand tracker; adopt pretrained `GestureRecognizer` in a dedicated Web Worker; strictly bound history buffers. |
| **Cursor Hover Check** | `checkClickable()` executed `document.elementFromPoint()` at 60fps inside animation loop. | Triggered synchronous browser style recalcs and DOM reflows 60 times per second, pinning client CPU. | Replace per-frame DOM raycasting with cached bounding-box spatial indexes or discrete hardware shortcuts. |
| **MediaPipe Context Leak** | `GestureCamera.tsx` did not invoke `handLandmarker.close()` during React component unmount/remount. | Leaked WebGL contexts and WASM memory allocations when toggling views. | Enforce deterministic component lifecycle cleanup; isolate vision inference outside UI render loops. |
| **LangGraph History Bloat** | Conversation state (`messages`) appended every user and assistant turn indefinitely to SQLite thread. | Latency grew linearly from ~250ms to >10 seconds per turn as conversation history inflated LLM prompts. | Hard sliding window (last 10–15 messages) for working memory; decouple long-term recall into **Shodh-Memory**. |
| **Eventlet Threading Clashes** | `eventlet.monkey_patch()` collided with native C-extensions (PaddleOCR, PyTorch, llama-cpp) and Python threading. | Socket.IO ping/pong heartbeats timed out; random connection drops during heavy AI computation. | Eliminate Flask + Eventlet; adopt **FastAPI + asyncio + native Uvicorn WebSockets**; isolate heavy local models in separate processes. |
| **TTS & STT Reliability** | Relied on `edge-tts` (unofficial Microsoft consumer endpoint) and Web Speech API. | Intermittent 429/403 rate limits, audio generation failures, and browser-specific microphone contention. | Upgrade to robust production providers (Azure / Google Cloud / ElevenLabs / Sarvam) or local `faster-whisper`. |
| **Multi-Hop Agent Latency** | Sequential pipeline: Classify → Validate → Context → Tool → Evaluate → Generate → Full TTS. | 4 to 10+ second turn turnaround for simple actions (like "pause music" or "set volume"). | **Split into Fast Path (<500ms single structured call) and Slow Path (bounded refinement).** Stream audio tokens. |
