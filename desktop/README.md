# VESPER Desktop Shell (Tauri v2 + Vite / React 19)

This folder contains the **Tauri v2** native desktop application for the desk companion HUD.

* **Tech Stack**: Rust Core (Tauri v2) + Vite + React 19 + Framer Motion + Tailwind CSS.
* **Responsibilities**:
  * Native borderless HUD window with glassmorphism styling.
  * System tray icon with quick toggle controls (Zen Mode, Mute, Status).
  * Supervision of the backend microservice processes.
  * Web Worker hosting MediaPipe `GestureRecognizer` for client-side gesture shortcuts.
