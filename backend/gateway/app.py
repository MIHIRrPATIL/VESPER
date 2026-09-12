"""VESPER Gateway FastAPI Application Factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.gateway.connection_manager import ConnectionManager
from backend.gateway.router import MessageRouter
from backend.gateway.routes.camera import router as camera_router
from backend.gateway.routes.finance import router as finance_router
from backend.gateway.routes.health import router as health_router
from backend.gateway.routes.media import router as media_router
from backend.gateway.routes.notifications import router as notifications_router
from backend.gateway.routes.sync import router as sync_router
from backend.gateway.routes.tasks import router as tasks_router
from backend.gateway.routes.workstation import router as workstation_router
from backend.gateway.routes.ws import router as ws_router
from backend.gateway.task_registry import TaskRegistry
from backend.shared.config import ENVIRONMENT, LOG_LEVEL


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vesper.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages the startup and shutdown lifecycles of the Gateway."""
    logger.info("[GATEWAY] Booting VESPER Gateway...")

    # Initialize Core Singletons
    connection_manager = ConnectionManager()
    task_registry = TaskRegistry()
    message_router = MessageRouter(connection_manager, task_registry)

    # Attach to app.state for access in routers and endpoints
    app.state.connection_manager = connection_manager
    app.state.task_registry = task_registry
    app.state.router = message_router

    # Start Heartbeat Supervisor
    connection_manager.start_heartbeat_supervisor()

    # Start Active Subnet Discovery Scanner
    from backend.sync.network_scanner import network_scanner
    network_scanner.start_periodic_loop()

    # Start UDP Broadcast Discovery Beacon (Port 8005)
    from backend.gateway.beacon import discovery_beacon
    discovery_beacon.start()

    # Start Proactive Agent (battery monitoring + VIP notification triage)
    from backend.agent.proactive.action_queue import action_queue
    action_queue.mark_as_server()

    from backend.agent.proactive_agent import proactive_agent
    proactive_agent.set_broadcast_callback(connection_manager.broadcast)
    proactive_agent.set_send_to_session_callback(connection_manager.send_envelope)
    proactive_agent.start()

    # Register ProactiveAgent as a SyncManager listener for real-time battery eval
    from backend.sync.sync_manager import sync_manager
    sync_manager.add_listener(proactive_agent.on_state_change)

    # Register host workstation in SyncManager
    try:
        from backend.vision.device_probe import DeviceProbe
        from backend.sync.models import DeviceRegistration
        caps = DeviceProbe.get_capabilities()
        # Check battery sensors on host machine
        batt = None
        try:
            import psutil
            batt = psutil.sensors_battery()
        except Exception:
            pass

        host_reg = DeviceRegistration(
            device_id="vesper-host-workstation",
            device_type="desktop",
            device_name=f"VESPER Host ({caps.hostname or 'Desktop'})",
            hostname=caps.hostname,
            os_name=caps.os_name,
            architecture=caps.architecture,
            is_headless=caps.is_headless,
            has_camera=caps.has_camera,
            has_display=caps.has_display,
            has_microphone=caps.has_microphone,
            has_speaker=True,
            cpu_cores=caps.cpu_cores_logical,
            cpu_usage_pct=caps.cpu_usage_pct,
            battery_level=round(batt.percent) if batt else None,
            is_charging=batt.power_plugged if batt else False,
            ram_total_gb=caps.ram_total_gb,
            ram_available_gb=caps.ram_available_gb,
            ip_address=getattr(caps, "ip_address", "127.0.0.1"),
            registered_at=time.time(),
            last_heartbeat=time.time(),
            is_online=True,
        )
        await sync_manager.register_device(host_reg)
    except Exception as host_err:
        logger.warning(f"[GATEWAY] Could not register host workstation: {host_err}")

    logger.info("[GATEWAY] Online and ready for WebSocket / REST connections.")

    yield

    # Shutdown Phase
    logger.info("[GATEWAY] Shutting down...")
    await proactive_agent.stop()
    sync_manager.remove_listener(proactive_agent.on_state_change)
    await discovery_beacon.stop()
    await network_scanner.stop_periodic_loop()
    await connection_manager.stop_heartbeat_supervisor()
    task_registry.cancel_all()
    logger.info("[GATEWAY] Cleanup complete. Offline.")


def create_app() -> FastAPI:
    """Factory creating the configured FastAPI Gateway application."""
    app = FastAPI(
        title="VESPER API Gateway",
        description="Unified async multiplexed WebSocket & REST gateway for the VESPER Desk Companion.",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Enable CORS for local Tauri, browser dev, and mobile clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount Routes
    app.include_router(health_router)
    app.include_router(ws_router)
    app.include_router(sync_router)
    app.include_router(camera_router)
    app.include_router(notifications_router)
    app.include_router(tasks_router)
    app.include_router(media_router)
    app.include_router(finance_router)
    app.include_router(workstation_router)

    @app.get("/briefing")
    @app.get("/notifications/briefing")
    async def get_briefing_alias(force_refresh: bool = False):
        from backend.agent.proactive.briefing_manager import briefing_manager
        return await briefing_manager.get_briefing(timeout=3.0, force_refresh=force_refresh)

    return app



# Default ASGI App Instance for Uvicorn
app = create_app()
