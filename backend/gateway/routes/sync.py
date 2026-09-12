"""VESPER REST Endpoints for Cross-Device Synchronization.

Allows HTTP/REST-only edge devices or web apps to read snapshots, register presence,
and submit state diffs without maintaining a continuous WebSocket connection.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.sync.models import DeviceRegistration, SynchronizedState
from backend.sync.sync_manager import sync_manager

logger = logging.getLogger("vesper.gateway.routes.sync")
router = APIRouter(prefix="/sync", tags=["sync"])


class StateUpdateRequest(BaseModel):
    diff: Dict[str, Any]
    source_device_id: str = "rest_client"


class HeartbeatRequest(BaseModel):
    device_id: str


@router.get("/state", response_model=Dict[str, Any])
@router.get("/snapshot", response_model=Dict[str, Any])
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
    """Returns list of currently active online devices with battery telemetry and deduplication."""
    # Evict only unverified ARP neighbor entries from legacy scans
    for k in list(sync_manager.state.active_devices.keys()):
        if k.startswith("mobile_192_168_"):
            del sync_manager.state.active_devices[k]

    active = sync_manager.get_active_devices()

    # Query real battery status on host machine
    batt = None
    try:
        import psutil
        batt = psutil.sensors_battery()
    except Exception:
        pass

    # Update host device with latest real battery and CPU metrics
    host_found = False
    for d in active:
        if d.device_id == "vesper-host-workstation":
            host_found = True
            if batt:
                d.battery_level = round(batt.percent)
                d.is_charging = batt.power_plugged

    # If host workstation is not registered yet, instantiate it
    if not host_found:
        try:
            from backend.vision.device_probe import DeviceProbe
            caps = DeviceProbe.get_capabilities()
            host_dev = DeviceRegistration(
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
            await sync_manager.register_device(host_dev)
            active.insert(0, host_dev)
        except Exception as e:
            logger.warning(f"[SYNC] Failed to create host device: {e}")

    # Filter out provisioned placeholder and any offline devices
    active = [
        d for d in active
        if d.device_id != "mobile_companion_provisioned" and d.is_online
    ]

    # Deduplicate devices by device_id and device_name
    seen_ids = set()
    seen_names = set()
    deduped: List[DeviceRegistration] = []
    for d in active:
        if d.device_id in seen_ids or d.device_name in seen_names:
            continue
        seen_ids.add(d.device_id)
        seen_names.add(d.device_name)
        deduped.append(d)

    return deduped


@router.post("/devices/register", response_model=Dict[str, Any])
async def register_device(reg: DeviceRegistration) -> Dict[str, Any]:
    """Registers an edge device into the cluster."""
    state = await sync_manager.register_device(reg)
    return {"status": "registered", "device_id": reg.device_id, "cluster_version": state.version}


@router.get("/devices/heartbeat", response_model=Dict[str, Any])
@router.post("/devices/heartbeat", response_model=Dict[str, Any])
async def heartbeat(req: HeartbeatRequest) -> Dict[str, Any]:
    """Records a heartbeat pulse for an edge device."""
    success = await sync_manager.record_heartbeat(req.device_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Device '{req.device_id}' not found.")
    return {"status": "ok", "device_id": req.device_id}


@router.get("/profile", response_model=DeviceRegistration)
async def get_gateway_profile() -> DeviceRegistration:
    """Returns the host workstation gateway hardware and capability profile."""
    from backend.vision.device_probe import DeviceProbe
    caps = DeviceProbe.get_capabilities()
    batt = None
    try:
        import psutil
        batt = psutil.sensors_battery()
    except Exception:
        pass

    return DeviceRegistration(
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
        registered_at=time.time(),
        last_heartbeat=time.time(),
        is_online=True,
    )



@router.post("/scan", response_model=Dict[str, Any])
@router.get("/scan", response_model=Dict[str, Any])
async def scan_network_devices() -> Dict[str, Any]:
    """Triggers an active subnet sweep to discover and register VESPER edge nodes."""
    from backend.sync.network_scanner import network_scanner
    discovered = await network_scanner.scan_subnet(auto_register=True)
    snapshot = sync_manager.get_state_snapshot()
    allocations = {dev.device_id: dev.assigned_roles for dev in snapshot.active_devices.values()}
    return {
        "status": "scan_complete",
        "discovered_count": len(discovered),
        "discovered_devices": [d.model_dump() for d in discovered],
        "active_devices": [d.model_dump() for d in sync_manager.get_active_devices()],
        "cluster_role_allocations": allocations,
        "cluster_version": snapshot.version,
    }


@router.get("/proactive/actions/recent", response_model=Dict[str, Any])
async def get_recent_proactive_action(max_age: float = 180.0) -> Dict[str, Any]:
    """Returns the most recently prompted proactive action awaiting confirmation."""
    from backend.agent.proactive.action_queue import action_queue
    act = action_queue.get_recent_prompted_action(max_age_sec=max_age)
    if not act:
        active = action_queue.get_active_actions()
        if active:
            act = active[0]
    if act:
        return {"found": True, "action": act.model_dump()}
    return {"found": False, "action": None}


@router.get("/proactive/actions/active", response_model=List[Dict[str, Any]])
async def get_active_proactive_actions(domain: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns active staged proactive actions."""
    from backend.agent.proactive.action_queue import action_queue
    acts = action_queue.get_active_actions(domain=domain)
    return [a.model_dump() for a in acts]


@router.post("/proactive/actions/{action_id}/resolve", response_model=Dict[str, Any])
async def resolve_proactive_action(action_id: str, new_status: str, confirmed_by: str = "voice") -> Dict[str, Any]:
    """Resolves a staged proactive action across the cluster, executing it upon confirmation."""
    from backend.agent.proactive.action_queue import action_queue
    from backend.agent.proactive.audit_logger import audit_logger

    res = action_queue.resolve_action(action_id, resolution=new_status, confirmed_by=confirmed_by)
    if res:
        exec_result: Optional[Dict[str, Any]] = None
        if new_status.lower() in ("confirmed", "confirm"):
            try:
                from backend.agent.registry import registry
                spec_res = await registry.execute_action(
                    agent_name=res.domain,
                    action=res.action,
                    params=res.params,
                )
                exec_result = {
                    "success": spec_res.success,
                    "action": spec_res.action,
                    "data": spec_res.data,
                    "speech": spec_res.speech_summary,
                    "error": spec_res.error,
                }
                logger.info(f"[SyncRouter] Executed confirmed staged action '{action_id}' ({res.domain}:{res.action}): {exec_result}")
            except Exception as e:
                logger.error(f"[SyncRouter] Error executing confirmed staged action '{action_id}': {e}", exc_info=True)
                exec_result = {"success": False, "error": str(e)}

            audit_logger.log_action(res, confirmed_by=confirmed_by)

        return {
            "success": True,
            "action": res.model_dump(),
            "execution": exec_result,
        }
    return {"success": False, "error": f"Action '{action_id}' not found"}

