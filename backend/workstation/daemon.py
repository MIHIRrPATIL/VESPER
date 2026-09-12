#!/usr/bin/env python3
"""VESPER Workstation Local Daemon.

Runs as a lightweight background service under systemd --user on Arch Linux.
Connects via WebSocket to the Gateway (as DESK_HUD) to:
  - Arm live microphone 'Hey Alfred' wake-word listener (openWakeWord + Groq STT + Piper TTS)
  - Arm live camera DPMS power & desk presence sentry (BlazeFace + Hyprland DPMS power management)
  - Execute workstation-local commands via WebSocket RPC (Wayland/grim screen capture, lock, audio sinks)

Configured via environment variables:
  VESPER_ENABLE_WAKEWORD=1 (default: 1)
  VESPER_ENABLE_SENTRY=1   (default: 1)
  VESPER_ENABLE_GESTURES=0 (default: 0)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Setup root path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from scripts.run_vesper_services import TerminalDesktopHUD, _restore_all_ducked_audio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [vesper.workstation] %(message)s",
)
logger = logging.getLogger("vesper.workstation")


async def main() -> None:
    enable_wakeword = os.getenv("VESPER_ENABLE_WAKEWORD", "1").lower() in ("1", "true", "yes")
    enable_sentry = os.getenv("VESPER_ENABLE_SENTRY", "1").lower() in ("1", "true", "yes")
    enable_gestures = os.getenv("VESPER_ENABLE_GESTURES", "1").lower() in ("1", "true", "yes")

    logger.info(
        f"[DAEMON] Initializing Workstation Daemon "
        f"(wakeword={enable_wakeword}, sentry={enable_sentry}, gestures={enable_gestures})..."
    )

    hud = TerminalDesktopHUD(client_id="vesper-workstation-daemon")

    def _sig_handler() -> None:
        logger.info("[DAEMON] Signal received, stopping peripherals and disconnecting...")
        hud.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _sig_handler)

    logger.info(f"[DAEMON] Connecting to Gateway at {hud.ws_url}...")
    while not await hud.connect():
        logger.warning("[DAEMON] Gateway not ready yet, retrying in 2.0s...")
        await asyncio.sleep(2.0)

    logger.info("[DAEMON] Arming background listeners...")
    try:
        await hud.start_session(
            with_gestures=enable_gestures,
            with_wakeword=enable_wakeword,
            with_sentry=enable_sentry,
            headless=True,
        )
    finally:
        hud.stop()
        try:
            _restore_all_ducked_audio()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
