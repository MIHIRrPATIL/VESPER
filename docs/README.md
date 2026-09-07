# VESPER Documentation Hub

Welcome to the documentation repository for **VESPER** (formerly ReflectOS v2), an AI-orchestrated desk companion assistant.

---

## Core Documents

| Document | Description |
| :--- | :--- |
| **[VESPER v2 Implementation & Agent Guide](file:///home/mihir/Codes/VESPER/docs/vesper_v2_system_implementation_and_agent_guide.md)** | Authoritative v2 implementation guide detailing the native Android companion service (`alfred-service`), telephony/call listeners, intelligent notification triage, dynamic UDP LAN beacon discovery, dual wake word engine ("Alfred" & "Jarvis"), Piper multi-voice neural TTS, audio ducking, touchless gesture interruption, and developer guide for building new agents. |
| **[Master Algorithms & Services Architecture](file:///home/mihir/Codes/VESPER/docs/algorithms_and_services_architecture.md)** | Authoritative technical treatise detailing every algorithm in VESPER: MediaPipe 3D landmark geometry, release hysteresis state machines, mirrored wrist swipe velocity, multi-monitor Wayland compositor capture, anti-blank frame detection, 3-tier semantic routing, 2-stage Swarm DAG planner, 4-tier temporal task grounding, least-capability cluster allocation, and client app connectivity manuals. |
| **[Master Service Connectivity & Communication Spec](file:///home/mihir/Codes/VESPER/docs/complete_service_connectivity_and_communication_specification.md)** | Definitive inter-service and cross-device communication manual: transport protocols, multiplexed WebSocket envelopes, Channel.VISION remote streaming, active TCP `/24` discovery, client-side Web Worker gestures, distributed audio routing, least-capability role allocation, out-of-band interrupts, and mobile relay. |
| **[AI Specialists & Tools Reference](file:///home/mihir/Codes/VESPER/docs/agents_and_tools_reference.md)** | Complete technical manual for all 10 active cognitive swarm specialists (`Task`, `Media`, `Research`, `Crawl`, `Finance`, `System`, `Memory`, `Vision`, `Email`, `GitHub`) + background triage sentry, detailing all OpenAI tool JSON schemas, parameters, types, and return models. |
| **[3-Tier Semantic Routing & Cognitive Planning](file:///home/mihir/Codes/VESPER/docs/three_tier_semantic_routing_architecture.md)** | Architectural deep dive for the hybrid 3-tier routing engine: Tier 1 deterministic cache/hardware (<0.1ms), Tier 2 local zero-token semantic router (`all-MiniLM-L6-v2` via FastEmbed, ~10ms CPU), and Tier 3 cognitive LLM generation. Detailed resolution of Exhibit A false-positive keyword bugs and Exhibit B dead code elimination. |
| **[Multi-Turn Context & Dynamic Planning](file:///home/mihir/Codes/VESPER/docs/multi_turn_context_and_planning.md)** | Technical specification for conversational context holding across turns, anaphora resolution (*"who sent me the email?"*), full email thread reconstruction, dynamic sequential variable interpolation (`$step_1.var`), and anti-hallucination fact verification. |
| **[Distributed Cluster & Hardware Allocation](file:///home/mihir/Codes/VESPER/docs/distributed_cluster_and_hardware_allocation.md)** | Architectural deep dive for distributed multi-device cluster topologies (Orange Pi + Mobile HUD + Laptop/Jetson), real-time CPU/RAM hardware telemetry probes, compute headroom verification, and the Least-Capability Workload Allocation Engine. |
| **[OAuth & Integrations Setup Guide](file:///home/mihir/Codes/VESPER/docs/oauth_and_integrations_guide.md)** | Complete setup guide for Google OAuth 2.0 (Gmail scopes & Calendar), Spotify Web API device switching, GitHub REST API, and Tavily/SerpAPI research engines with offline sandbox fallbacks. |
| **[Gateway & Real-Time Networking Reference](file:///home/mihir/Codes/VESPER/docs/gateway_and_networking_reference.md)** | Full specification for the FastAPI async WebSocket gateway (`/ws`), multiplexed channels (`CONTROL`, `VOICE`, `GESTURE`, `NOTIFY`, `SYSTEM`, `SYNC`), out-of-band barge-in interruptions (<30ms), and REST endpoint catalog. |
| **[Touchless Gesture Perception & Control](file:///home/mihir/Codes/VESPER/docs/gesture_perception_and_control.md)** | Complete specification for the expanded gesture vocabulary (`CLOSED_FIST`, `OPEN_PALM`, `SWIPE_LEFT`/`RIGHT`, `VOLUME_DIAL`, `PEACE_SIGN`, `POINTING_UP`, `ROCK_ON` lock), bifurcated perception (client Web Worker vs. throttled 5–8 FPS backend `GestureWorker`), gateway event broadcast, and state sync. |
| **[Perceptual & Synchronization Engines](file:///home/mihir/Codes/VESPER/docs/perceptual_and_sync_engines.md)** | Architectural deep dive for the 2-Tier Wake Word Engine (<0.5% CPU VAD gating, self-trigger protection), Vision Perception Suite (DeviceProbe, Orange Pi graceful degradation, webcam-first OCR/VLLM, decoupled gestures), and Cross-Device State Sync. |
| **[Backend & Multi-Agent Swarm Architecture](file:///home/mihir/Codes/VESPER/docs/backend_and_multiagent_architecture.md)** | Technical specification for the decoupled microservice backend (`gateway`, `agent`, `voice`, `vision`, `sync`, `data`), Orange Pi / PC deployment topologies, and the LangGraph Multi-Agent Swarm (`Alfred` supervisor, specialist agents, proactive background sentries, parallel multi-intent execution). |
| **[VESPER Desk Companion Specification](file:///home/mihir/Codes/VESPER/docs/vesper_desk_companion_specification.md)** | Full architectural blueprint, hardware bill of materials (Nvidia Jetson Orin Nano Super), fast-path/slow-path agent execution, 3-tier memory model (Shodh-Memory), mobile notification relay (Android vs. iOS), and implementation roadmap. |
| **[Complete System Architecture Diagram](file:///home/mihir/Codes/VESPER/docs/vesper_complete_system_architecture.puml)** | Comprehensive system architecture specifying every client connection (Tauri v2 Desktop, Kotlin/Swift Mobile, Orange Pi edge nodes), multiplexed WebSocket envelopes, 3-tier semantic routing, all 10 specialist sub-agents with every individual tool signature, and background sentries. Available in **[PlantUML Source](file:///home/mihir/Codes/VESPER/docs/vesper_complete_system_architecture.puml)**, **[Scalable SVG](file:///home/mihir/Codes/VESPER/docs/vesper_complete_system_architecture.svg)**, and **[4K PNG](file:///home/mihir/Codes/VESPER/docs/vesper_complete_system_architecture.png)**. |
| **[ReflectOS v1 Technical Audit](file:///home/mihir/Codes/VESPER/docs/reflectos_architecture_audit.md)** | Comprehensive audit of the original codebase (`/home/mihir/Codes/ReflectOS`), covering the Flask+Eventlet backend, LangGraph state machine, client-side gesture engine, CV/ML models, and lessons learned from technical debt and performance bottlenecks. |


---

## Architectural Evolution Summary

```
   ┌──────────────────────────────────────────────────────────┐
   │                  ReflectOS v1 (Smart Mirror)             │
   │  • Large-scale gesture HUD (across room)                 │
   │  • Flask + Eventlet + Socket.IO (concurrency clashes)    │
   │  • Sequential multi-hop LangGraph (4-10s latency)        │
   │  • Unbounded LangGraph history & gesture tracking memory │
   │  • Unofficial consumer TTS scrapers (edge-tts)           │
   └─────────────────────────────┬────────────────────────────┘
                                 │ Redesigned from
                                 │ first principles
                                 ▼
   ┌──────────────────────────────────────────────────────────┐
   │             VESPER / v2 (Stationary Desk Companion)       │
   │  • Voice-first ambient assistant with glanceable UI      │
   │  • Tauri v2 Native Desktop Shell (Rust + Vite/React 19)  │
   │  • FastAPI + Asyncio + native WebSocket gateway          │
   │  • Rust Sidecar managing Python backend lifecycle        │
   │  • Bifurcated LangGraph (Fast Path <500ms / Slow Path)   │
   │  • 3-Tier Memory: Sliding window + Shodh-Memory + SQLite │
   │  • MediaPipe in Web Worker + optional Ultraleap sensor   │
   │  • Strictly Native Mobile App (NotificationListener)     │
   │  • Dev on Intel CPU / Cloud; future Jetson edge path     │
   └──────────────────────────────────────────────────────────┘
```

---

## Quick Reference: Hardware Specs & Ports

* **Development Compute Platform**: Host Linux PC (Intel Core i5-12500H, 16 vCPUs, 16GB RAM) + Groq/OpenRouter cloud inference.
* **Future Hardware Target**: Nvidia Jetson Orin Nano Super Dev Kit (67 TOPS, 8GB unified memory, 1024 CUDA cores).
* **Desktop App Shell**: **Tauri v2** (Rust core process supervisor, system tray, borderless HUD, ~35MB RAM).
* **Communication Gateway**: FastAPI Async WebSocket server on port `8000` (or `5000`).
* **Desk Client UI**: Vite + React 19 + Tailwind CSS + Framer Motion (inside Tauri Webview).
* **Mobile Companion**: Strictly Native (React Native / Kotlin with Android `NotificationListenerService` + Swift `EventKit`). No PWA due to OS permission sandboxes.
