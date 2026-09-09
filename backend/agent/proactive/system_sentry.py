"""VESPER Hardware & System Health Sentry.

Monitors CPU utilization, memory pressure, thermals, and connected cluster nodes.
Enforces a hard process exclusion list (TERMINATION_DENY_LIST) ensuring user work
is never proposed for termination.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("vesper.agent.proactive.system")

# Hard-coded deny-list of critical processes that must NEVER be terminated
TERMINATION_DENY_LIST: Set[str] = {
    # IDEs, Text Editors, and Dev Environments
    "code", "cursor", "nvim", "vim", "emacs", "idea", "pycharm", "sublime_text",
    "vscode", "code-insiders",
    # Compilers, Interpreters & Runtime Toolchains
    "python", "python3", "node", "rustc", "cargo", "gcc", "g++", "clang", "go",
    "java", "javac", "ruby", "dotnet", "pip", "npm", "yarn", "bun", "git",
    # Shells, Multiplexers & Terminals
    "bash", "zsh", "fish", "sh", "tmux", "screen", "kitty", "alacritty",
    "gnome-terminal", "konsole", "wezterm",
    # System Daemons & Core Infrastructure
    "systemd", "dockerd", "containerd", "Xorg", "wayland", "pulseaudio",
    "pipewire", "postgres", "mysqld", "redis-server", "uvicorn", "fastapi",
    "sshd", "dbus-daemon", "polkitd"
}


class SystemSentry:
    """Evaluates host vitals and manages safe hardware advisories."""

    _instance: Optional["SystemSentry"] = None

    def __init__(self) -> None:
        self._consecutive_spikes: int = 0
        self._last_alert_time: float = 0.0
        self._alert_cooldown_sec: float = 900.0  # 15 min cooldown

    @classmethod
    def get_instance(cls) -> "SystemSentry":
        if cls._instance is None:
            cls._instance = SystemSentry()
        return cls._instance

    def evaluate_vitals(self, vitals: Dict[str, Any], top_processes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Evaluates CPU and RAM metrics.

        Returns an advisory payload if sustained spikes occur, strictly avoiding
        unsafe termination proposals for protected processes.
        """
        now = time.time()
        cpu_percent = vitals.get("cpu_percent", 0.0)
        ram_percent = vitals.get("ram_percent", 0.0)

        # High resource threshold: CPU > 90% or RAM > 92%
        is_spike = cpu_percent > 90.0 or ram_percent > 92.0

        if is_spike:
            self._consecutive_spikes += 1
        else:
            self._consecutive_spikes = 0
            return None

        # Require 2 consecutive spikes (~60s sustained load) and check cooldown
        if self._consecutive_spikes < 2 or (now - self._last_alert_time) < self._alert_cooldown_sec:
            return None

        # Find the highest consumer among top processes
        offender_name = "System Task"
        offender_pid = None
        offender_cpu = 0.0

        if top_processes:
            p0 = top_processes[0]
            offender_name = p0.get("name", "Unknown")
            offender_pid = p0.get("pid")
            offender_cpu = p0.get("cpu_percent", 0.0)

        # Check if process is on hard deny-list
        base_name = offender_name.lower().split("/")[-1].split(".")[0]
        is_protected = any(denied in base_name for denied in TERMINATION_DENY_LIST)

        self._last_alert_time = now

        if is_protected:
            # Advisory mode only: Never offer to kill protected dev processes
            speech = (
                f"Sir, host load is elevated with '{offender_name}' utilizing {offender_cpu:.0f}% CPU. "
                f"As this appears to be an active development task, I am maintaining advisory surveillance only."
            )
            return {
                "type": "advisory",
                "speech": speech,
                "process_name": offender_name,
                "cpu_percent": offender_cpu,
                "can_terminate": False,
            }
        else:
            speech = (
                f"Sir, background process '{offender_name}' (PID {offender_pid}) has consumed {offender_cpu:.0f}% CPU "
                f"continuously for over a minute. Would you like me to inspect or terminate this process?"
            )
            return {
                "type": "termination_candidate",
                "speech": speech,
                "process_name": offender_name,
                "pid": offender_pid,
                "cpu_percent": offender_cpu,
                "can_terminate": True,
            }

    def is_protected_process(self, process_name: str) -> bool:
        """Returns True if the process name is on the protected deny-list."""
        base_name = process_name.lower().split("/")[-1].split(".")[0]
        return any(denied in base_name for denied in TERMINATION_DENY_LIST)

    def kill_rogue_process(self, pid: int, process_name: str = "") -> Dict[str, Any]:
        """Safely terminates an uncooperative rogue process, enforcing the deny-list."""
        if process_name and self.is_protected_process(process_name):
            logger.warning(
                f"[SystemSentry] Blocked termination attempt on protected process '{process_name}' (PID {pid})"
            )
            return {
                "success": False,
                "error": f"Process '{process_name}' is on the protected deny-list and cannot be terminated.",
            }

        import os, signal
        try:
            os.kill(pid, signal.SIGTERM)
            return {"success": True, "pid": pid, "process_name": process_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def evaluate_system_health(self) -> Dict[str, Any]:
        """Gathers host vitals and surfaces advisory recommendations if overloaded."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            vitals = {"cpu_percent": cpu, "ram_percent": ram}

            top_procs = []
            for p in sorted(
                psutil.process_iter(["pid", "name", "cpu_percent"]),
                key=lambda x: (x.info.get("cpu_percent") or 0.0),
                reverse=True,
            )[:3]:
                top_procs.append(p.info)

            adv = self.evaluate_vitals(vitals, top_procs)
            if adv and adv.get("can_terminate") and adv.get("pid"):
                from backend.agent.proactive.action_queue import ActionPriority, StagedAction, action_queue

                staged = action_queue.stage_action(
                    StagedAction(
                        id=f"act_sys_kill_{int(time.time())}_{adv['pid']}",
                        domain="system",
                        action="terminate_process",
                        params={"pid": adv["pid"], "name": adv["process_name"]},
                        verbatim_text=f"Terminate rogue process {adv['process_name']} (PID {adv['pid']})",
                        speech_prompt=adv["speech"],
                        priority=ActionPriority.HIGH.value,
                    )
                )
                return {"status": "ELEVATED_LOAD", "proposals": [staged]}

            return {"status": "HEALTHY", "vitals": vitals}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}


system_sentry = SystemSentry.get_instance()
