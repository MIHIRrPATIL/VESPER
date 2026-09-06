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
from backend.gateway.routes.health import router as health_router
from backend.gateway.routes.notifications import router as notifications_router
from backend.gateway.routes.sync import router as sync_router
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

    logger.info("[GATEWAY] Online and ready for WebSocket / REST connections.")

    yield

    # Shutdown Phase
    logger.info("[GATEWAY] Shutting down...")
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

    return app



# Default ASGI App Instance for Uvicorn
app = create_app()
