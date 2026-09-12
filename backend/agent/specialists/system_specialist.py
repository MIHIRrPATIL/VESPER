"""VESPER System Specialist Agent.

Manages Arch Linux OS hardware vitals, process resource consumption queries,
and PipeWire/PulseAudio audio sink and volume controls on mihir-arch.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional
import psutil

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.vision.gesture_service import (
    _get_system_volume,
    _set_system_mute,
    _set_system_volume,
)

logger = logging.getLogger("vesper.agent.specialists.system")


class SystemSpecialist(BaseSpecialist):
    """Specialist agent for hardware telemetry, process monitoring, and native audio controls."""

    def __init__(self) -> None:
        self._pactl_bin = shutil.which("pactl")

    @property
    def name(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return "Monitors hardware vitals (CPU, RAM, thermals, processes) and controls system volume and audio sinks on Arch Linux."

    def get_capabilities(self) -> str:
        return (
            "Inspect live CPU and memory utilization, detect resource-heavy processes, "
            "adjust system volume, mute/unmute audio, and list or switch audio output devices."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_system_vitals",
                "description": "Retrieves real-time CPU %, RAM usage, disk space, and battery/thermal metrics.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "get_top_processes",
                "description": "Identifies the top processes consuming the most CPU or RAM.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sort_by": {"type": "string", "enum": ["cpu", "memory"], "description": "Sort criterion."},
                        "limit": {"type": "integer", "description": "Number of processes (default 5)."},
                    },
                },
            },
            {
                "name": "query_process",
                "description": "Checks resource consumption (CPU and RAM) for a specific application or process.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the process or app (e.g. 'chrome', 'docker', 'python')."},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "set_volume",
                "description": "Sets master system audio volume (0% to 100%).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "volume_percent": {"type": "integer", "description": "Target volume percentage (0-100)."},
                    },
                    "required": ["volume_percent"],
                },
            },
            {
                "name": "set_mute",
                "description": "Mutes or unmutes master audio output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mute": {"type": "boolean", "description": "True to mute, False to unmute."},
                    },
                    "required": ["mute"],
                },
            },
            {
                "name": "list_audio_sinks",
                "description": "Lists available audio output devices (speakers, headphones, HDMI, Bluetooth).",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "scan_network_devices",
                "description": "Performs an active subnet sweep to discover connected VESPER edge nodes (Orange Pi, Raspberry Pi, mobile HUD) and automatically re-allocate cluster roles.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "check_battery_status",
                "description": "Reports the battery level and charging state for all connected devices (phone, laptop, edge nodes). Shows whether each device is charging and if any alerts are active.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "set_screen_power",
                "description": "Controls display power management (DPMS) to turn monitors off (sleep screen) or turn them back on without locking session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "string",
                            "enum": ["off", "on", "toggle"],
                            "description": "Target screen state: 'off' to turn displays off/sleep screen, 'on' to wake displays, 'toggle' to toggle.",
                        },
                    },
                    "required": ["state"],
                },
            },
            {
                "name": "lock_session",
                "description": "Locks the current desktop session securely (triggers hyprlock/loginctl).",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    # ── Hardware Telemetry (<5ms) ─────────────────────────────────────────────

    def _collect_vitals(self) -> Dict[str, Any]:
        """Collects CPU, RAM, Disk, Battery, and Hardware telemetry synchronously."""
        cpu_pct = psutil.cpu_percent(interval=0.1)
        vmem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        battery = psutil.sensors_battery()

        # Hardware models (CPU & GPU)
        cpu_model = ""
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            cpu_model = "Intel/AMD Multi-core Processor"

        gpu_model = ""
        try:
            lspci_out = subprocess.check_output(["lspci"], text=True, timeout=1.0)
            for line in lspci_out.splitlines():
                if "vga compatible controller" in line.lower() or "3d controller" in line.lower():
                    parts = line.split(":", 2)
                    gpu_model = parts[-1].strip() if len(parts) >= 3 else line.strip()
                    break
        except Exception:
            gpu_model = "Integrated Graphics"

        # Thermals
        temps = {}
        try:
            raw_temps = psutil.sensors_temperatures()
            for name, entries in raw_temps.items():
                if entries:
                    temps[name] = round(entries[0].current, 1)
        except Exception:
            pass

        return {
            "cpu_percent": cpu_pct,
            "hardware": {
                "cpu_model": cpu_model,
                "cpu_cores": psutil.cpu_count(logical=True),
                "gpu_model": gpu_model,
            },
            "ram": {
                "used_gb": round(vmem.used / (1024**3), 2),
                "total_gb": round(vmem.total / (1024**3), 2),
                "percent": vmem.percent,
            },
            "disk": {
                "used_gb": round(disk.used / (1024**3), 1),
                "total_gb": round(disk.total / (1024**3), 1),
                "percent": disk.percent,
            },
            "battery": {
                "percent": battery.percent if battery else None,
                "power_plugged": battery.power_plugged if battery else None,
            } if battery else None,
            "temperatures": temps,
        }

    async def get_system_vitals(self) -> SpecialistResult:
        """Retrieves system vitals and formats a butler response."""
        vitals = await asyncio.to_thread(self._collect_vitals)

        cpu = vitals["cpu_percent"]
        ram_pct = vitals["ram"]["percent"]
        ram_used = vitals["ram"]["used_gb"]
        ram_total = vitals["ram"]["total_gb"]
        hw = vitals.get("hardware", {})
        cpu_name = hw.get("cpu_model") or "CPU"
        gpu_name = hw.get("gpu_model") or "GPU"

        speech = (
            f"Your laptop is powered by a {cpu_name} with {ram_total:.0f} gigabytes of RAM "
            f"and {gpu_name}. Current CPU load is {cpu}%, with {ram_used:.1f} GB memory in use."
        )

        return SpecialistResult(
            success=True,
            action="get_system_vitals",
            data=vitals,
            speech_summary=speech,
            card_payload={
                "type": "system_vitals_card",
                "cpu_model": cpu_name,
                "gpu_model": gpu_name,
                "cpu_percent": cpu,
                "ram_percent": ram_pct,
                "ram_used_gb": ram_used,
                "ram_total_gb": ram_total,
                "disk_percent": vitals["disk"]["percent"],
                "battery": vitals.get("battery"),
            },
        )

    # ── Process Telemetry ────────────────────────────────────────────────────

    def _collect_top_processes(self, sort_by: str = "cpu", limit: int = 5) -> List[Dict[str, Any]]:
        """Finds top processes consuming the most resources."""
        processes = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info"]):
            try:
                info = p.info
                # Calculate MB
                mem_mb = round(info["memory_info"].rss / (1024 * 1024), 1) if info.get("memory_info") else 0.0
                processes.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": info.get("cpu_percent") or 0.0,
                    "memory_percent": round(info.get("memory_percent") or 0.0, 1),
                    "memory_mb": mem_mb,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
        return sorted(processes, key=lambda x: x.get(key) or 0.0, reverse=True)[:limit]

    async def get_top_processes(self, sort_by: str = "cpu", limit: int = 5) -> SpecialistResult:
        """Reports the highest resource-consuming processes."""
        procs = await asyncio.to_thread(self._collect_top_processes, sort_by, limit)
        if not procs:
            return SpecialistResult(success=True, action="get_top_processes", speech_summary="No active processes detected, sir.")

        names = [f"{p['name']} ({p['cpu_percent']}% CPU, {p['memory_mb']}MB RAM)" for p in procs[:3]]
        speech = f"The primary processes consuming resources are {', '.join(names)}, sir."

        return SpecialistResult(
            success=True,
            action="get_top_processes",
            data={"processes": procs, "sort_by": sort_by},
            speech_summary=speech,
            card_payload={"type": "top_processes_card", "sort_by": sort_by, "processes": procs},
        )

    def _query_single_process(self, name: str) -> List[Dict[str, Any]]:
        """Queries resource consumption for processes matching name."""
        matches = []
        name_lower = name.lower()
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info"]):
            try:
                if name_lower in p.info["name"].lower():
                    info = p.info
                    mem_mb = round(info["memory_info"].rss / (1024 * 1024), 1) if info.get("memory_info") else 0.0
                    matches.append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu_percent": info.get("cpu_percent") or 0.0,
                        "memory_mb": mem_mb,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return matches

    async def query_process(self, name: str) -> SpecialistResult:
        """Inspects resource usage of a specific application."""
        matches = await asyncio.to_thread(self._query_single_process, name)
        if not matches:
            return SpecialistResult(
                success=True,
                action="query_process",
                data={"found": False, "process": name},
                speech_summary=f"I found no active processes matching '{name}' on your system, sir.",
                card_payload={"type": "process_query_card", "found": False, "name": name},
            )

        total_cpu = sum(p["cpu_percent"] for p in matches)
        total_mem = sum(p["memory_mb"] for p in matches)
        count = len(matches)

        speech = (
            f"Found {count} instances of '{name}'. "
            f"Combined resource usage is {total_cpu:.1f}% CPU and {total_mem:.1f} megabytes of RAM, sir."
        )

        return SpecialistResult(
            success=True,
            action="query_process",
            data={"found": True, "name": name, "instances": count, "total_cpu": total_cpu, "total_mem_mb": total_mem},
            speech_summary=speech,
            card_payload={"type": "process_query_card", "found": True, "name": name, "instances": count, "cpu": total_cpu, "memory_mb": total_mem},
        )

    # ── PulseAudio / PipeWire Audio Controls ─────────────────────────────────

    def _run_pactl(self, args: List[str]) -> str:
        """Executes pactl command safely."""
        if not self._pactl_bin:
            return ""
        try:
            res = subprocess.run([self._pactl_bin] + args, capture_output=True, text=True, timeout=2.0)
            return res.stdout.strip()
        except Exception as e:
            logger.warning(f"[System:pactl] Error running pactl {args}: {e}")
            return ""

    async def set_volume(self, volume_percent: int) -> SpecialistResult:
        """Sets master output volume (0-100)."""
        pct = max(0, min(100, volume_percent))
        await asyncio.to_thread(_set_system_volume, pct)

        return SpecialistResult(
            success=True,
            action="set_volume",
            data={"volume": pct},
            speech_summary=f"Master volume adjusted to {pct}%, sir.",
            card_payload={"type": "volume_card", "volume": pct},
        )

    async def set_mute(self, mute: bool) -> SpecialistResult:
        """Mutes or unmutes system audio output."""
        await asyncio.to_thread(_set_system_mute, mute)
        state = "muted" if mute else "unmuted"

        return SpecialistResult(
            success=True,
            action="set_mute",
            data={"muted": mute},
            speech_summary=f"System audio {state}, sir.",
            card_payload={"type": "mute_card", "muted": mute},
        )

    async def list_audio_sinks(self) -> SpecialistResult:
        """Lists connected audio output sinks."""
        out = await asyncio.to_thread(self._run_pactl, ["list", "short", "sinks"])
        sinks = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                sinks.append({"id": parts[0], "name": parts[1]})

        if not sinks:
            sinks = [{"id": "0", "name": "Default Audio Device"}]

        sink_names = ", ".join([s["name"].split(".")[-1] for s in sinks[:3]])
        speech = f"Available audio sinks include: {sink_names}, sir."

        return SpecialistResult(
            success=True,
            action="list_audio_sinks",
            data={"sinks": sinks},
            speech_summary=speech,
            card_payload={"type": "audio_sinks_card", "sinks": sinks},
        )

    # ── Display & Screen Power Management (DPMS) ─────────────────────────────

    def _run_dpms_control(self, state: str) -> bool:
        """Dispatches display power management state (Hyprland / wlopm / xset) safely."""
        if state == "on":
            try:
                from backend.vision.display_sentry import turn_display_on
                return turn_display_on(recover_caelestia=True)
            except Exception as e:
                logger.warning(f"[System:dpms] turn_display_on error: {e}")

        hyprctl = shutil.which("hyprctl")
        if hyprctl:
            try:
                # If turning off, give slight 0.8s lead time so audio/card dispatch starts cleanly
                if state == "off":
                    subprocess.Popen(["bash", "-c", "sleep 0.8 && hyprctl dispatch dpms off"])
                else:
                    subprocess.run([hyprctl, "dispatch", "dpms", state], capture_output=True, text=True, timeout=2.0)
                return True
            except Exception as e:
                logger.warning(f"[System:dpms] hyprctl error: {e}")

        wlopm = shutil.which("wlopm")
        if wlopm:
            try:
                action = "--off" if state == "off" else "--on"
                if state == "off":
                    subprocess.Popen(["bash", "-c", f"sleep 0.8 && wlopm {action} '*'"])
                else:
                    subprocess.run([wlopm, action, "*"], capture_output=True, text=True, timeout=2.0)
                return True
            except Exception:
                pass

        xset = shutil.which("xset")
        if xset:
            try:
                action = "off" if state == "off" else "on"
                if state == "off":
                    subprocess.Popen(["bash", "-c", f"sleep 0.8 && xset dpms force {action}"])
                else:
                    subprocess.run([xset, "dpms", "force", action], capture_output=True, text=True, timeout=2.0)
                return True
            except Exception:
                pass

        return False

    async def set_screen_power(self, state: str = "off") -> SpecialistResult:
        """Turns monitor displays off or on without session locking."""
        st = state.lower().strip()
        if st not in ("off", "on", "toggle"):
            st = "off"

        success = await asyncio.to_thread(self._run_dpms_control, st)
        if success:
            speech = "Turning off the display now, sir." if st == "off" else "Display powered on, sir."
            return SpecialistResult(
                success=True,
                action="set_screen_power",
                data={"screen_state": st},
                speech_summary=speech,
                card_payload={"type": "screen_power_card", "state": st},
            )
        else:
            speech = f"Unable to toggle display power to '{st}', sir."
            return SpecialistResult(
                success=False,
                action="set_screen_power",
                error=f"Display power manager failed for state '{st}'",
                speech_summary=speech,
            )

    def _run_lock_session(self) -> bool:
        """Invokes system session lock via loginctl or hyprlock."""
        try:
            res = subprocess.run(["loginctl", "lock-session"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                return True
        except Exception as e:
            logger.warning(f"[System:lock] loginctl failed: {e}")

        try:
            subprocess.Popen(["bash", "-c", "pidof hyprlock || hyprlock"])
            return True
        except Exception as e:
            logger.error(f"[System:lock] hyprlock fallback failed: {e}")
            return False

    async def lock_session(self) -> SpecialistResult:
        """Locks the desktop session securely."""
        success = await asyncio.to_thread(self._run_lock_session)
        if success:
            speech = "Locking the session now, sir."
            return SpecialistResult(
                success=True,
                action="lock_session",
                data={"locked": True},
                speech_summary=speech,
                card_payload={"type": "session_lock_card", "locked": True},
            )
        else:
            speech = "Unable to lock session, sir."
            return SpecialistResult(
                success=False,
                action="lock_session",
                error="Session lock command failed",
                speech_summary=speech,
            )


    # ── Battery Status (Cross-Device) ──────────────────────────────────────────

    async def check_battery_status(self) -> SpecialistResult:
        """Reports battery levels across all registered VESPER devices."""
        from backend.agent.proactive_agent import proactive_agent

        statuses = proactive_agent.get_all_device_battery_status()

        if not statuses:
            return SpecialistResult(
                success=True,
                action="check_battery_status",
                data={"devices": []},
                speech_summary="No devices with battery telemetry are currently registered in the cluster, sir.",
                card_payload={"type": "battery_status_card", "devices": []},
            )

        speech_parts = []
        for dev in statuses:
            if dev["battery_level"] is not None:
                charging_str = "and charging" if dev["is_charging"] else "and not charging"
                alert_str = " (alert active)" if dev.get("alert_active") else ""
                speech_parts.append(
                    f"{dev['device_name']} is at {dev['battery_level']}% {charging_str}{alert_str}"
                )
            else:
                speech_parts.append(f"{dev['device_name']} has no battery telemetry")

        speech = f"Battery status across your devices, sir: {'; '.join(speech_parts)}."

        return SpecialistResult(
            success=True,
            action="check_battery_status",
            data={"devices": statuses},
            speech_summary=speech,
            card_payload={"type": "battery_status_card", "devices": statuses},
        )

    # ── Network Device Discovery & Dynamic Role Allocation ───────────────────

    async def scan_network_devices(self) -> SpecialistResult:
        """Runs active subnet scan and returns discovery telemetry and new cluster role allocations."""
        from backend.sync.network_scanner import network_scanner
        from backend.sync.sync_manager import sync_manager

        discovered = await network_scanner.scan_subnet(auto_register=True)
        active = sync_manager.get_active_devices()
        allocations = {dev.device_id: dev.assigned_roles for dev in active}

        if not discovered:
            speech = f"Network scan completed, sir. No new edge nodes were discovered on the local subnet. {len(active)} active device(s) registered in cluster."
        else:
            names = [f"{d.device_name} ({d.ip_address})" for d in discovered]
            speech = f"Network scan completed, sir. Discovered {len(discovered)} active node(s): {', '.join(names)}. Cluster roles have been reallocated automatically."

        return SpecialistResult(
            success=True,
            action="scan_network_devices",
            data={
                "discovered_count": len(discovered),
                "discovered": [d.model_dump() for d in discovered],
                "active_devices": [d.model_dump() for d in active],
                "role_allocations": allocations,
            },
            speech_summary=speech,
            card_payload={
                "type": "network_discovery_card",
                "discovered": [d.model_dump() for d in discovered],
                "active_devices": [d.model_dump() for d in active],
                "role_allocations": allocations,
            },
        )

    # ── Execution Router ─────────────────────────────────────────────────────

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        act = action.lower().strip()

        # 1. Hardware vitals
        if act in ["get_system_vitals", "vitals", "status", "health", "specs"]:
            return await self.get_system_vitals()

        # 2. Process monitoring
        elif act in ["get_top_processes", "top_processes", "processes", "heavy_processes"]:
            sort = str(params.get("sort_by") or "cpu")
            lim = int(params.get("limit") or 5)
            return await self.get_top_processes(sort_by=sort, limit=lim)

        elif act in ["query_process", "check_process", "find_process", "app_usage"]:
            p_name = str(params.get("name") or params.get("process") or params.get("app") or "").strip()
            return await self.query_process(p_name)

        # 3. Volume & Mute Controls
        elif act in ["set_volume", "volume"]:
            vol = int(params.get("volume_percent") or params.get("volume") or 50)
            return await self.set_volume(vol)

        elif act in ["volume_up", "volume_down"]:
            delta = int(params.get("delta") or (10 if act == "volume_up" else -10))
            cur = _get_system_volume()
            new_vol = max(0, min(100, cur + delta))
            await asyncio.to_thread(_set_system_volume, new_vol)
            return SpecialistResult(
                success=True,
                action=act,
                data={"volume": new_vol, "delta": delta},
                speech_summary=f"Adjusted volume by {delta}%, now at {new_vol}%, sir.",
                card_payload={"type": "volume_card", "volume": new_vol, "delta": delta},
            )

        elif act in ["set_mute", "mute", "unmute"]:
            mute_state = True if act == "mute" else bool(params.get("mute", False))
            return await self.set_mute(mute_state)

        elif act in ["list_audio_sinks", "audio_sinks", "devices"]:
            return await self.list_audio_sinks()

        # 4. Display & Screen Power (DPMS)
        elif act in [
            "set_screen_power", "screen_power", "screen_off", "screen_on",
            "display_off", "display_on", "sleep_screen", "turn_off_screen",
            "turn_on_screen", "screen", "display", "dpms",
        ]:
            st = str(params.get("state") or ("off" if any(k in act for k in ["off", "sleep"]) else "on"))
            return await self.set_screen_power(st)

        # 4. Session Lock
        elif act in ["lock_session", "lock_screen", "lock", "screen_lock", "lock_system"]:
            return await self.lock_session()

        # 5. Network Discovery
        elif act in ["scan_network_devices", "scan_network", "discover_devices", "scan_devices"]:
            return await self.scan_network_devices()

        # 5. Battery Status (cross-device)
        elif act in ["check_battery_status", "battery_status", "battery", "check_battery", "device_battery"]:
            return await self.check_battery_status()

        # 6. Process Termination & Rogue Cleanup
        elif act in ["terminate_process", "kill_process", "kill_rogue_process", "stop_process"]:
            pid = params.get("pid")
            p_name = str(params.get("name") or params.get("process") or params.get("process_name") or "")
            if pid:
                try:
                    pid = int(pid)
                except ValueError:
                    pid = None
            if not pid and p_name:
                for p in psutil.process_iter(["pid", "name"]):
                    try:
                        if p_name.lower() in p.info["name"].lower():
                            pid = p.info["pid"]
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            if not pid:
                return SpecialistResult(
                    success=False,
                    action=act,
                    error=f"Could not identify running process '{p_name}' to terminate, sir.",
                    speech_summary=f"I could not locate active process '{p_name}', sir.",
                )
            from backend.agent.proactive.system_sentry import system_sentry
            res = system_sentry.kill_rogue_process(pid, p_name)
            if res.get("success"):
                speech = f"Process '{p_name or pid}' has been terminated, sir."
                return SpecialistResult(
                    success=True,
                    action=act,
                    data=res,
                    speech_summary=speech,
                    card_payload={"type": "process_terminated_card", "pid": pid, "process_name": p_name},
                )
            else:
                speech = f"Unable to terminate process '{p_name}': {res.get('error')}"
                return SpecialistResult(
                    success=False,
                    action=act,
                    error=res.get("error"),
                    speech_summary=speech,
                )

        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}' on system specialist.")
