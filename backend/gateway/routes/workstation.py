"""VESPER Workstation Command RPC Route.

Allows specialists (SystemSpecialist, VisionSpecialist) or external services
to command the user's desktop session (Wayland/grim, Hyprland DPMS, audio sinks, session lock)
asynchronously over the existing WebSocket connection without requiring open listening ports on the laptop.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("vesper.gateway.routes.workstation")
router = APIRouter(prefix="/api/workstation", tags=["Workstation RPC"])


class WorkstationCommandRequest(BaseModel):
    command: str = Field(..., description="Action name: dpms, screen_capture, session_lock, audio_sink, media_control")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command-specific parameters")
    timeout: float = Field(default=4.0, description="Max seconds to await desktop execution response")


@router.post("/command")
async def execute_command(req: WorkstationCommandRequest, request: Request):
    """Executes a workstation command on the connected desktop client via WebSocket RPC."""
    msg_router = getattr(request.app.state, "router", None)
    if not msg_router:
        raise HTTPException(status_code=500, detail="Gateway message router unavailable")

    result = await msg_router.execute_workstation_command(
        command=req.command,
        params=req.params,
        timeout=req.timeout,
    )
    return result
