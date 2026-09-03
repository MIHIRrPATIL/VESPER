# VESPER Documentation Hub

Welcome to the documentation repository for **VESPER** (formerly ReflectOS v2), an AI-orchestrated desk companion assistant.

---

## 📚 Core Documents

| Document | Description |
| :--- | :--- |
| **[AI Specialists & Tools Reference](file:///home/mihir/Codes/VESPER/docs/agents_and_tools_reference.md)** | Complete technical manual for all 8 active cognitive swarm specialists (`Task`, `Media`, `Research`, `Crawl`, `Finance`, `System`, `Memory`, `Vision`) + background triage sentry, detailing all OpenAI tool JSON schemas, parameters, types, and return models. |
| **[Gateway & Real-Time Networking Reference](file:///home/mihir/Codes/VESPER/docs/gateway_and_networking_reference.md)** | Full specification for the FastAPI async WebSocket gateway (`/ws`), multiplexed channels (`CONTROL`, `VOICE`, `GESTURE`, `NOTIFY`, `SYSTEM`, `SYNC`), out-of-band barge-in interruptions (<30ms), and REST endpoint catalog. |
| **[Perceptual & Synchronization Engines](file:///home/mihir/Codes/VESPER/docs/perceptual_and_sync_engines.md)** | Architectural deep dive for the 2-Tier Wake Word Engine (<0.5% CPU VAD gating, self-trigger protection), Vision Perception Suite (DeviceProbe, Orange Pi graceful degradation, webcam-first OCR/VLLM, decoupled gestures), and Cross-Device State Sync. |
| **[Backend & Multi-Agent Swarm Architecture](file:///home/mihir/Codes/VESPER/docs/backend_and_multiagent_architecture.md)** | Technical specification for the decoupled microservice backend (`gateway`, `agent`, `voice`, `vision`, `sync`, `data`), Orange Pi / PC deployment topologies, and the LangGraph Multi-Agent Swarm (`Alfred` supervisor, specialist agents, proactive background sentries, parallel multi-intent execution). |
| **[VESPER Desk Companion Specification](file:///home/mihir/Codes/VESPER/docs/vesper_desk_companion_specification.md)** | Full architectural blueprint, hardware bill of materials (Nvidia Jetson Orin Nano Super), fast-path/slow-path agent execution, 3-tier memory model (Shodh-Memory), mobile notification relay (Android vs. iOS), and implementation roadmap. |
| **[ReflectOS v1 Technical Audit](file:///home/mihir/Codes/VESPER/docs/reflectos_architecture_audit.md)** | Comprehensive audit of the original codebase (`/home/mihir/Codes/ReflectOS`), covering the Flask+Eventlet backend, LangGraph state machine, client-side gesture engine, CV/ML models, and lessons learned from technical debt and performance bottlenecks. |


---

## 🎯 Architectural Evolution Summary

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

## 🛠️ Quick Reference: Hardware Specs & Ports

* **Development Compute Platform**: Host Linux PC (Intel Core i5-12500H, 16 vCPUs, 16GB RAM) + Groq/OpenRouter cloud inference.
* **Future Hardware Target**: Nvidia Jetson Orin Nano Super Dev Kit (67 TOPS, 8GB unified memory, 1024 CUDA cores).
* **Desktop App Shell**: **Tauri v2** (Rust core process supervisor, system tray, borderless HUD, ~35MB RAM).
* **Communication Gateway**: FastAPI Async WebSocket server on port `8000` (or `5000`).
* **Desk Client UI**: Vite + React 19 + Tailwind CSS + Framer Motion (inside Tauri Webview).
* **Mobile Companion**: Strictly Native (React Native / Kotlin with Android `NotificationListenerService` + Swift `EventKit`). No PWA due to OS permission sandboxes.
