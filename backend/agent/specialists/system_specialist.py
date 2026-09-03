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
        ]

    # ── Hardware Telemetry (<5ms) ─────────────────────────────────────────────

    def _collect_vitals(self) -> Dict[str, Any]:
        """Collects CPU, RAM, Disk, and Battery telemetry synchronously."""
        cpu_pct = psutil.cpu_percent(interval=0.1)
        vmem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        battery = psutil.sensors_battery()

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

        speech = (
            f"Core vitals are optimal, sir. CPU utilization is currently at {cpu}%, "
            f"and memory consumption stands at {ram_used:.1f} of {ram_total:.1f} gigabytes ({ram_pct}%)."
        )

        return SpecialistResult(
            success=True,
            action="get_system_vitals",
            data=vitals,
            speech_summary=speech,
            card_payload={
                "type": "system_vitals_card",
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
        await asyncio.to_thread(self._run_pactl, ["set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"])

        return SpecialistResult(
            success=True,
            action="set_volume",
            data={"volume": pct},
            speech_summary=f"Master volume adjusted to {pct}%, sir.",
            card_payload={"type": "volume_card", "volume": pct},
        )

    async def set_mute(self, mute: bool) -> SpecialistResult:
        """Mutes or unmutes system audio output."""
        arg = "1" if mute else "0"
        await asyncio.to_thread(self._run_pactl, ["set-sink-mute", "@DEFAULT_SINK@", arg])
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
            sign = "+" if delta > 0 else ""
            await asyncio.to_thread(self._run_pactl, ["set-sink-volume", "@DEFAULT_SINK@", f"{sign}{delta}%"])
            return SpecialistResult(
                success=True,
                action=act,
                data={"delta": delta},
                speech_summary=f"Adjusted volume by {delta}%, sir.",
                card_payload={"type": "volume_card", "delta": delta},
            )

        elif act in ["set_mute", "mute", "unmute"]:
            mute_state = True if act == "mute" else bool(params.get("mute", False))
            return await self.set_mute(mute_state)

        elif act in ["list_audio_sinks", "audio_sinks", "devices"]:
            return await self.list_audio_sinks()

        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}' on system specialist.")
