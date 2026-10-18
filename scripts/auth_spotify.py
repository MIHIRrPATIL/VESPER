"""Spotify OAuth Authorization Script for VESPER.

Launches a local HTTP server on port 8888 and prints an authorization URL.
Upon user consent, exchanges the authorization code for a fresh refresh_token
and saves it to backend/credentials/.spotify_cache.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx

# Ensure VESPER root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.shared.config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
)

CACHE_PATH = BASE_DIR / "backend" / "credentials" / ".spotify_cache"
SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-recently-played",
]

auth_code: str | None = None


class SpotifyOAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Spotify Authentication Successful!</h1>"
                b"<p>You can close this tab and return to VESPER.</p></body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authentication Failed</h1></body></html>")

    def log_message(self, format: str, *args: list[object]) -> None:
        pass


def main() -> None:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("ERROR: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in backend/.env")
        sys.exit(1)

    parsed_uri = urllib.parse.urlparse(SPOTIFY_REDIRECT_URI)
    port = parsed_uri.port or 8888

    query_params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    auth_url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(query_params)}"

    print("==========================================================")
    print("VESPER SPOTIFY OAUTH AUTHENTICATION")
    print("==========================================================")
    print("Please open the following URL in your browser to authorize Spotify:")
    print()
    print(auth_url)
    print()
    print(f"Waiting for callback on port {port}...")

    server = HTTPServer(("0.0.0.0", port), SpotifyOAuthCallbackHandler)
    while auth_code is None:
        server.handle_request()

    server.server_close()
    print("Authorization code received! Exchanging for refresh token...")

    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }

    res = httpx.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    if res.status_code == 200:
        token_data = res.json()
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

        cache = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scope"),
            "expires_in": token_data.get("expires_in", 3600),
        }

        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)

        print(f"SUCCESS: Saved new Spotify credentials to {CACHE_PATH}")
        print("Spotify integration is now active!")
    else:
        print(f"ERROR: Token exchange failed ({res.status_code}): {res.text}")


if __name__ == "__main__":
    main()
