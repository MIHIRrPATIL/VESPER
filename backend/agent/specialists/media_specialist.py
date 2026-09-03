"""VESPER Media Specialist Agent.

Provides dual-engine music and video capabilities:
  1. Spotify Web API (Live player control, user playlist browsing, track changes).
  2. SerpAPI YouTube Engine (Video/audio search, high-res thumbnails, direct watch URLs).
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import httpx

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.shared.config import (
    SERPAPI_API_KEY,
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
)

logger = logging.getLogger("vesper.agent.specialists.media")

SPOTIFY_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "credentials" / ".spotify_cache"


class MediaSpecialist(BaseSpecialist):
    """Specialist sub-agent for live Spotify playback control and SerpAPI YouTube discovery."""

    def __init__(
        self,
        serpapi_key: Optional[str] = None,
        spotify_client_id: Optional[str] = None,
        spotify_client_secret: Optional[str] = None,
    ) -> None:
        self.serpapi_key = serpapi_key or SERPAPI_API_KEY
        self.spotify_id = spotify_client_id or SPOTIFY_CLIENT_ID
        self.spotify_secret = spotify_client_secret or SPOTIFY_CLIENT_SECRET
        self._user_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return "Controls live Spotify playback (play song, playlists, pause/skip) and searches YouTube via SerpAPI."

    def get_capabilities(self) -> str:
        return (
            "Play specific songs or user playlists on Spotify, control playback (pause, resume, skip), "
            "and search for videos or music on YouTube via SerpAPI."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "play_track",
                "description": "Searches for a track or artist on Spotify and immediately changes the song on the user's active device.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Song name, artist, or album to play on Spotify."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "play_playlist",
                "description": "Plays a specific user playlist on Spotify (e.g. Focus Flow, Chill, Rock).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the playlist to play."},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "control_playback",
                "description": "Controls active media playback: pause, resume, next track, previous track.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["pause", "play", "resume", "next", "previous"],
                            "description": "Playback action to execute.",
                        }
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "search_youtube_video",
                "description": "Searches YouTube for videos, official music videos, live sets, or audio streams via SerpAPI.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for YouTube (song, artist, topic)."},
                        "max_results": {"type": "integer", "description": "Number of videos to return (default 3)."},
                    },
                    "required": ["query"],
                },
            },
        ]

    # ── Spotify User OAuth Token Refresh ─────────────────────────────────────

    async def _get_user_token(self) -> Optional[str]:
        """Retrieves and auto-refreshes user OAuth access token with playback control scopes."""
        if self._user_token and time.time() < self._token_expires_at - 60:
            return self._user_token

        if not SPOTIFY_CACHE_PATH.exists():
            logger.warning(f"[Media:Spotify] No .spotify_cache found at {SPOTIFY_CACHE_PATH}")
            return None

        try:
            with open(SPOTIFY_CACHE_PATH, "r") as f:
                cache = json.load(f)

            refresh_token = cache.get("refresh_token")
            if not refresh_token:
                logger.warning("[Media:Spotify] No refresh_token in .spotify_cache")
                return None

            auth_header = base64.b64encode(f"{self.spotify_id}:{self.spotify_secret}".encode()).decode()
            url = "https://accounts.spotify.com/api/token"
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }

            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, headers=headers, data=data)
                if res.status_code == 200:
                    token_data = res.json()
                    self._user_token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                    self._token_expires_at = time.time() + expires_in

                    # Update cache on disk
                    cache["access_token"] = self._user_token
                    cache["expires_at"] = int(self._token_expires_at)
                    if "refresh_token" in token_data:
                        cache["refresh_token"] = token_data["refresh_token"]
                    with open(SPOTIFY_CACHE_PATH, "w") as f:
                        json.dump(cache, f)

                    logger.info("[Media:Spotify] Successfully refreshed user access token.")
                    return self._user_token
                else:
                    logger.error(f"[Media:Spotify] Refresh token failed: {res.text}")

        except Exception as e:
            logger.exception(f"[Media:Spotify] Error refreshing user token: {e}")

        return None

    # ── Live Spotify Player Controls ─────────────────────────────────────────

    async def play_track_on_spotify(self, query: str) -> SpecialistResult:
        """Searches Spotify catalog and triggers live playback on active device."""
        token = await self._get_user_token()
        if not token:
            logger.info(f"[Media:Spotify] No user token, falling back to YouTube for '{query}'...")
            return await self.search_youtube(query)

        search_url = "https://api.spotify.com/v1/search"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"q": query, "type": "track", "limit": 3}

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                search_res = await client.get(search_url, headers=headers, params=params)
                if search_res.status_code != 200:
                    return await self.search_youtube(query)

                tracks = search_res.json().get("tracks", {}).get("items", [])
                if not tracks:
                    return await self.search_youtube(query)

                top_track = tracks[0]
                track_uri = top_track.get("uri")
                track_name = top_track.get("name", "Unknown Track")
                artists = ", ".join([a.get("name", "") for a in top_track.get("artists", [])])
                album_art = top_track.get("album", {}).get("images", [{}])[0].get("url", "")
                spotify_url = top_track.get("external_urls", {}).get("spotify", "")

                # Send live PLAY command to Spotify player
                play_url = "https://api.spotify.com/v1/me/player/play"
                play_payload = {"uris": [track_uri]}

                play_res = await client.put(play_url, headers=headers, json=play_payload)

                # If 404 No Active Device, find devices and transfer playback
                if play_res.status_code == 404:
                    dev_res = await client.get("https://api.spotify.com/v1/me/player/devices", headers=headers)
                    devices = dev_res.json().get("devices", [])
                    if devices:
                        target_device = devices[0]["id"]
                        await client.put(
                            "https://api.spotify.com/v1/me/player",
                            headers=headers,
                            json={"device_ids": [target_device], "play": True},
                        )
                        # Retry play
                        await client.put(f"{play_url}?device_id={target_device}", headers=headers, json=play_payload)

                logger.info(f"[Media:Spotify] ✓ Live playback started for '{track_name}' by {artists}")

                return SpecialistResult(
                    success=True,
                    action="play_track",
                    data={
                        "title": track_name,
                        "artist": artists,
                        "uri": track_uri,
                        "album_art": album_art,
                        "url": spotify_url,
                        "status": "playing",
                    },
                    speech_summary=f"Playing '{track_name}' by {artists} on Spotify, sir.",
                    card_payload={
                        "type": "spotify_now_playing",
                        "title": track_name,
                        "artist": artists,
                        "album_art": album_art,
                        "url": spotify_url,
                    },
                )

        except Exception as e:
            logger.exception(f"[Media:Spotify] Error starting playback for '{query}': {e}")
            return await self.search_youtube(query)

    async def play_playlist_on_spotify(self, playlist_name: str) -> SpecialistResult:
        """Finds a user playlist and starts playback."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="play_playlist", error="Spotify user token unavailable.")

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get("https://api.spotify.com/v1/me/playlists?limit=50", headers=headers)
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="play_playlist", error="Could not retrieve playlists.")

                items = res.json().get("items", [])
                match = next((p for p in items if playlist_name.lower() in p.get("name", "").lower()), None)
                if not match:
                    # Fallback to catalog search for public playlist
                    search_res = await client.get(
                        f"https://api.spotify.com/v1/search?q={playlist_name}&type=playlist&limit=1",
                        headers=headers,
                    )
                    found = search_res.json().get("playlists", {}).get("items", [])
                    if found:
                        match = found[0]

                if not match:
                    return SpecialistResult(
                        success=False,
                        action="play_playlist",
                        error=f"Could not locate playlist '{playlist_name}' on Spotify.",
                    )

                playlist_uri = match["uri"]
                p_name = match["name"]

                # Start playback
                await client.put(
                    "https://api.spotify.com/v1/me/player/play",
                    headers=headers,
                    json={"context_uri": playlist_uri},
                )

                return SpecialistResult(
                    success=True,
                    action="play_playlist",
                    data={"playlist": p_name, "uri": playlist_uri},
                    speech_summary=f"Starting playlist '{p_name}' on Spotify, sir.",
                    card_payload={"type": "spotify_playlist", "name": p_name, "uri": playlist_uri},
                )

        except Exception as e:
            logger.exception(f"[Media:Spotify] Playlist error: {e}")
            return SpecialistResult(success=False, action="play_playlist", error=str(e))

    async def control_playback(self, command: str) -> SpecialistResult:
        """Executes live playback controls: pause, play, next, previous."""
        token = await self._get_user_token()
        cmd = command.lower().strip()

        if token:
            headers = {"Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    if cmd in ["pause", "stop"]:
                        await client.put("https://api.spotify.com/v1/me/player/pause", headers=headers)
                    elif cmd in ["play", "resume"]:
                        await client.put("https://api.spotify.com/v1/me/player/play", headers=headers)
                    elif cmd in ["next", "skip"]:
                        await client.post("https://api.spotify.com/v1/me/player/next", headers=headers)
                    elif cmd in ["previous", "prev"]:
                        await client.post("https://api.spotify.com/v1/me/player/previous", headers=headers)
            except Exception as e:
                logger.warning(f"[Media:Spotify] Control error ({cmd}): {e}")

        speech_map = {
            "pause": "Playback paused, sir.",
            "stop": "Playback stopped, sir.",
            "play": "Resuming playback, sir.",
            "resume": "Resuming playback, sir.",
            "next": "Skipping to next track, sir.",
            "skip": "Skipping track, sir.",
            "previous": "Returning to previous track, sir.",
        }
        speech = speech_map.get(cmd, f"Executed {cmd} command, sir.")

        return SpecialistResult(
            success=True,
            action="control_playback",
            data={"command": cmd, "status": "executed"},
            speech_summary=speech,
            card_payload={"type": "media_control", "action": cmd},
        )

    # ── SerpAPI YouTube Search ───────────────────────────────────────────────

    async def search_youtube(self, query: str, max_results: int = 3) -> SpecialistResult:
        """Searches YouTube using SerpAPI engine."""
        if not self.serpapi_key:
            return SpecialistResult(
                success=False,
                action="search_youtube_video",
                error="SERPAPI_API_KEY is not configured.",
            )

        url = "https://serpapi.com/search.json"
        params = {
            "engine": "youtube",
            "search_query": query,
            "api_key": self.serpapi_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, params=params)
                if res.status_code != 200:
                    return SpecialistResult(
                        success=False,
                        action="search_youtube_video",
                        error=f"SerpAPI HTTP {res.status_code}: {res.text[:150]}",
                    )

                data = res.json()
                video_results = data.get("video_results", [])
                if not video_results:
                    return SpecialistResult(
                        success=True,
                        action="search_youtube_video",
                        data={"query": query, "videos": []},
                        speech_summary=f"I couldn't locate any YouTube videos matching '{query}', sir.",
                        card_payload={"type": "media_video_list", "query": query, "videos": []},
                    )

                cards = []
                for v in video_results[:max_results]:
                    channel_info = v.get("channel", {})
                    channel_name = channel_info.get("name", "Unknown Channel") if isinstance(channel_info, dict) else str(channel_info)
                    thumb = v.get("thumbnail", {}).get("static", "") if isinstance(v.get("thumbnail"), dict) else ""

                    cards.append({
                        "title": v.get("title", "Untitled Video"),
                        "link": v.get("link", ""),
                        "channel": channel_name,
                        "duration": v.get("length", ""),
                        "thumbnail": thumb,
                        "views": v.get("views", ""),
                    })

                top = cards[0]
                speech = f"Found '{top['title']}' by {top['channel']} on YouTube, sir."

                return SpecialistResult(
                    success=True,
                    action="search_youtube_video",
                    data={"query": query, "videos": cards, "top_video": top},
                    speech_summary=speech,
                    card_payload={
                        "type": "media_video_card",
                        "query": query,
                        "title": top["title"],
                        "channel": top["channel"],
                        "link": top["link"],
                        "duration": top["duration"],
                        "thumbnail": top["thumbnail"],
                        "videos": cards,
                    },
                )

        except Exception as e:
            logger.exception(f"[Media:YouTube] SerpAPI search failed: {e}")
            return SpecialistResult(success=False, action="search_youtube_video", error=str(e))

    # ── Execution Router ─────────────────────────────────────────────────────

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        act = action.lower().strip()

        # 1. Video / YouTube search
        if (
            any(k in act for k in ["video", "youtube", "clip", "watch", "channel"])
            or act in ["search_youtube_video", "youtube_search", "search_video", "find_video"]
        ):
            query = str(params.get("query") or params.get("search_query") or params.get("video") or "")
            return await self.search_youtube(query, max_results=int(params.get("max_results") or 3))

        # 2. Spotify Playlists
        elif any(k in act for k in ["playlist", "user_playlists"]):
            name = str(params.get("name") or params.get("query") or "")
            return await self.play_playlist_on_spotify(name)

        # 3. Spotify Tracks / Music
        elif (
            any(k in act for k in ["track", "song", "music", "spotify"])
            or act in ["play", "play_track", "search_and_play_spotify", "play_song"]
        ):
            query = str(params.get("query") or params.get("song") or params.get("track") or "")
            if not query:
                return await self.control_playback("play")
            return await self.play_track_on_spotify(query)

        # 4. Playback Controls
        elif act in ["control_playback", "pause", "resume", "next", "previous", "stop", "skip"]:
            cmd = params.get("command", act)
            return await self.control_playback(cmd)

        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}' on media specialist.")
