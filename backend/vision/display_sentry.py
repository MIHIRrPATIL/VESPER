"""VESPER Display Power Management & Presence Sentry Service.

Features:
1. Automated DPMS Power Management:
   - Queries real-time display status via `hyprctl monitors -j`.
   - Dispatches `hyprctl dispatch dpms off` and `hyprctl dispatch dpms on`.
   - Locks session via `hyprlock &` upon confirmed user absence.
2. Caelestia Service & Notification Badge Recovery:
   - Restarts Caelestia Quickshell instance (`qs -c caelestia -n -d`).
   - Ensures `dunst.service` remains inactive so Quickshell cleanly claims `org.freedesktop.Notifications`.
   - Verifies `caelestia resizer -d` daemon is running.
3. Dual-Loop Camera Presence Sentry (BlazeFace CPU):
   - Screen ON: Every 5 minutes, verifies user presence across 10 frames.
     If absent for 10 consecutive frames, locks screen and turns display off.
   - Screen OFF: Every 30 seconds, probes camera for 1 frame.
     If a human face is detected, verifies return across 10 consecutive frames (min 6 positive).
     If return confirmed, wakes display, restarts Caelestia services, and logs recovery.
4. Voice Wake Trigger:
   - Exposes `wake_by_voice()` to wake display from audio commands ("wake up", "hey jarvis").
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("vesper.vision.display_sentry")

MODEL_PATH = Path(__file__).resolve().parent / "models" / "blaze_face_short_range.tflite"


def _lock_windows() -> None:
    """Locks user session on Windows."""
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    except Exception as e:
        logger.warning(f"[DisplaySentry] Could not lock Windows workstation: {e}")


def _turn_display_off_windows() -> None:
    """Powers off monitors on Windows using SendMessage SC_MONITORPOWER."""
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SYSCOMMAND = 0x0112
        SC_MONITORPOWER = 0xF170
        ctypes.windll.user32.PostMessageA(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
    except Exception as e:
        logger.warning(f"[DisplaySentry] Could not power off Windows display via SendMessage: {e}")
        try:
            cmd = '(Add-Type \'[DllImport("user32.dll")]public static extern int SendMessage(int hWnd, int hMsg, int wParam, int lParam);\' -Name a -Passthru)::SendMessage(0xffff, 0x0112, 0xf170, 2)'
            subprocess.run(["powershell", "-Command", cmd], check=False, timeout=3)
        except Exception:
            pass


def _turn_display_on_windows() -> None:
    """Wakes monitors on Windows by posting input events and SC_MONITORPOWER -1."""
    try:
        import ctypes
        MOUSEEVENTF_MOVE = 0x0001
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, -1, 0, 0)

        HWND_BROADCAST = 0xFFFF
        WM_SYSCOMMAND = 0x0112
        SC_MONITORPOWER = 0xF170
        ctypes.windll.user32.PostMessageA(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, -1)
    except Exception as e:
        logger.warning(f"[DisplaySentry] Could not wake Windows display: {e}")


def _is_display_on_windows() -> bool:
    """Checks if desktop is accessible on Windows."""
    try:
        import ctypes
        hdesktop = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0001)
        if hdesktop == 0:
            return False
        ctypes.windll.user32.CloseDesktop(hdesktop)
        return True
    except Exception:
        return True


def is_display_on() -> bool:
    """Queries display power status across Linux (Hyprland / xset) and Windows."""
    if sys.platform == "win32":
        return _is_display_on_windows()

    try:
        if shutil.which("hyprctl"):
            res = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                monitors = json.loads(res.stdout)
                return any(m.get("dpmsStatus", False) for m in monitors)

        if shutil.which("xset"):
            res = subprocess.run(["xset", "q"], capture_output=True, text=True, timeout=2, check=False)
            if "Monitor is Off" in res.stdout:
                return False
            if "Monitor is On" in res.stdout:
                return True
    except Exception as e:
        logger.debug(f"[DisplaySentry] Error querying DPMS status: {e}")
    return True


_DISPLAY_STATE_FILE = Path("/tmp/vesper_display_state.json")
_SAVED_DISPLAY_STATE: Optional[Dict[str, Any]] = None


def _ensure_hyprland_env() -> None:
    """Auto-detects and exports Wayland and Hyprland instance variables if missing."""
    if not os.environ.get("XDG_RUNTIME_DIR"):
        uid = os.getuid()
        candidate = Path(f"/run/user/{uid}")
        if candidate.exists():
            os.environ["XDG_RUNTIME_DIR"] = str(candidate)

    xdg_runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))

    if not os.environ.get("WAYLAND_DISPLAY") and xdg_runtime.exists():
        for wayland_sock in sorted(xdg_runtime.glob("wayland-*")):
            if not wayland_sock.name.endswith(".lock"):
                os.environ["WAYLAND_DISPLAY"] = wayland_sock.name
                break

    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and xdg_runtime.exists():
        hypr_dir = xdg_runtime / "hypr"
        if hypr_dir.exists():
            signatures = [d.name for d in hypr_dir.iterdir() if d.is_dir()]
            if signatures:
                signatures.sort(key=lambda s: (hypr_dir / s).stat().st_mtime, reverse=True)
                os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = signatures[0]


def _clean_stale_quickshell_sockets() -> None:
    """Removes stale socket and PID entries from $XDG_RUNTIME_DIR/quickshell/ for dead PIDs."""
    try:
        xdg_runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        qs_dir = xdg_runtime / "quickshell"
        if not qs_dir.exists():
            return

        by_pid = qs_dir / "by-pid"
        if by_pid.exists():
            for pid_entry in by_pid.iterdir():
                try:
                    pid = int(pid_entry.name)
                    os.kill(pid, 0)
                except (ValueError, ProcessLookupError, PermissionError):
                    try:
                        if pid_entry.is_symlink() or pid_entry.is_file():
                            pid_entry.unlink()
                        elif pid_entry.is_dir():
                            shutil.rmtree(pid_entry, ignore_errors=True)
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"[DisplaySentry] Socket cleanup glitch: {e}")


def _probe_drm_connectors() -> List[str]:
    """Actively probes DRM sysfs connectors to wake DP AUX link and discover physical monitors."""
    connected: List[str] = []
    drm_path = Path("/sys/class/drm")
    if drm_path.exists():
        for status_file in drm_path.glob("card*-*/status"):
            try:
                status = status_file.read_text().strip()
                if status == "connected":
                    conn_name = status_file.parent.name.split("-", 1)[1]
                    connected.append(conn_name)
            except Exception:
                pass
    return connected


def _get_configured_monitor_names() -> List[str]:
    """Reads ~/.config/hypr/monitors.conf to know which monitors the user explicitly configured."""
    monitors: List[str] = []
    conf_path = Path.home() / ".config" / "hypr" / "monitors.conf"
    if conf_path.exists():
        try:
            for line in conf_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("monitor=") and "," in line:
                    name = line.split("=")[1].split(",")[0].strip()
                    if name and not name.startswith("fallback"):
                        monitors.append(name)
        except Exception:
            pass
    return monitors


def _get_expected_monitor_names() -> List[str]:
    """Returns all expected monitors, prioritizing physical DRM probes, saved state, and hyprland config."""
    saved = load_display_state()
    if saved and saved.get("monitors"):
        saved_names = [m["name"] for m in saved["monitors"] if m.get("name")]
        if saved_names:
            return saved_names

    probed = _probe_drm_connectors()
    if probed:
        return probed

    active = _get_active_monitor_names()
    if active:
        return active

    configured = _get_configured_monitor_names()
    return configured or ["eDP-1"]


def _get_active_monitor_names() -> List[str]:
    """Queries Hyprland for active monitor names (e.g. eDP-1)."""
    _ensure_hyprland_env()
    try:
        if shutil.which("hyprctl"):
            res = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                names = [m.get("name") for m in data if m.get("name") and not m.get("disabled")]
                if names:
                    return names
    except Exception:
        pass
    probed = _probe_drm_connectors()
    return probed or ["eDP-1"]


def save_display_state() -> Dict[str, Any]:
    """Captures and persists the exact live state of all active monitors, workspaces,
    focused window, and Caelestia status before display power down."""
    global _SAVED_DISPLAY_STATE
    _ensure_hyprland_env()

    state: Dict[str, Any] = {
        "timestamp": time.time(),
        "monitors": [],
        "active_workspace": None,
        "active_window": None,
        "caelestia_healthy": False,
        "drm_connected": _probe_drm_connectors(),
    }

    if shutil.which("hyprctl"):
        # 1. Capture monitors state
        try:
            m_res = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if m_res.returncode == 0 and m_res.stdout.strip():
                monitors_data = json.loads(m_res.stdout)
                if isinstance(monitors_data, list):
                    for m in monitors_data:
                        if not m.get("disabled", False):
                            state["monitors"].append({
                                "name": m.get("name"),
                                "id": m.get("id"),
                                "activeWorkspace": m.get("activeWorkspace", {}),
                                "focused": m.get("focused", False),
                                "dpmsStatus": m.get("dpmsStatus", True),
                                "width": m.get("width"),
                                "height": m.get("height"),
                                "refreshRate": m.get("refreshRate"),
                                "scale": m.get("scale", 1.0),
                                "transform": m.get("transform", 0),
                                "x": m.get("x", 0),
                                "y": m.get("y", 0),
                            })
        except Exception as e:
            logger.debug(f"[DisplaySentry] Failed to capture monitors state: {e}")

        # 2. Capture active workspace
        try:
            ws_res = subprocess.run(
                ["hyprctl", "activeworkspace", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if ws_res.returncode == 0 and ws_res.stdout.strip():
                state["active_workspace"] = json.loads(ws_res.stdout)
        except Exception as e:
            logger.debug(f"[DisplaySentry] Failed to capture active workspace: {e}")

        # 3. Capture active window
        try:
            win_res = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if win_res.returncode == 0 and win_res.stdout.strip():
                win_data = json.loads(win_res.stdout)
                if win_data.get("address"):
                    state["active_window"] = {
                        "address": win_data.get("address"),
                        "title": win_data.get("title"),
                        "class": win_data.get("class"),
                        "workspace": win_data.get("workspace", {}),
                    }
        except Exception as e:
            logger.debug(f"[DisplaySentry] Failed to capture active window: {e}")

    state["caelestia_healthy"] = is_caelestia_shell_healthy()

    _SAVED_DISPLAY_STATE = state
    try:
        _DISPLAY_STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.debug(f"[DisplaySentry] Failed to persist display state to file: {e}")

    mon_names = [m.get("name") for m in state["monitors"]]
    ws_id = state["active_workspace"].get("id") if state.get("active_workspace") else None
    logger.info(f"[DisplaySentry] Saved pre-sleep display state: monitors={mon_names}, workspace={ws_id}")
    return state


def load_display_state() -> Optional[Dict[str, Any]]:
    """Retrieves the last saved display state from memory or disk."""
    global _SAVED_DISPLAY_STATE
    if _SAVED_DISPLAY_STATE is not None:
        return _SAVED_DISPLAY_STATE

    if _DISPLAY_STATE_FILE.exists():
        try:
            data = json.loads(_DISPLAY_STATE_FILE.read_text())
            _SAVED_DISPLAY_STATE = data
            return data
        except Exception:
            pass
    return None


def restore_display_state(saved_state: Optional[Dict[str, Any]] = None) -> bool:
    """Restores saved monitor layout, workspaces, active windows, and focused displays upon wake."""
    if saved_state is None:
        saved_state = load_display_state()
    if not saved_state:
        logger.info("[DisplaySentry] No saved display state to restore.")
        return False

    _ensure_hyprland_env()
    if not shutil.which("hyprctl"):
        return False

    try:
        monitors = saved_state.get("monitors", [])
        logger.info(f"[DisplaySentry] Restoring saved display state for {len(monitors)} monitor(s)...")

        # 1. Restore each monitor's active workspace
        for m in monitors:
            m_name = m.get("name")
            ws = m.get("activeWorkspace", {})
            ws_id = ws.get("id")
            if m_name and ws_id:
                subprocess.run(
                    ["hyprctl", "dispatch", "focusmonitor", m_name],
                    check=False,
                    timeout=2,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                subprocess.run(
                    ["hyprctl", "dispatch", "workspace", str(ws_id)],
                    check=False,
                    timeout=2,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

        # 2. Refocus the monitor that was focused before sleep
        focused_mon = next((m.get("name") for m in monitors if m.get("focused")), None)
        if focused_mon:
            subprocess.run(
                ["hyprctl", "dispatch", "focusmonitor", focused_mon],
                check=False,
                timeout=2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # 3. Restore global active workspace if present
        act_ws = saved_state.get("active_workspace")
        if act_ws and act_ws.get("id"):
            subprocess.run(
                ["hyprctl", "dispatch", "workspace", str(act_ws["id"])],
                check=False,
                timeout=2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # 4. Restore focused active window if present
        act_win = saved_state.get("active_window")
        if act_win and act_win.get("address"):
            addr = act_win["address"]
            subprocess.run(
                ["hyprctl", "dispatch", "focuswindow", f"address:{addr}"],
                check=False,
                timeout=2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        logger.info("[DisplaySentry] Display workspaces and window focus restored to pre-sleep state.")
        return True
    except Exception as e:
        logger.warning(f"[DisplaySentry] Failed to restore display state: {e}")
        return False


def _wait_for_monitors_ready(timeout_sec: float = 2.5, expected_monitors: Optional[List[str]] = None) -> bool:
    """Waits for expected active monitors to complete DPMS wake and DRM modesetting."""
    if not shutil.which("hyprctl"):
        return True

    if expected_monitors:
        expected = set(expected_monitors)
    else:
        saved = load_display_state()
        if saved and saved.get("monitors"):
            expected = {m["name"] for m in saved["monitors"] if m.get("name")}
        else:
            probed = _probe_drm_connectors()
            expected = set(probed) if probed else set(_get_active_monitor_names())

    # Constrain expected set to physically connected DRM connectors to prevent timeouts on unplugged displays
    probed = set(_probe_drm_connectors())
    if probed:
        expected = expected.intersection(probed) or probed

    logger.info(f"[DisplaySentry] Waiting for monitors to complete link training: {list(expected)}")
    start_time = time.time()

    while time.time() - start_time < timeout_sec:
        _probe_drm_connectors()
        try:
            res = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                try:
                    monitors = json.loads(res.stdout)
                except Exception:
                    monitors = []

                if isinstance(monitors, list) and monitors:
                    awake_names = {
                        m.get("name")
                        for m in monitors
                        if m.get("name") and m.get("dpmsStatus", False) and not m.get("disabled", False)
                    }
                    if expected and expected.issubset(awake_names):
                        logger.info(f"[DisplaySentry] All target monitors confirmed awake: {list(awake_names)}")
                        time.sleep(0.3)
                        return True
                    elif not expected and awake_names:
                        time.sleep(0.3)
                        return True
        except Exception as e:
            logger.debug(f"[DisplaySentry] Monitor readiness probe glitch: {e}")

        time.sleep(0.2)

    logger.info("[DisplaySentry] Target monitors link training complete or best-effort proceed.")
    return True


def turn_display_off(lock: bool = True) -> bool:
    """Locks user session and powers off displays across Linux and Windows,
    saving the full state of monitors, workspaces, and windows beforehand."""
    try:
        if sys.platform == "win32":
            if lock:
                _lock_windows()
            _turn_display_off_windows()
            logger.info("[DisplaySentry] Display powered OFF (Windows standby engaged)")
            return True

        _ensure_hyprland_env()

        # 1. CRITICAL: Save exact state of all monitors, workspaces, and windows BEFORE sleeping
        save_display_state()

        # 2. Lock screen if requested
        if lock and shutil.which("hyprlock"):
            check = subprocess.run(["pidof", "hyprlock"], capture_output=True, text=True, check=False)
            if not check.stdout.strip():
                subprocess.Popen(
                    ["hyprlock"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=os.environ.copy(),
                )
                time.sleep(0.2)

        # 3. Power off monitors via DPMS
        if shutil.which("hyprctl"):
            subprocess.run(["hyprctl", "dispatch", "dpms", "off"], check=False, timeout=2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("[DisplaySentry] Display powered OFF (DPMS sleep engaged with saved state)")
            return True

        if shutil.which("xset"):
            subprocess.run(["xset", "dpms", "force", "off"], check=False, timeout=2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("[DisplaySentry] Display powered OFF (xset sleep engaged with saved state)")
            return True

        return True
    except Exception as e:
        logger.error(f"[DisplaySentry] Failed to power off display: {e}")
        return False


def is_caelestia_shell_healthy() -> bool:
    """Verifies that Quickshell process is alive AND Caelestia layer surfaces are mapped across active monitors in Hyprland."""
    try:
        _ensure_hyprland_env()
        # 1. Process check
        qs_check = subprocess.run(["pgrep", "-x", "qs"], capture_output=True, text=True, check=False)
        if not qs_check.stdout.strip():
            qs_check = subprocess.run(["pgrep", "-f", "qs -c caelestia"], capture_output=True, text=True, check=False)
        if not qs_check.stdout.strip():
            return False

        # 2. Hyprland layer-shell surface check across active monitors
        if shutil.which("hyprctl"):
            layers_res = subprocess.run(["hyprctl", "layers"], capture_output=True, text=True, timeout=2, check=False)
            if layers_res.returncode == 0:
                stdout = layers_res.stdout
                if not stdout.strip() or stdout.strip() == qs_check.stdout.strip():
                    return True

                probed = _probe_drm_connectors()
                active_monitors = probed or _get_active_monitor_names()
                if active_monitors and "Monitor " in stdout:
                    sections = stdout.split("Monitor ")
                    for m_name in active_monitors:
                        m_section = ""
                        for s in sections[1:]:
                            if s.startswith(m_name) or s.startswith(f"{m_name}:"):
                                m_section = s
                                break
                        if m_section:
                            if not any(ns in m_section for ns in ("caelestia-drawers", "caelestia-background", "caelestia-border-exclusion")):
                                logger.warning(f"[DisplaySentry] Monitor {m_name} is missing Caelestia layer surfaces")
                                return False
                    return True

                if any(ns in stdout for ns in ("caelestia-drawers", "caelestia-background", "caelestia-border-exclusion")):
                    return True
                return False
        return True
    except Exception:
        return False


def ensure_caelestia_running(force_restart: bool = False) -> None:
    """Ensures Caelestia Quickshell shell is active, refreshes display devices,
    and guarantees that the Caelestia resizer daemon is restarted synchronously whenever the shell restarts."""
    _ensure_hyprland_env()
    try:
        # 1. Ensure dunst remains inactive so Quickshell retains org.freedesktop.Notifications
        subprocess.run(
            ["systemctl", "--user", "stop", "dunst"],
            check=False,
            timeout=2,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        qs_restarted = False
        shell_healthy = is_caelestia_shell_healthy()

        if force_restart or not shell_healthy:
            logger.info("[DisplaySentry] Caelestia shell unhealthy or restart requested; cycling shell...")
            # 2. Clean shutdown of any existing Quickshell and resizer instances
            subprocess.run(
                ["caelestia", "shell", "-k"],
                check=False,
                timeout=2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["pkill", "-9", "-f", "caelestia resizer"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Grace period for graceful exit
            for _ in range(6):
                c = subprocess.run(["pgrep", "-x", "qs"], capture_output=True, text=True, check=False)
                if not c.stdout.strip():
                    break
                time.sleep(0.08)

            # Force kill if still lingering
            subprocess.run(["pkill", "-9", "-x", "qs"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "qs -c caelestia"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.1)

            # 3. Clean stale quickshell runtime sockets to prevent duplicate launch failures
            _clean_stale_quickshell_sockets()

            # 4. Launch Caelestia Quickshell cleanly with verified environment
            env = os.environ.copy()
            if shutil.which("hyprctl"):
                subprocess.run(
                    ["hyprctl", "dispatch", "exec", "caelestia shell -d"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["qs", "-c", "caelestia", "-n", "-d"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
            qs_restarted = True
            logger.info("[DisplaySentry] Caelestia shell launched")

            # CRITICAL TIMING BARRIER: Wait for Caelestia Shell to compile QML and create
            # its border-exclusion layer surfaces in Hyprland BEFORE starting the resizer.
            if shutil.which("hyprctl"):
                for _ in range(15):
                    time.sleep(0.2)
                    try:
                        chk = subprocess.run(["hyprctl", "layers"], capture_output=True, text=True, timeout=1, check=False)
                        if "caelestia-border-exclusion" in chk.stdout or "caelestia-drawers" in chk.stdout:
                            break
                    except Exception:
                        pass
            else:
                time.sleep(0.8)
        else:
            # Shell is healthy and running - refresh input devices non-destructively
            subprocess.run(
                ["caelestia", "shell", "hypr", "refreshDevices"],
                check=False,
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("[DisplaySentry] Caelestia shell confirmed healthy; refreshed via IPC (refreshDevices)")

        # 5. Synchronize / restart Caelestia resizer daemon
        resizer_check = subprocess.run(
            ["pgrep", "-f", "caelestia resizer"],
            capture_output=True,
            text=True,
            check=False,
        )
        resizer_pids = [p for p in resizer_check.stdout.strip().split() if p]

        if qs_restarted or not resizer_pids or len(resizer_pids) > 1:
            if resizer_pids:
                subprocess.run(
                    ["pkill", "-9", "-f", "caelestia resizer"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(0.1)

            if shutil.which("hyprctl"):
                subprocess.run(
                    ["hyprctl", "dispatch", "exec", "caelestia resizer -d"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["caelestia", "resizer", "-d"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=os.environ.copy(),
                )
            logger.info("[DisplaySentry] Caelestia resizer daemon restarted cleanly")

        logger.info("[DisplaySentry] Caelestia shell and resizer confirmed active and synchronized")
    except Exception as e:
        logger.warning(f"[DisplaySentry] Error during Caelestia service check: {e}")


# Retain alias for backward compatibility
restart_caelestia_services = ensure_caelestia_running


def turn_display_on(recover_caelestia: bool = True) -> bool:
    """Powers on displays across Linux (Hyprland / xset) and Windows,
    retrieving and restoring the exact pre-sleep state of monitors, workspaces, and Caelestia shell."""
    try:
        if sys.platform == "win32":
            _turn_display_on_windows()
            logger.info("[DisplaySentry] Display powered ON (Windows wake engaged)")
            return True

        _ensure_hyprland_env()

        if shutil.which("hyprctl"):
            saved = load_display_state()
            saved_monitors = [m["name"] for m in saved.get("monitors", [])] if saved else []

            # 1. Probe physical DRM connectors to wake DisplayPort AUX bus
            probed_connectors = _probe_drm_connectors()

            # Target monitors = physically connected monitors that were saved, or probed
            if saved_monitors:
                target_monitors = [m for m in saved_monitors if not probed_connectors or m in probed_connectors] or saved_monitors
            else:
                target_monitors = probed_connectors or _get_active_monitor_names()

            # 2. Dispatch global DPMS on
            subprocess.run(["hyprctl", "dispatch", "dpms", "on"], check=False, timeout=2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # 3. Explicitly wake target monitors
            for m_name in target_monitors:
                subprocess.run(["hyprctl", "dispatch", "dpms", "on", m_name], check=False, timeout=2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            logger.info(f"[DisplaySentry] Display powered ON (DPMS wake dispatched for {target_monitors})")

            # 4. Wait for target monitors to settle
            _wait_for_monitors_ready(timeout_sec=2.5, expected_monitors=target_monitors)

            # 5. RETRIEVE AND RESTORE exact monitor workspaces, layout, and focus!
            if saved:
                restore_display_state(saved)

            # 6. Verify and recover Caelestia Quickshell if needed (non-destructive if already healthy)
            if recover_caelestia:
                ensure_caelestia_running(force_restart=False)

            return True

        if shutil.which("xset"):
            subprocess.run(["xset", "dpms", "force", "on"], check=False, timeout=2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("[DisplaySentry] Display powered ON (xset wake engaged)")
            return True

        return True
    except Exception as e:
        logger.error(f"[DisplaySentry] Failed to power on display: {e}")
        return False


class BlazeFaceDetector:
    """High-speed offline face presence detector using MediaPipe Tasks API (BlazeFace CPU)."""

    def __init__(self, model_path: Optional[Path] = None, min_confidence: float = 0.35) -> None:
        self.model_path = model_path or MODEL_PATH
        self.min_confidence = min_confidence
        self._detector: Any = None
        self._init_failed = False

    def _get_detector(self) -> Any:
        if self._detector is not None or self._init_failed:
            return self._detector

        try:
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            if not self.model_path.exists():
                logger.warning(f"[BlazeFace] Model file not found at {self.model_path}")
                self._init_failed = True
                return None

            base_options = python.BaseOptions(model_asset_path=str(self.model_path))
            options = vision.FaceDetectorOptions(
                base_options=base_options,
                min_detection_confidence=self.min_confidence,
            )
            self._detector = vision.FaceDetector.create_from_options(options)
            logger.info("[BlazeFace] Loaded BlazeFace presence detector successfully")
            return self._detector
        except Exception as e:
            logger.warning(f"[BlazeFace] Failed to initialize FaceDetector: {e}")
            self._init_failed = True
            return None

    def detect(self, frame_bgr: np.ndarray) -> bool:
        """Detects whether at least one human face is visible in the given BGR frame."""
        detector = self._get_detector()
        if detector is None or frame_bgr is None:
            return False

        try:
            import mediapipe as mp

            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = detector.detect(mp_image)
            return bool(result.detections and len(result.detections) > 0)
        except Exception as e:
            logger.debug(f"[BlazeFace] Detection glitch: {e}")
            return False


class DisplaySentryService:
    """Asynchronous background sentry managing DPMS power, presence checks, and recovery."""

    def __init__(
        self,
        camera_index: int = 0,
        screen_on_interval: float = 300.0,    # 5 minutes check when screen is ON
        screen_off_interval: float = 2.5,     # 2.5 seconds probe when screen is OFF
        absence_frames: int = 10,             # 10 consecutive frames without human
        return_verify_frames: int = 5,        # 5 frames to verify return
        return_min_positives: int = 2,        # at least 2 positive detections = verified return
        on_state_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.camera_index = camera_index
        self.screen_on_interval = screen_on_interval
        self.screen_off_interval = screen_off_interval
        self.absence_frames = absence_frames
        self.return_verify_frames = return_verify_frames
        self.return_min_positives = return_min_positives
        self.on_state_change = on_state_change

        self.detector = BlazeFaceDetector()
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._last_on_check = time.time()
        self._last_user_activity = time.time()
        self._lock = asyncio.Lock()

    def notify_user_activity(self) -> None:
        """Registers recent user interaction (e.g. gesture or command) to prevent false absence locking."""
        self._last_user_activity = time.time()

    async def start(self) -> None:
        """Starts the background sentry supervisor loop."""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._sentry_loop())
        logger.info(
            f"[DisplaySentry] Started Sentry (OnCheck: {self.screen_on_interval}s, "
            f"OffProbe: {self.screen_off_interval}s)"
        )

    async def stop(self) -> None:
        """Stops the sentry supervisor loop cleanly."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[DisplaySentry] Stopped Sentry")

    async def wake_by_voice(self) -> bool:
        """Triggered by wake word or voice assistant command to wake display from sleep."""
        async with self._lock:
            display_active = await asyncio.to_thread(is_display_on)
            if not display_active:
                logger.info("[DisplaySentry] Voice wake trigger activated")
                woken = await asyncio.to_thread(turn_display_on, True)
                if woken and self.on_state_change:
                    try:
                        self.on_state_change("WAKE_VOICE")
                    except Exception:
                        pass
                return woken
            return True

    def _sample_camera_frames(self, num_frames: int, delay: float = 0.12) -> List[np.ndarray]:
        """Acquires num_frames from live shared RAM buffer or opens camera hardware cleanly."""
        frames: List[np.ndarray] = []

        # 1. Check if another service (e.g. GestureWorker or CameraHub) is actively streaming frames
        try:
            from backend.vision.camera_stream import get_shared_frame_path
            target_p = get_shared_frame_path()
            if target_p.exists() and (time.time() - target_p.stat().st_mtime) < 2.5:
                for _ in range(num_frames):
                    if target_p.exists():
                        raw_bytes = target_p.read_bytes()
                        if len(raw_bytes) > 1000:
                            nparr = np.frombuffer(raw_bytes, np.uint8)
                            f = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if f is not None:
                                frames.append(f)
                    time.sleep(delay)
                if len(frames) >= 1:
                    return frames
        except Exception as e:
            logger.debug(f"[DisplaySentry] Shared frame poll error: {e}")

        # 2. Acquire directly from camera hardware (fallback if shared memory not active)
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.debug(f"[DisplaySentry] Camera index {self.camera_index} could not be opened")
            return frames

        try:
            # Warm up sensor by reading 2 discarded frames
            for _ in range(2):
                cap.read()
            for _ in range(num_frames):
                ret, frame = cap.read()
                if ret and frame is not None:
                    frames.append(frame.copy())
                time.sleep(delay)
        finally:
            cap.release()

        return frames

    async def _sentry_loop(self) -> None:
        """Supervises display power state and performs periodic absence/presence detection."""
        while self.is_running:
            try:
                display_active = await asyncio.to_thread(is_display_on)

                if display_active:
                    # ── Screen is ON: Check for user absence every 5 minutes ─────────
                    await asyncio.sleep(min(5.0, self.screen_on_interval))
                    now = time.time()
                    if now - self._last_on_check >= self.screen_on_interval:
                        self._last_on_check = now

                        # If user recently interacted with gestures or system, they cannot be absent
                        if (now - self._last_user_activity) < 120.0:
                            logger.debug("[DisplaySentry] Recent user interaction within 120s; skipping absence check.")
                            continue

                        logger.info("[DisplaySentry] Executing desk presence check...")
                        frames = await asyncio.to_thread(
                            self._sample_camera_frames,
                            self.absence_frames,
                            0.12,
                        )

                        if len(frames) >= 5:
                            detected_count = sum(
                                1 for f in frames if self.detector.detect(f)
                            )
                            logger.info(
                                f"[DisplaySentry] Desk presence: {detected_count}/{len(frames)} frames with human detected"
                            )

                            # If 0 human detections, perform a confirmation check after a 6s grace window
                            if detected_count == 0:
                                logger.info("[DisplaySentry] No human detected in first sample. Confirming absence over 6s grace window...")
                                await asyncio.sleep(6.0)
                                if not self.is_running or not (await asyncio.to_thread(is_display_on)):
                                    continue
                                if (time.time() - self._last_user_activity) < 120.0:
                                    continue

                                confirm_frames = await asyncio.to_thread(
                                    self._sample_camera_frames,
                                    self.absence_frames,
                                    0.12,
                                )
                                confirm_count = sum(
                                    1 for f in confirm_frames if self.detector.detect(f)
                                )
                                if confirm_count == 0:
                                    logger.warning(
                                        f"[DisplaySentry] User absence confirmed across consecutive sample rounds. "
                                        "Engaging session lock and powering off display."
                                    )
                                    await asyncio.to_thread(turn_display_off, True)
                                    if self.on_state_change:
                                        try:
                                            self.on_state_change("ABSENT_LOCK")
                                        except Exception:
                                            pass
                        elif frames:
                            logger.warning(
                                f"[DisplaySentry] Insufficient camera sample frames ({len(frames)}/5) acquired. "
                                "Skipping absence lock check to avoid false lockouts."
                            )

                else:
                    # ── Screen is OFF: Probe camera every 2.5 seconds for return ───────
                    await asyncio.sleep(self.screen_off_interval)
                    if not self.is_running:
                        break

                    # Verify display is still off
                    if await asyncio.to_thread(is_display_on):
                        continue

                    logger.debug("[DisplaySentry] Screen is OFF. Probing camera for returning human...")
                    probes = await asyncio.to_thread(
                        self._sample_camera_frames, 2, 0.06
                    )

                    if probes and any(self.detector.detect(f) for f in probes):
                        logger.info(
                            f"[DisplaySentry] Potential human detected on return probe. "
                            f"Verifying over {self.return_verify_frames} consecutive frames..."
                        )

                        verify_frames = await asyncio.to_thread(
                            self._sample_camera_frames,
                            self.return_verify_frames,
                            0.08,
                        )

                        positive_count = sum(
                            1 for f in verify_frames if self.detector.detect(f)
                        )
                        logger.info(
                            f"[DisplaySentry] Verification result: {positive_count}/{len(verify_frames)} positive detections"
                        )

                        if positive_count >= self.return_min_positives:
                            logger.info(
                                "[DisplaySentry] User presence confirmed at desk! "
                                "Waking display and restoring Caelestia services."
                            )
                            await asyncio.to_thread(turn_display_on, True)
                            self._last_on_check = time.time()
                            self.notify_user_activity()
                            if self.on_state_change:
                                try:
                                    self.on_state_change("RETURN_WAKE")
                                except Exception:
                                    pass

            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.warning(f"[DisplaySentry] Error in sentry loop: {loop_err}")
                await asyncio.sleep(5.0)
