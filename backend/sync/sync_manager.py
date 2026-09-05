"""VESPER Centralized State Synchronization Hub.

Maintains canonical state across all nodes in the ecosystem:
- Primary Arch Linux Workstation
- Edge Nodes (Orange Pi / Headless SBCs)
- Mobile Companions & Desk HUD

Ensures seamless state replication (audio volume, zen mode, media playback, device presence).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from backend.sync.models import DeviceRegistration, SynchronizedState

logger = logging.getLogger("vesper.sync.manager")


class SyncManager:
    """Manages cross-device state convergence, device heartbeats, and broadcast relays."""

    _instance: Optional["SyncManager"] = None

    def __init__(self) -> None:
        self.state = SynchronizedState()
        self._listeners: List[Callable[[SynchronizedState, Dict[str, Any]], Any]] = []
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "SyncManager":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = SyncManager()
        return cls._instance

    def add_listener(self, callback: Callable[[SynchronizedState, Dict[str, Any]], Any]) -> None:
        """Registers a listener callback invoked whenever cluster state updates."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[SynchronizedState, Dict[str, Any]], Any]) -> None:
        """Unregisters a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def get_snapshot(self) -> SynchronizedState:
        """Returns the current synchronized cluster state snapshot."""
        return self.state

    async def register_device(self, reg: DeviceRegistration) -> SynchronizedState:
        """Registers or updates a connected device's presence and hardware profile."""
        async with self._lock:
            reg.last_heartbeat = time.time()
            reg.is_online = True
            self.state.active_devices[reg.device_id] = reg
            self.state.version += 1
            self.state.updated_at = time.time()

            logger.info(
                f"[SyncManager] Registered device '{reg.device_id}' ({reg.device_type} - {reg.device_name}) | "
                f"Camera: {reg.has_camera} | Display: {reg.has_display} | CPU: {reg.cpu_cores}c | RAM: {reg.ram_available_gb}/{reg.ram_total_gb}GB"
            )
            self._reallocate_roles_sync()
            await self._notify_listeners({"device_registered": reg.device_id})
            return self.state

    async def record_heartbeat(self, device_id: str) -> bool:
        """Updates the heartbeat timestamp for a connected device."""
        async with self._lock:
            if device_id in self.state.active_devices:
                dev = self.state.active_devices[device_id]
                dev.last_heartbeat = time.time()
                dev.is_online = True
                return True
            return False

    async def update_state(
        self,
        diff: Dict[str, Any],
        source_device_id: str = "master",
    ) -> SynchronizedState:
        """Applies state changes and replicates them across all nodes."""
        async with self._lock:
            modified = False

            if "master_volume" in diff and isinstance(diff["master_volume"], int):
                clamped_vol = max(0, min(100, diff["master_volume"]))
                if self.state.master_volume != clamped_vol:
                    self.state.master_volume = clamped_vol
                    modified = True

            if "zen_mode" in diff and isinstance(diff["zen_mode"], bool):
                if self.state.zen_mode != diff["zen_mode"]:
                    self.state.zen_mode = diff["zen_mode"]
                    modified = True

            if "focus_mode" in diff and isinstance(diff["focus_mode"], bool):
                if self.state.focus_mode != diff["focus_mode"]:
                    self.state.focus_mode = diff["focus_mode"]
                    modified = True

            if "wakeword_active" in diff and isinstance(diff["wakeword_active"], bool):
                if self.state.wakeword_active != diff["wakeword_active"]:
                    self.state.wakeword_active = diff["wakeword_active"]
                    modified = True

            if "optical_sensor_active" in diff and isinstance(diff["optical_sensor_active"], bool):
                if self.state.optical_sensor_active != diff["optical_sensor_active"]:
                    self.state.optical_sensor_active = diff["optical_sensor_active"]
                    modified = True

            if "active_tasks_count" in diff and isinstance(diff["active_tasks_count"], int):
                self.state.active_tasks_count = diff["active_tasks_count"]
                modified = True

            if "current_media" in diff and isinstance(diff["current_media"], dict):
                self.state.current_media.update(diff["current_media"])
                modified = True

            if "last_speech_summary" in diff:
                self.state.last_speech_summary = str(diff["last_speech_summary"])
                modified = True

            if modified:
                self.state.version += 1
                self.state.updated_at = time.time()
                logger.info(
                    f"[SyncManager] State updated (v{self.state.version}) by '{source_device_id}': "
                    f"Vol={self.state.master_volume}% | Zen={self.state.zen_mode} | Focus={self.state.focus_mode}"
                )
                await self._notify_listeners(diff)

            return self.state

    def get_state_snapshot(self) -> SynchronizedState:
        """Returns the current state snapshot."""
        return self.state

    def get_active_devices(self) -> List[DeviceRegistration]:
        """Returns list of online devices."""
        return [dev for dev in self.state.active_devices.values() if dev.is_online]

    async def prune_stale_devices(self, timeout_sec: float = 30.0) -> List[str]:
        """Marks devices whose heartbeat timed out as offline."""
        now = time.time()
        pruned: List[str] = []
        async with self._lock:
            for dev_id, dev in self.state.active_devices.items():
                if dev.is_online and (now - dev.last_heartbeat) > timeout_sec:
                    dev.is_online = False
                    pruned.append(dev_id)
                    logger.warning(f"[SyncManager] Device '{dev_id}' heartbeat timed out; marked offline.")

            if pruned:
                self.state.version += 1
                self.state.updated_at = now
                self._reallocate_roles_sync()
                await self._notify_listeners({"devices_pruned": pruned})
        return pruned

    def _reallocate_roles_sync(self) -> Dict[str, List[str]]:
        """Synchronously invokes ClusterWorkloadAllocator to assign cluster roles."""
        try:
            from backend.sync.cluster_allocator import ClusterWorkloadAllocator
            return ClusterWorkloadAllocator.allocate_roles(self.state.active_devices)
        except Exception as e:
            logger.error(f"[SyncManager] Failed to allocate cluster roles: {e}", exc_info=True)
            return {}

    async def reallocate_cluster_roles(self) -> Dict[str, List[str]]:
        """Asynchronously triggers full cluster workload reallocation and notifies subscribers."""
        async with self._lock:
            allocs = self._reallocate_roles_sync()
            self.state.version += 1
            self.state.updated_at = time.time()
            await self._notify_listeners({"roles_reallocated": allocs})
            return allocs

    async def _notify_listeners(self, change_meta: Dict[str, Any]) -> None:
        """Invokes registered subscriber callbacks asynchronously."""
        for cb in self._listeners:
            try:
                res = cb(self.state, change_meta)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(f"[SyncManager] Error notifying state listener: {e}", exc_info=True)


# Global default sync manager instance
sync_manager = SyncManager.get_instance()
