"""VESPER Gateway Live Media Playback & Spotify REST Endpoints.

Provides live track metadata (artwork, title, artist, album, status) and
monochrome theme-synchronized playback controls via MPRIS / playerctl.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.vision.gesture_service import _control_media_player

logger = logging.getLogger("vesper.gateway.routes.media")
router = APIRouter(prefix="/api/media", tags=["Media"])


class MediaControlRequest(BaseModel):
    action: str  # "play-pause", "play", "pause", "next", "previous"


def _fetch_mpris_now_playing() -> Dict[str, Any]:
    """Queries playerctl for current track metadata and status."""
    playerctl = shutil.which("playerctl")
    if not playerctl:
        return {
            "title": "Player Unavailable",
            "artist": "Local Audio Sink",
            "album": "",
            "art_url": "",
            "is_playing": False,
            "status": "Stopped",
            "duration_ms": 0,
            "position_ms": 0,
        }

    try:
        # 1. Query playback status
        st_res = subprocess.run(
            [playerctl, "-p", "spotify,%any", "status"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        status = st_res.stdout.strip()
        if not status or st_res.returncode != 0:
            return {
                "title": "No Media Playing",
                "artist": "Spotify / Audio Sink",
                "album": "",
                "art_url": "",
                "is_playing": False,
                "status": "Stopped",
                "duration_ms": 0,
                "position_ms": 0,
            }

        is_playing = status.lower() == "playing"

        # 2. Query track metadata
        meta_res = subprocess.run(
            [playerctl, "-p", "spotify,%any", "metadata"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )

        metadata: Dict[str, str] = {}
        for line in meta_res.stdout.strip().split("\n"):
            parts = line.split(None, 2)
            if len(parts) == 3:
                _player, key, val = parts
                metadata[key] = val

        title = metadata.get("xesam:title", "Unknown Track")
        artist = metadata.get("xesam:artist") or metadata.get("xesam:albumArtist", "Unknown Artist")
        album = metadata.get("xesam:album", "")
        art_url = metadata.get("mpris:artUrl", "")

        # Handle file:// or local artwork path if present
        if art_url.startswith("file://"):
            art_url = art_url[7:]

        # Duration in microseconds
        duration_ms = 0
        raw_len = metadata.get("mpris:length")
        if raw_len and raw_len.isdigit():
            duration_ms = int(int(raw_len) / 1000)

        return {
            "title": title,
            "artist": artist,
            "album": album,
            "art_url": art_url,
            "is_playing": is_playing,
            "status": status,
            "duration_ms": duration_ms,
            "position_ms": 0,
        }

    except Exception as e:
        logger.debug(f"[Media] Error querying playerctl: {e}")
        return {
            "title": "No Media Playing",
            "artist": "Spotify / Audio Sink",
            "album": "",
            "art_url": "",
            "is_playing": False,
            "status": "Stopped",
            "duration_ms": 0,
            "position_ms": 0,
        }


@router.get("/now-playing")
async def get_now_playing() -> Dict[str, Any]:
    """Returns currently playing track metadata, artwork, and playback status."""
    return _fetch_mpris_now_playing()


@router.post("/control")
async def control_playback(req: MediaControlRequest, request: Request) -> Dict[str, Any]:
    """Executes media control action (play-pause, next, previous) and returns updated state."""
    action = req.action.lower().strip()
    if action in ("play-pause", "toggle", "play", "pause", "next", "previous", "prev"):
        _control_media_player(action, is_gesture=False)
        time.sleep(0.15)

    track_info = _fetch_mpris_now_playing()

    try:
        from backend.sync.sync_manager import sync_manager
        await sync_manager.update_state({"current_media": track_info}, source_device_id="media_endpoint")
    except Exception:
        pass

    try:
        conn_mgr = getattr(request.app.state, "connection_manager", None)
        if conn_mgr is not None:
            from backend.shared.events import Channel, EventType, ServerEnvelope
            import uuid
            env = ServerEnvelope(
                uuid=str(uuid.uuid4()),
                channel=Channel.SYSTEM,
                type=EventType.MEDIA_CONTROL,
                payload=track_info,
            )
            await conn_mgr.broadcast(env)
    except Exception:
        pass

    return track_info
