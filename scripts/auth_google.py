#!/usr/bin/env python3
"""Unified Google Workspace OAuth 2.0 Authorization Script for VESPER.

Authorizes both Gmail and Google Calendar in a single OAuth consent step:
    .venv/bin/python3 scripts/auth_google.py
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = (
    PROJECT_ROOT / "backend" / "credentials" / "google_calendar_credentials.json"
    if (PROJECT_ROOT / "backend" / "credentials" / "google_calendar_credentials.json").exists()
    else PROJECT_ROOT / "backend" / "credentials" / "gmail_credentials.json"
)

GMAIL_TOKEN_FILE = PROJECT_ROOT / "backend" / "credentials" / "gmail_token.json"
CALENDAR_TOKEN_FILE = PROJECT_ROOT / "backend" / "credentials" / "google_calendar_token.json"

# Unified Scopes: Gmail + Google Calendar
SCOPES = [
    # Gmail API
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    # Google Calendar API
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def main():
    print("\n=======================================================")
    print("      VESPER UNIFIED GOOGLE AUTHORIZATION (GMAIL + CALENDAR)")
    print("=======================================================\n")

    if not CREDENTIALS_FILE.exists():
        print(f"Error: Google OAuth client credentials not found at:\n  {CREDENTIALS_FILE}")
        print("Please place your OAuth client JSON file in backend/credentials/")
        sys.exit(1)

    print(f"1. Loading client credentials from {CREDENTIALS_FILE.name}...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)

    print("2. Launching local authorization flow on port 8080...")
    print("   (Sign in and grant permissions for both Gmail and Calendar)")
    
    # Run local server for OAuth callback
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    # Save token for Gmail and Calendar
    GMAIL_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    json_data = creds.to_json()

    with open(GMAIL_TOKEN_FILE, "w") as f:
        f.write(json_data)
    with open(CALENDAR_TOKEN_FILE, "w") as f:
        f.write(json_data)

    print(f"\n[OK] Authorization successful! Saved tokens to:")
    print(f"  - {GMAIL_TOKEN_FILE}")
    print(f"  - {CALENDAR_TOKEN_FILE}\n")

    # Test Gmail
    print("3. Testing live Gmail inbox connectivity...")
    try:
        gmail_service = build("gmail", "v1", credentials=creds)
        profile = gmail_service.users().getProfile(userId="me").execute()
        print(f"[OK] Gmail authenticated as: {profile.get('emailAddress')} (Messages: {profile.get('messagesTotal')})")
    except Exception as e:
        print(f"Warning: Gmail verification query failed ({e})")

    # Test Google Calendar
    print("4. Testing live Google Calendar connectivity...")
    try:
        cal_service = build("calendar", "v3", credentials=creds)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        events_result = cal_service.events().list(
            calendarId="primary",
            timeMin=now_iso,
            maxResults=3,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = events_result.get("items", [])
        print(f"[OK] Google Calendar connected successfully ({len(events)} upcoming events found).")
    except Exception as e:
        print(f"Warning: Google Calendar verification query failed ({e})")

    print("\nVESPER Gmail and Google Calendar are now fully synchronized and authorized!\n")


if __name__ == "__main__":
    main()
