#!/usr/bin/env python3
"""Google Gmail OAuth 2.0 Authorization Script for VESPER.

Run this script once to authorize VESPER to access your Gmail inbox:
    .venv/bin/python3 scripts/auth_gmail.py
"""

import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = (
    PROJECT_ROOT / "backend" / "credentials" / "gmail_credentials.json"
    if (PROJECT_ROOT / "backend" / "credentials" / "gmail_credentials.json").exists()
    else PROJECT_ROOT / "backend" / "credentials" / "google_calendar_credentials.json"
)
TOKEN_FILE = PROJECT_ROOT / "backend" / "credentials" / "gmail_token.json"

# Full Gmail scopes needed for VESPER: reading, searching, thread triage, drafting, and sending
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


def main():
    print("\n=======================================================")
    print("         VESPER GMAIL AUTHORIZATION SETUP")
    print("=======================================================\n")

    if not CREDENTIALS_FILE.exists():
        print(f"Error: Google OAuth credentials file not found at:\n  {CREDENTIALS_FILE}")
        print("Please place your OAuth client JSON file in backend/credentials/")
        sys.exit(1)

    print(f"1. Loading client credentials from {CREDENTIALS_FILE.name}...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)

    print("2. Launching local authorization flow...")
    print("   (A browser window will open, or sign in with your Google account)")
    
    # Run local server to complete OAuth callback
    creds = flow.run_local_server(port=8080, prompt="consent")

    # Save token for subsequent runs
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())

    print(f"\n[OK] Authorization successful! Saved Gmail token to:\n  {TOKEN_FILE}\n")

    # Test live retrieval
    print("3. Testing live Gmail inbox connectivity...")
    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        print(f"[OK] Authenticated as: {profile.get('emailAddress')} (Total Messages: {profile.get('messagesTotal')})")

        res = service.users().messages().list(userId="me", maxResults=3).execute()
        msgs = res.get("messages", [])
        print(f"[OK] Retrieved {len(msgs)} sample message headers:")
        for m in msgs:
            detail = service.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject"]
            ).execute()
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            print(f"   • From: {headers.get('From')} | Subject: {headers.get('Subject')}")
        print("\nVESPER Gmail integration is now fully authorized and active!\n")
    except Exception as e:
        print(f"Warning: Verification query failed ({e}), but token was successfully saved.")


if __name__ == "__main__":
    main()
