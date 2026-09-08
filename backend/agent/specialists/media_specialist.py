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
                        "device": {"type": "string", "description": "Optional target device name (e.g. 'phone', 'laptop', 'desktop')."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "play_playlist",
                "description": "Plays a specific playlist on Spotify (e.g. 'Everyday', 'Focus Flow', 'Groovy Vibes'). Smartly prioritizes the user's own playlists and fuzzy matches.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the playlist to play."},
                        "device": {"type": "string", "description": "Optional target device name (e.g. 'phone', 'laptop', 'desktop')."},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "list_playlists",
                "description": "Lists the user's saved, created, and followed Spotify playlists with track counts and owners.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum number of playlists to retrieve (default: 20)."}
                    },
                },
            },
            {
                "name": "play_radio",
                "description": "Plays an artist radio, genre radio, or themed radio station on Spotify (e.g. 'Justin Bieber Radio', 'Coldplay Radio', 'Synthwave Radio').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "station": {"type": "string", "description": "Artist or genre for the radio station (e.g. 'Justin Bieber', 'Rock', 'Jazz')."},
                        "device": {"type": "string", "description": "Optional target device name (e.g. 'phone', 'laptop', 'desktop')."},
                    },
                    "required": ["station"],
                },
            },
            {
                "name": "list_devices",
                "description": "Lists all available Spotify Connect devices (e.g. Phone, Laptop, Web Player) and their active status.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "switch_device",
                "description": "Switches or transfers active Spotify playback to a specified device (e.g. 'phone', 'laptop', 'S23').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "description": "Target device name or type to transfer playback to (e.g. 'phone', 'laptop')."},
                    },
                    "required": ["device"],
                },
            },
            {
                "name": "get_playback_status",
                "description": "Checks what track is currently playing on Spotify and which device is playing it (e.g. 'where is it playing?').",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "get_recently_played",
                "description": "Retrieves recent music playback history from Spotify (e.g. to answer 'what was that song we played from Michael Jackson?').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of recent tracks to fetch (default: 5)."},
                        "filter_artist": {"type": "string", "description": "Optional artist to filter history by (e.g. 'Michael Jackson')."},
                    },
                },
            },
            {
                "name": "queue_track",
                "description": "Adds a song or track to the end of the user's active Spotify playback queue without interrupting current music.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Song name or artist to queue up on Spotify."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_queue",
                "description": "Retrieves the currently playing song and upcoming queued tracks on Spotify.",
                "parameters": {
                    "type": "object",
                    "properties": {},
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

    async def _resolve_target_device(
        self,
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        requested_device: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
        """Resolves target playback device ID and human name from Spotify Connect devices."""
        try:
            dev_res = await client.get("https://api.spotify.com/v1/me/player/devices", headers=headers)
            devices = dev_res.json().get("devices", []) if dev_res.status_code == 200 else []
        except Exception:
            devices = []

        if not devices:
            return None, None, []

        # 1. Match specific requested device if specified
        if requested_device:
            req = requested_device.lower().strip()
            # Common aliases for phone/mobile devices
            phone_aliases = {"phone", "mobile", "smartphone", "cell", "handset", "android", "iphone", "samsung", "galaxy", "pixel", "oneplus"}
            # Common aliases for computer/desktop
            desktop_aliases = {"laptop", "desktop", "pc", "computer", "macbook", "mac"}
            # Common aliases for web player
            web_aliases = {"web", "browser", "web player"}

            is_phone_req = req in phone_aliases or any(alias in req for alias in phone_aliases)
            is_desktop_req = req in desktop_aliases or any(alias in req for alias in desktop_aliases)
            is_web_req = req in web_aliases or any(alias in req for alias in web_aliases)

            # Pass 1: Strict name/type match
            for d in devices:
                name_lower = d.get("name", "").lower()
                type_lower = d.get("type", "").lower()
                d_id = d.get("id")

                if is_phone_req and type_lower == "smartphone":
                    return d_id, d["name"], devices
                if is_desktop_req and type_lower == "computer":
                    return d_id, d["name"], devices
                if is_web_req and ("web" in name_lower or type_lower == "web_player"):
                    return d_id, d["name"], devices
                # Direct name substring match
                if req in name_lower or req in type_lower:
                    return d_id, d["name"], devices

            # Pass 2: Fuzzy word overlap on device name (e.g. "mihir's app" -> "MIHIR-S23")
            req_words = set(req.replace("'s", "").replace("'", "").split())
            for d in devices:
                name_lower = d.get("name", "").lower()
                name_words = set(name_lower.replace("-", " ").replace("_", " ").split())
                if req_words & name_words:
                    return d["id"], d["name"], devices

            # Pass 3: If user explicitly asked for a device but we couldn't find it,
            # DON'T silently fall back — return None so the caller can report the error
            logger.warning(f"[Media:Spotify] Could not match requested device '{requested_device}' among: {[d.get('name') for d in devices]}")
            return None, None, devices

        # 2. Check if an active device is currently streaming
        active_dev = next((d for d in devices if d.get("is_active")), None)
        if active_dev:
            return active_dev["id"], active_dev["name"], devices

        # 3. Fallback to first available device
        first_dev = devices[0]
        return first_dev["id"], first_dev["name"], devices

    async def play_track_on_spotify(self, query: str, device: Optional[str] = None) -> SpecialistResult:
        """Searches Spotify catalog and triggers live playback on active or designated device."""
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

                # Resolve target device (phone, laptop, or currently active)
                target_id, target_name, all_devs = await self._resolve_target_device(client, headers, requested_device=device)
                if not target_id:
                    logger.info(f"[Media:Spotify] No connected devices found for '{query}'...")
                    return SpecialistResult(
                        success=False,
                        action="play_track",
                        error="No active or connected Spotify devices detected.",
                        speech_summary="I cannot start Spotify playback because no devices are currently connected on your account, sir. Please open Spotify on your phone or desktop.",
                    )

                # Send live PLAY command to Spotify player
                play_url = f"https://api.spotify.com/v1/me/player/play?device_id={target_id}"
                play_payload = {"uris": [track_uri]}

                play_res = await client.put(play_url, headers=headers, json=play_payload)

                # If 404/403 (inactive device), transfer playback first then retry
                if play_res.status_code in [404, 403]:
                    await client.put(
                        "https://api.spotify.com/v1/me/player",
                        headers=headers,
                        json={"device_ids": [target_id], "play": True},
                    )
                    await client.put(play_url, headers=headers, json=play_payload)

                logger.info(f"[Media:Spotify] [OK] Live playback started for '{track_name}' by {artists} on {target_name}")

                return SpecialistResult(
                    success=True,
                    action="play_track",
                    data={
                        "title": track_name,
                        "artist": artists,
                        "uri": track_uri,
                        "album_art": album_art,
                        "url": spotify_url,
                        "device": target_name,
                        "status": "playing",
                    },
                    speech_summary=f"Playing '{track_name}' by {artists} on {target_name}, sir.",
                    card_payload={
                        "type": "spotify_now_playing",
                        "title": track_name,
                        "artist": artists,
                        "album_art": album_art,
                        "url": spotify_url,
                        "device": target_name,
                    },
                )

        except Exception as e:
            logger.exception(f"[Media:Spotify] Error starting playback for '{query}': {e}")
            return await self.search_youtube(query)

    async def play_playlist_on_spotify(self, playlist_name: str, device: Optional[str] = None) -> SpecialistResult:
        """Finds a playlist (smartly prioritizing user-owned playlists and fuzzy matching) and starts playback."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(
                success=False,
                action="play_playlist",
                speech_summary="Sir, your Spotify account is not yet connected. Please authenticate with Spotify or configure your refresh token in the environment so I may access your playlists.",
                error="Spotify user token unavailable. Please authenticate with Spotify.",
            )

        headers = {"Authorization": f"Bearer {token}"}
        try:
            import difflib

            async with httpx.AsyncClient(timeout=8.0) as client:
                # 1. Fetch current user identity to prioritize user-owned playlists
                my_name = ""
                my_id = ""
                try:
                    me_res = await client.get("https://api.spotify.com/v1/me", headers=headers)
                    if me_res.status_code == 200:
                        me_data = me_res.json()
                        my_name = str(me_data.get("display_name", "")).lower()
                        my_id = str(me_data.get("id", "")).lower()
                except Exception:
                    pass

                # If query contains "radio", route to radio handler if artist exists
                clean_name = playlist_name.lower().replace("playlist", "").strip()
                if "radio" in clean_name:
                    radio_candidate = clean_name.replace("radio", "").strip()
                    if radio_candidate:
                        return await self.play_radio_on_spotify(radio_candidate, device=device)

                # 2. Gather candidates from user library and Spotify search
                candidates = []

                # A. User library
                try:
                    pl_res = await client.get("https://api.spotify.com/v1/me/playlists?limit=50", headers=headers)
                    if pl_res.status_code == 200:
                        candidates.extend([p for p in pl_res.json().get("items", []) if p])
                except Exception:
                    pass

                # B. Spotify catalog search with limit=20
                try:
                    s_res = await client.get(
                        f"https://api.spotify.com/v1/search?q={playlist_name}&type=playlist&limit=20",
                        headers=headers,
                    )
                    if s_res.status_code == 200:
                        search_items = [p for p in s_res.json().get("playlists", {}).get("items", []) if p]
                        candidates.extend(search_items)
                except Exception:
                    pass

                if not candidates:
                    return SpecialistResult(
                        success=False,
                        action="play_playlist",
                        error=f"Could not locate playlist '{playlist_name}' on Spotify.",
                    )

                # 3. Deduplicate and score candidates
                seen_uris = set()
                unique_candidates = []
                for p in candidates:
                    uri = p.get("uri")
                    if uri and uri not in seen_uris:
                        seen_uris.add(uri)
                        unique_candidates.append(p)

                target_q = playlist_name.lower().strip().replace('"', "")

                def score_playlist(p: dict) -> float:
                    name = str(p.get("name", "")).lower().strip().replace('"', "")
                    owner_name = str(p.get("owner", {}).get("display_name", "")).lower()
                    owner_id = str(p.get("owner", {}).get("id", "")).lower()
                    is_mine = (
                        (my_name and owner_name == my_name)
                        or (my_id and owner_id == my_id)
                        or ("mihir" in owner_name)
                    )

                    score = 0.0
                    # Exact name match
                    if name == target_q:
                        score += 1000.0
                    # Sequence similarity ratio
                    ratio = difflib.SequenceMatcher(None, target_q, name).ratio()
                    score += ratio * 300.0
                    # Substring match with length penalty if vastly longer
                    if target_q in name:
                        score += 100.0 * (len(target_q) / max(len(name), 1))
                    elif name in target_q:
                        score += 80.0
                    # Heavily prioritize user's own playlist
                    if is_mine:
                        score += 600.0
                    return score

                ranked = sorted(unique_candidates, key=score_playlist, reverse=True)
                match = ranked[0]
                best_score = score_playlist(match)

                # If score is very low, check if this is an artist name
                if best_score < 150:
                    return await self.play_radio_on_spotify(playlist_name, device=device)

                playlist_uri = match["uri"]
                p_name = match.get("name", playlist_name)
                owner_display = match.get("owner", {}).get("display_name", "")

                # 4. Resolve target device and trigger playback
                target_id, target_name, _ = await self._resolve_target_device(client, headers, requested_device=device)
                play_url = f"https://api.spotify.com/v1/me/player/play?device_id={target_id}" if target_id else "https://api.spotify.com/v1/me/player/play"
                play_payload = {"context_uri": playlist_uri}
                play_res = await client.put(play_url, headers=headers, json=play_payload)

                # If 404/403 No Active Device, transfer playback and retry
                if play_res.status_code in [404, 403]:
                    if target_id:
                        await client.put(
                            "https://api.spotify.com/v1/me/player",
                            headers=headers,
                            json={"device_ids": [target_id], "play": True},
                        )
                        await client.put(play_url, headers=headers, json=play_payload)

                owner_suffix = f" by {owner_display}" if owner_display else ""
                logger.info(f"[Media:Spotify] Started playlist '{p_name}'{owner_suffix} on {target_name} ({playlist_uri})")

                dev_mention = f" on {target_name}" if target_name else ""
                speech = (
                    f"Starting your '{p_name}' playlist{dev_mention} on Spotify, sir."
                    if (my_name and owner_display.lower() == my_name)
                    else f"Starting playlist '{p_name}'{dev_mention} on Spotify, sir."
                )

                return SpecialistResult(
                    success=True,
                    action="play_playlist",
                    data={"playlist": p_name, "uri": playlist_uri, "owner": owner_display, "device": target_name},
                    speech_summary=speech,
                    card_payload={"type": "spotify_playlist", "name": p_name, "uri": playlist_uri, "owner": owner_display, "device": target_name},
                )

        except Exception as e:
            logger.exception(f"[Media:Spotify] Playlist error: {e}")
            return SpecialistResult(success=False, action="play_playlist", error=str(e))

    async def list_user_playlists(self, limit: int = 25) -> SpecialistResult:
        """Retrieves and lists the user's Spotify playlists (both created and followed)."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(
                success=False,
                action="list_playlists",
                error="Spotify account is not connected.",
                speech_summary="Sir, your Spotify account is not currently connected. Please authenticate with Spotify so I may view your playlists.",
            )

        try:
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(
                    f"https://api.spotify.com/v1/me/playlists?limit={limit}",
                    headers=headers,
                )
                if res.status_code != 200:
                    return SpecialistResult(
                        success=False,
                        action="list_playlists",
                        error=f"Spotify API error ({res.status_code}): {res.text}",
                        speech_summary="I encountered an error retrieving your Spotify playlists, sir.",
                    )

                items = [p for p in res.json().get("items", []) if p]
                if not items:
                    return SpecialistResult(
                        success=True,
                        action="list_playlists",
                        data={"playlists": [], "count": 0},
                        speech_summary="You do not have any saved playlists in your Spotify library, sir.",
                        card_payload={"type": "spotify_playlists_card", "title": "Your Spotify Playlists", "playlists": []},
                    )

                playlists_data = []
                names = []
                for p in items:
                    p_name = p.get("name", "Untitled")
                    owner_name = p.get("owner", {}).get("display_name", "Spotify")
                    total_tracks = p.get("tracks", {}).get("total", 0)
                    uri = p.get("uri", "")
                    img_url = p.get("images", [{}])[0].get("url", "") if p.get("images") else ""
                    playlists_data.append({
                        "name": p_name,
                        "owner": owner_name,
                        "total_tracks": total_tracks,
                        "uri": uri,
                        "image_url": img_url,
                    })
                    names.append(p_name)

                # Format speech summary in Alfred's refined butler tone
                if len(names) <= 5:
                    playlist_list_str = ", ".join(f"'{n}'" for n in names)
                    speech = f"You have {len(names)} playlists in your library, sir: {playlist_list_str}."
                else:
                    top_five = ", ".join(f"'{n}'" for n in names[:5])
                    speech = f"You have {len(names)} playlists in your library, sir, including {top_five}, among others."

                logger.info(f"[Media:Spotify] Retrieved {len(playlists_data)} user playlists successfully")
                return SpecialistResult(
                    success=True,
                    action="list_playlists",
                    data={"playlists": playlists_data, "count": len(playlists_data)},
                    speech_summary=speech,
                    card_payload={
                        "type": "spotify_playlists_card",
                        "title": "Your Spotify Playlists",
                        "count": len(playlists_data),
                        "playlists": playlists_data,
                    },
                )
        except Exception as e:
            logger.exception(f"[Media:Spotify] Error listing user playlists: {e}")
            return SpecialistResult(
                success=False,
                action="list_playlists",
                error=str(e),
                speech_summary="I was unable to retrieve your playlists at this time, sir.",
            )

    async def play_radio_on_spotify(self, station: str, device: Optional[str] = None) -> SpecialistResult:
        """Plays an artist radio, genre radio, or themed radio on Spotify."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="play_radio", error="Spotify user token unavailable.")

        clean = station.lower().replace("radio", "").replace("station", "").replace("playlist", "").strip()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                target_id, target_name, _ = await self._resolve_target_device(client, headers, requested_device=device)

                # 1. First check if this is an artist (e.g. "Justin Bieber", "Coldplay", "The Weeknd")
                a_res = await client.get(f"https://api.spotify.com/v1/search?q={clean}&type=artist&limit=3", headers=headers)
                if a_res.status_code == 200:
                    artists = a_res.json().get("artists", {}).get("items", [])
                    if artists:
                        top_artist = artists[0]
                        artist_name = top_artist.get("name", clean)
                        artist_uri = top_artist.get("uri")

                        play_url = f"https://api.spotify.com/v1/me/player/play?device_id={target_id}" if target_id else "https://api.spotify.com/v1/me/player/play"
                        play_res = await client.put(play_url, headers=headers, json={"context_uri": artist_uri})

                        if play_res.status_code in [404, 403]:
                            if target_id:
                                await client.put("https://api.spotify.com/v1/me/player", headers=headers, json={"device_ids": [target_id], "play": True})
                                await client.put(play_url, headers=headers, json={"context_uri": artist_uri})

                        dev_mention = f" on {target_name}" if target_name else ""
                        return SpecialistResult(
                            success=True,
                            action="play_radio",
                            data={"artist": artist_name, "uri": artist_uri, "type": "artist_radio", "device": target_name},
                            speech_summary=f"Playing {artist_name} Radio{dev_mention} on Spotify, sir.",
                            card_payload={"type": "spotify_radio", "station": f"{artist_name} Radio", "uri": artist_uri, "device": target_name},
                        )

                # 2. If not artist, search for radio or curated playlist (e.g. "Lofi Radio", "Rock Radio")
                p_res = await client.get(f"https://api.spotify.com/v1/search?q={clean} Radio&type=playlist&limit=5", headers=headers)
                items = [p for p in p_res.json().get("playlists", {}).get("items", []) if p]
                if items:
                    top_pl = items[0]
                    p_name = top_pl.get("name")
                    p_uri = top_pl.get("uri")

                    play_url = f"https://api.spotify.com/v1/me/player/play?device_id={target_id}" if target_id else "https://api.spotify.com/v1/me/player/play"
                    play_res = await client.put(play_url, headers=headers, json={"context_uri": p_uri})
                    if play_res.status_code in [404, 403]:
                        if target_id:
                            await client.put("https://api.spotify.com/v1/me/player", headers=headers, json={"device_ids": [target_id], "play": True})
                            await client.put(play_url, headers=headers, json={"context_uri": p_uri})

                    dev_mention = f" on {target_name}" if target_name else ""
                    return SpecialistResult(
                        success=True,
                        action="play_radio",
                        data={"playlist": p_name, "uri": p_uri, "type": "playlist_radio", "device": target_name},
                        speech_summary=f"Playing '{p_name}'{dev_mention} on Spotify, sir.",
                        card_payload={"type": "spotify_radio", "station": p_name, "uri": p_uri, "device": target_name},
                    )

                return SpecialistResult(
                    success=False,
                    action="play_radio",
                    error=f"Could not find an artist or radio station for '{station}' on Spotify.",
                )

        except Exception as e:
            logger.exception(f"[Media:Spotify] Radio playback error: {e}")
            return SpecialistResult(success=False, action="play_radio", error=str(e))

    async def queue_track_on_spotify(self, query: str) -> SpecialistResult:
        """Adds a track to the active Spotify playback queue without interrupting current song."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="queue_track", error="Spotify user token unavailable.")

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                search_res = await client.get(
                    f"https://api.spotify.com/v1/search?q={query}&type=track&limit=5",
                    headers=headers,
                )
                if search_res.status_code != 200:
                    return SpecialistResult(success=False, action="queue_track", error="Failed to search track on Spotify.")

                tracks = search_res.json().get("tracks", {}).get("items", [])
                if not tracks:
                    return SpecialistResult(success=False, action="queue_track", error=f"Could not find track '{query}' to queue.")

                track = tracks[0]
                track_uri = track.get("uri")
                track_name = track.get("name", "Unknown Track")
                artists = ", ".join([a.get("name", "") for a in track.get("artists", [])])

                queue_res = await client.post(
                    f"https://api.spotify.com/v1/me/player/queue?uri={track_uri}",
                    headers=headers,
                )

                if queue_res.status_code == 404:
                    # Transfer to first available device if inactive
                    dev_res = await client.get("https://api.spotify.com/v1/me/player/devices", headers=headers)
                    devices = dev_res.json().get("devices", [])
                    if devices:
                        target_device = devices[0]["id"]
                        await client.put("https://api.spotify.com/v1/me/player", headers=headers, json={"device_ids": [target_device], "play": False})
                        await client.post(
                            f"https://api.spotify.com/v1/me/player/queue?uri={track_uri}&device_id={target_device}",
                            headers=headers,
                        )

                logger.info(f"[Media:Spotify] Queued '{track_name}' by {artists}")
                return SpecialistResult(
                    success=True,
                    action="queue_track",
                    data={"title": track_name, "artist": artists, "uri": track_uri},
                    speech_summary=f"Added '{track_name}' by {artists} to your Spotify queue, sir.",
                    card_payload={"type": "spotify_queue_card", "title": track_name, "artist": artists, "uri": track_uri},
                )

        except Exception as e:
            logger.exception(f"[Media:Spotify] Queue error: {e}")
            return SpecialistResult(success=False, action="queue_track", error=str(e))

    async def get_spotify_queue(self) -> SpecialistResult:
        """Retrieves currently playing song and upcoming queue on Spotify."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="get_queue", error="Spotify user token unavailable.")

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get("https://api.spotify.com/v1/me/player/queue", headers=headers)
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="get_queue", error="Could not retrieve Spotify queue.")

                data = res.json()
                curr = data.get("currently_playing")
                queue_items = data.get("queue", [])

                curr_title = curr.get("name") if curr else "None"
                curr_artist = ", ".join([a.get("name", "") for a in curr.get("artists", [])]) if curr else ""

                queued_titles = [f"'{t.get('name')}' by {t.get('artists', [{}])[0].get('name')}" for t in queue_items[:3]]
                next_str = ", ".join(queued_titles) if queued_titles else "No upcoming tracks"

                speech = (
                    f"Currently playing '{curr_title}' by {curr_artist}. Next in queue: {next_str}, sir."
                    if curr
                    else f"No track is currently playing. Upcoming in queue: {next_str}."
                )

                return SpecialistResult(
                    success=True,
                    action="get_queue",
                    data={"currently_playing": curr_title, "artist": curr_artist, "queue": queued_titles},
                    speech_summary=speech,
                    card_payload={"type": "spotify_queue_status", "now_playing": curr_title, "queue": queued_titles},
                )
        except Exception as e:
            logger.exception(f"[Media:Spotify] Get queue error: {e}")
            return SpecialistResult(success=False, action="get_queue", error=str(e))

    # ── Spotify Device Management & Playback Status ──────────────────────────

    async def list_spotify_devices(self) -> SpecialistResult:
        """Lists all available Spotify Connect devices and active status."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="list_devices", error="Spotify token unavailable.")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get("https://api.spotify.com/v1/me/player/devices", headers=headers)
                devs = res.json().get("devices", []) if res.status_code == 200 else []
                if not devs:
                    speech = "No active Spotify Connect devices are currently detected, sir. Please open Spotify on your phone or computer."
                else:
                    parts = []
                    for d in devs:
                        status = "actively playing" if d.get("is_active") else "connected"
                        parts.append(f"{d.get('name')} ({d.get('type')}, {status})")
                    speech = f"I detect {len(devs)} Spotify device{'s' if len(devs) != 1 else ''}, sir: {', '.join(parts)}."
                return SpecialistResult(
                    success=True,
                    action="list_devices",
                    data={"devices": devs, "count": len(devs)},
                    speech_summary=speech,
                    card_payload={"type": "spotify_devices_card", "devices": devs},
                )
        except Exception as e:
            logger.exception(f"[Media:Spotify] List devices error: {e}")
            return SpecialistResult(success=False, action="list_devices", error=str(e))

    async def switch_spotify_device(self, device_query: str) -> SpecialistResult:
        """Transfers Spotify playback to a requested device (phone, laptop, desktop)."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="switch_device", error="Spotify token unavailable.")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                dev_id, dev_name, all_devs = await self._resolve_target_device(client, headers, requested_device=device_query)
                if not dev_id:
                    avail_names = [str(d["name"]) for d in all_devs if d.get("name")]
                    return SpecialistResult(
                        success=False,
                        action="switch_device",
                        error=f"Device '{device_query}' not found.",
                        speech_summary=f"I couldn't locate a Spotify device matching '{device_query}', sir. Available devices are: {', '.join(avail_names) if avail_names else 'None'}.",
                    )
                # Transfer playback
                res = await client.put(
                    "https://api.spotify.com/v1/me/player",
                    headers=headers,
                    json={"device_ids": [dev_id], "play": True},
                )
                if res.status_code in [200, 202, 204]:
                    speech = f"Switched Spotify playback to {dev_name}, sir."
                    return SpecialistResult(
                        success=True,
                        action="switch_device",
                        data={"device_id": dev_id, "device_name": dev_name},
                        speech_summary=speech,
                        card_payload={"type": "spotify_device_switched", "device": dev_name},
                    )
                return SpecialistResult(success=False, action="switch_device", error=f"Device transfer failed: {res.text}")
        except Exception as e:
            logger.exception(f"[Media:Spotify] Switch device error: {e}")
            return SpecialistResult(success=False, action="switch_device", error=str(e))

    async def get_playback_status(self) -> SpecialistResult:
        """Informs the user what is currently playing AND on which device it is playing."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="get_playback_status", error="Spotify token unavailable.")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get("https://api.spotify.com/v1/me/player", headers=headers)
                if res.status_code == 204 or not res.text:
                    dev_res = await client.get("https://api.spotify.com/v1/me/player/devices", headers=headers)
                    devs = dev_res.json().get("devices", []) if dev_res.status_code == 200 else []
                    dev_names = [f"{d['name']} ({d['type']})" for d in devs]
                    msg = f"Spotify playback is currently idle, sir. Reachable devices: {', '.join(dev_names) if dev_names else 'None'}."
                    return SpecialistResult(success=True, action="get_playback_status", data={"is_playing": False, "devices": devs}, speech_summary=msg)

                data = res.json()
                item = data.get("item", {})
                track = item.get("name", "Unknown Track")
                artists = ", ".join([a.get("name", "") for a in item.get("artists", [])])
                album = item.get("album", {})
                album_name = album.get("name", "")
                release_date = album.get("release_date", "")
                device = data.get("device", {})
                dev_name = device.get("name", "Unknown Device")
                is_playing = data.get("is_playing", False)
                status_str = "playing" if is_playing else "paused"

                album_phrase = f" from the album or film '{album_name}'" if album_name else ""
                speech = f"Spotify is currently {status_str} '{track}' by {artists}{album_phrase} on {dev_name}, sir."
                return SpecialistResult(
                    success=True,
                    action="get_playback_status",
                    data={
                        "track": track,
                        "title": track,
                        "song": track,
                        "artist": artists,
                        "album": album_name,
                        "movie": album_name,
                        "release_date": release_date,
                        "device": dev_name,
                        "is_playing": is_playing,
                    },
                    speech_summary=speech,
                    card_payload={"type": "spotify_now_playing", "title": track, "artist": artists, "album": album_name, "device": dev_name},
                )
        except Exception as e:
            logger.exception(f"[Media:Spotify] Playback status error: {e}")
            return SpecialistResult(success=False, action="get_playback_status", error=str(e))

    async def get_recently_played(self, limit: int = 5, filter_artist: Optional[str] = None) -> SpecialistResult:
        """Retrieves user's recent playback history from Spotify (e.g. to answer 'what song did we play?')."""
        token = await self._get_user_token()
        if not token:
            return SpecialistResult(success=False, action="get_recently_played", error="Spotify token unavailable.")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get("https://api.spotify.com/v1/me/player/recently-played?limit=25", headers=headers)
                if res.status_code != 200:
                    return SpecialistResult(success=False, action="get_recently_played", error="Could not fetch history from Spotify.")

                items = res.json().get("items", [])
                parsed = []
                for it in items:
                    t = it.get("track", {})
                    artists = ", ".join([a.get("name", "") for a in t.get("artists", [])])
                    parsed.append({
                        "name": t.get("name"),
                        "artist": artists,
                        "played_at": it.get("played_at"),
                    })

                if filter_artist:
                    fa = filter_artist.lower().strip()
                    matched = [p for p in parsed if fa in p["artist"].lower() or fa in p["name"].lower()]
                    if matched:
                        top = matched[0]
                        speech = f"The track we played by {filter_artist} was '{top['name']}' by {top['artist']}, sir."
                        return SpecialistResult(
                            success=True,
                            action="get_recently_played",
                            data={"tracks": matched, "match": top},
                            speech_summary=speech,
                            card_payload={"type": "spotify_history", "tracks": matched[:limit]},
                        )
                    else:
                        recent_summary = f"'{parsed[0]['name']}' by {parsed[0]['artist']}" if parsed else "none"
                        speech = (
                            f"I examined your recent Spotify sessions, sir; we haven't played any tracks by {filter_artist} recently. "
                            f"Our most recent playback was {recent_summary}. Shall I play one of {filter_artist}'s classics now?"
                        )
                        return SpecialistResult(
                            success=True,
                            action="get_recently_played",
                            data={"tracks": parsed[:limit], "found_filter": False},
                            speech_summary=speech,
                            card_payload={"type": "spotify_history", "tracks": parsed[:limit]},
                        )

                top_tracks = [f"'{p['name']}' by {p['artist']}" for p in parsed[:3]]
                speech = f"Recently played on Spotify: {', '.join(top_tracks)}, sir."
                return SpecialistResult(
                    success=True,
                    action="get_recently_played",
                    data={"tracks": parsed[:limit]},
                    speech_summary=speech,
                    card_payload={"type": "spotify_history", "tracks": parsed[:limit]},
                )
        except Exception as e:
            logger.exception(f"[Media:Spotify] Recently played error: {e}")
            return SpecialistResult(success=False, action="get_recently_played", error=str(e))

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

        # 2. Spotify Device Inspection & Switching
        elif any(k in act for k in ["device", "devices"]) or act in ["list_devices", "get_devices", "show_devices", "switch_device"]:
            if "switch" in act or "transfer" in act or "change" in act or "target" in act or params.get("device"):
                dev_target = str(params.get("device") or params.get("name") or params.get("target") or "")
                return await self.switch_spotify_device(dev_target)
            return await self.list_spotify_devices()

        # 3. Spotify Playback Status & Device Check
        elif any(k in act for k in ["status", "now_playing", "where", "playing_on"]) or act in ["get_playback_status", "playback_status"]:
            return await self.get_playback_status()

        # 4. Recently Played / Music History
        elif any(k in act for k in ["recent", "history", "past_song", "played_before"]) or act in ["get_recently_played", "recently_played"]:
            limit = int(params.get("limit") or 5)
            filter_artist = params.get("filter_artist") or params.get("artist")
            return await self.get_recently_played(limit=limit, filter_artist=filter_artist)

        # 5. Spotify Queue Management
        elif any(k in act for k in ["queue", "add_to_queue"]) or act in ["queue_track", "get_queue", "view_queue"]:
            if act in ["get_queue", "view_queue", "show_queue", "list_queue"]:
                return await self.get_spotify_queue()
            query = str(params.get("query") or params.get("track") or params.get("song") or "")
            if not query:
                return await self.get_spotify_queue()
            return await self.queue_track_on_spotify(query)

        # 6. Radio Stations (Artist Radio, Genre Radio)
        elif any(k in act for k in ["radio", "station"]) or act == "play_radio":
            station = str(params.get("station") or params.get("query") or params.get("name") or "")
            device = params.get("device")
            return await self.play_radio_on_spotify(station, device=device)

        # 7a. List User Playlists
        elif act in ["list_playlists", "get_playlists", "get_user_playlists", "list_user_playlists", "show_playlists"]:
            limit = int(params.get("limit") or 25)
            return await self.list_user_playlists(limit=limit)

        # 7b. Spotify Playlists Playback
        elif any(k in act for k in ["playlist", "user_playlists"]) or act == "play_playlist":
            name = str(params.get("name") or params.get("query") or params.get("playlist") or "").strip()
            if not name or act in ["list_playlists", "get_playlists", "show_playlists"]:
                return await self.list_user_playlists()
            device = params.get("device")
            return await self.play_playlist_on_spotify(name, device=device)

        # 8. Spotify Tracks / Music
        elif (
            any(k in act for k in ["track", "song", "music", "spotify"])
            or act in ["play", "play_track", "search_and_play_spotify", "play_song"]
        ):
            query = str(params.get("query") or params.get("song") or params.get("track") or "")
            device = params.get("device")
            if not query:
                return await self.control_playback("play")
            return await self.play_track_on_spotify(query, device=device)

        # 9. Playback Controls
        elif act in ["control_playback", "pause", "resume", "next", "previous", "stop", "skip"]:
            cmd = params.get("command", act)
            return await self.control_playback(cmd)

        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}' on media specialist.")
