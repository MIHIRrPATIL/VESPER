#!/usr/bin/env python3
"""Google Calendar OAuth 2.0 Authorization Script for VESPER.

Run this script once to authorize VESPER to access your Google Calendar:
    python3 scripts/auth_google_calendar.py
"""

import datetime
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "backend" / "credentials" / "google_calendar_credentials.json"
TOKEN_FILE = PROJECT_ROOT / "backend" / "credentials" / "google_calendar_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def main():
    print("\n=======================================================")
    print("      VESPER GOOGLE CALENDAR AUTHORIZATION SETUP")
    print("=======================================================\n")

    if not CREDENTIALS_FILE.exists():
        print(f"Error: Credentials file not found at {CREDENTIALS_FILE}")
        return

    print(f"1. Loading client credentials from {CREDENTIALS_FILE.name}...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)

    print("2. Launching local authorization flow...")
    print("   (A browser window will open, or click the URL below to sign in with your Google account)")
    
    # Run local server to complete OAuth callback
    creds = flow.run_local_server(port=8080, prompt="consent")

    # Save token for subsequent runs
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())

    print(f"\n[OK] Authorization successful! Saved token to:\n  {TOKEN_FILE}\n")

    # Test live retrieval
    print("3. Testing live Google Calendar retrieval...")
    from typing import Any
    service: Any = build("calendar", "v3", credentials=creds)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    events_result = service.events().list(
        calendarId="primary",
        timeMin=now_iso,
        maxResults=5,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    if not events:
        print("[OK] Connected to your calendar! No upcoming events found in primary calendar.")
    else:
        print(f"[OK] Connected to your calendar! Found {len(events)} upcoming events:")
        for event in events:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
            print(f"   - [{start}] {event.get('summary', 'Untitled Event')}")

    print("\nGoogle Calendar is now fully linked to VESPER TaskAgent!\n")


if __name__ == "__main__":
    main()
