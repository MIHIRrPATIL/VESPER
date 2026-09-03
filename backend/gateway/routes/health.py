"""VESPER Gateway Health & Status REST Routes."""

from __future__ import annotations

import time
from fastapi import APIRouter, Request

router = APIRouter(tags=["Health"])

START_TIME = time.time()


@router.get("/health")
async def health_check(request: Request) -> dict:
    """Returns basic system liveness, uptime, and active connection metrics."""
    manager = request.app.state.connection_manager
    tasks = request.app.state.task_registry

    return {
        "status": "ok",
        "service": "vesper-gateway",
        "version": "2.0.0",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "active_clients": manager.active_count if manager else 0,
        "active_tasks": tasks.active_count if tasks else 0,
    }


@router.get("/clients")
async def list_clients(request: Request) -> dict:
    """Returns sanitized metadata for all currently connected client sessions."""
    manager = request.app.state.connection_manager
    sessions = manager.get_sessions_info() if manager else []
    return {
        "count": len(sessions),
        "clients": sessions,
    }
