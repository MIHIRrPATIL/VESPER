"""VESPER REST Endpoints for Cross-Device Synchronization.

Allows HTTP/REST-only edge devices or web apps to read snapshots, register presence,
and submit state diffs without maintaining a continuous WebSocket connection.
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.sync.models import DeviceRegistration, SynchronizedState
from backend.sync.sync_manager import sync_manager

router = APIRouter(prefix="/sync", tags=["sync"])


class StateUpdateRequest(BaseModel):
    diff: Dict[str, Any]
    source_device_id: str = "rest_client"


class HeartbeatRequest(BaseModel):
    device_id: str


@router.get("/state", response_model=Dict[str, Any])
async def get_state_snapshot() -> Dict[str, Any]:
    """Returns the full cluster synchronization state snapshot."""
    return sync_manager.get_state_snapshot().to_snapshot()


@router.post("/state", response_model=Dict[str, Any])
async def update_state(req: StateUpdateRequest) -> Dict[str, Any]:
    """Applies a state update diff to the cluster state."""
    state = await sync_manager.update_state(req.diff, source_device_id=req.source_device_id)
    return state.to_snapshot()


@router.get("/devices", response_model=List[DeviceRegistration])
async def list_active_devices() -> List[DeviceRegistration]:
    """Returns list of currently active online devices."""
    return sync_manager.get_active_devices()


@router.post("/devices/register", response_model=Dict[str, Any])
async def register_device(reg: DeviceRegistration) -> Dict[str, Any]:
    """Registers an edge device into the cluster."""
    state = await sync_manager.register_device(reg)
    return {"status": "registered", "device_id": reg.device_id, "cluster_version": state.version}


@router.post("/devices/heartbeat", response_model=Dict[str, Any])
async def heartbeat(req: HeartbeatRequest) -> Dict[str, Any]:
    """Records a heartbeat pulse for an edge device."""
    success = await sync_manager.record_heartbeat(req.device_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Device '{req.device_id}' not found.")
    return {"status": "ok", "device_id": req.device_id}
