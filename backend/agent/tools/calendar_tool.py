"""VESPER Google Calendar v3 Tool Integration.

Handles listing today's agenda, scheduling meetings, and checking time conflicts.
Uses OAuth Desktop App credentials configured in backend/.env.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.shared.config import (
    GOOGLE_CALENDAR_CLIENT_ID,
    GOOGLE_CALENDAR_CLIENT_SECRET,
)

logger = logging.getLogger("vesper.agent.tools.calendar")

CREDENTIALS_PATH = Path(__file__).resolve().parent.parent.parent / "credentials" / "google_calendar_credentials.json"
TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / "credentials" / "google_calendar_token.json"


class GoogleCalendarTool:
    """Interface to Google Calendar v3 API."""

    def __init__(self) -> None:
        self.client_id = GOOGLE_CALENDAR_CLIENT_ID
        self.client_secret = GOOGLE_CALENDAR_CLIENT_SECRET
        self.credentials_file = CREDENTIALS_PATH

    def is_configured(self) -> bool:
        """Returns True if Google Calendar credentials are present."""
        return bool(self.client_id and self.client_secret) or self.credentials_file.exists()

    async def list_upcoming_events(self, max_results: int = 5) -> List[Dict[str, Any]]:
        """Lists upcoming calendar events."""
        if not self.is_configured():
            return []

        # Return mock / active sample if user has not yet completed interactive browser OAuth
        if not TOKEN_PATH.exists():
            now = datetime.datetime.now()
            return [
                {
                    "summary": "Team Sync & Architectural Review",
                    "start": (now + datetime.timedelta(hours=2)).strftime("%I:%M %p"),
                    "end": (now + datetime.timedelta(hours=3)).strftime("%I:%M %p"),
                    "location": "Google Meet",
                    "status": "confirmed",
                    "source": "sandbox",
                }
            ]

        # Standard Google API execution when token is present
        def _fetch_events_sync() -> List[Dict[str, Any]]:
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build

                creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, "w") as token:
                        token.write(creds.to_json())

                service: Any = build("calendar", "v3", credentials=creds)
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

                events_result = service.events().list(
                    calendarId="primary",
                    timeMin=now_iso,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()

                items = events_result.get("items", [])
                parsed = []
                for item in items:
                    start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date"))
                    parsed.append({
                        "id": item.get("id"),
                        "summary": item.get("summary", "Untitled Event"),
                        "start": start,
                        "location": item.get("location", ""),
                    })
                return parsed
            except Exception as e:
                logger.warning(f"[Calendar] Error querying Google Calendar API: {e}")
                return []

        import asyncio
        return await asyncio.to_thread(_fetch_events_sync)

    async def create_event(
        self,
        summary: str,
        start_time_str: str,
        end_time_str: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Schedules a new event on Google Calendar."""
        start_dt, end_dt = self._parse_event_time(start_time_str, end_time_str)

        if not TOKEN_PATH.exists():
            return {
                "id": f"event_mock_{int(datetime.datetime.now().timestamp())}",
                "summary": summary,
                "start": start_dt.strftime("%I:%M %p"),
                "end": end_dt.strftime("%I:%M %p"),
                "status": "confirmed_mock",
                "html_link": "https://calendar.google.com",
            }

        def _create_event_sync() -> Dict[str, Any]:
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build

                creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, "w") as token:
                        token.write(creds.to_json())

                service: Any = build("calendar", "v3", credentials=creds)
                
                # Use timezone-aware ISO strings
                local_tz = datetime.datetime.now().astimezone().tzinfo
                s_dt = start_dt if start_dt.tzinfo else start_dt.replace(tzinfo=local_tz)
                e_dt = end_dt if end_dt.tzinfo else end_dt.replace(tzinfo=local_tz)
                body = {
                    "summary": summary,
                    "description": description or "Scheduled by Alfred",
                    "start": {"dateTime": s_dt.isoformat()},
                    "end": {"dateTime": e_dt.isoformat()},
                }
                if location:
                    body["location"] = location

                created = service.events().insert(calendarId="primary", body=body).execute()
                return {
                    "id": created.get("id"),
                    "summary": created.get("summary", summary),
                    "start": start_dt.strftime("%I:%M %p"),
                    "end": end_dt.strftime("%I:%M %p"),
                    "status": "confirmed",
                    "html_link": created.get("htmlLink", "https://calendar.google.com"),
                }
            except Exception as e:
                logger.warning(f"[Calendar] Error creating event via Google Calendar API: {e}")
                return {
                    "id": f"event_fallback_{int(datetime.datetime.now().timestamp())}",
                    "summary": summary,
                    "start": start_dt.strftime("%I:%M %p"),
                    "end": end_dt.strftime("%I:%M %p"),
                    "status": "fallback_local",
                    "error": str(e),
                }

        import asyncio
        return await asyncio.to_thread(_create_event_sync)

    async def delete_event(self, event_id: str) -> bool:
        """Deletes an event from Google Calendar by ID."""
        if not TOKEN_PATH.exists() or not event_id:
            return True

        def _delete_sync() -> bool:
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build

                creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(TOKEN_PATH, "w") as token:
                        token.write(creds.to_json())

                service: Any = build("calendar", "v3", credentials=creds)
                service.events().delete(calendarId="primary", eventId=event_id).execute()
                logger.info(f"[Calendar] Successfully deleted event {event_id} from Google Calendar.")
                return True
            except Exception as e:
                logger.warning(f"[Calendar] Error deleting event {event_id}: {e}")
                return False

        import asyncio
        return await asyncio.to_thread(_delete_sync)

    @staticmethod
    def _parse_event_time(start_str: str, end_str: Optional[str] = None) -> tuple[datetime.datetime, datetime.datetime]:
        """Parses conversational time expressions (e.g. '5.30 today', '5:30 PM', 'tomorrow at 3pm') into datetimes."""
        import re

        now = datetime.datetime.now()
        target_date = now.date()

        text = start_str.lower().strip()
        if "tomorrow" in text:
            target_date = target_date + datetime.timedelta(days=1)
        elif "day after tomorrow" in text:
            target_date = target_date + datetime.timedelta(days=2)

        # Match patterns like 5:30, 5.30, 5pm, 17:30, 5:30 pm
        match = re.search(r"(\d{1,2})[:.]?(\d{2})?\s*(am|pm)?", text)
        hour = 12
        minute = 0
        if match:
            h_str, m_str, ampm = match.groups()
            hour = int(h_str)
            minute = int(m_str) if m_str else 0
            if ampm:
                if ampm == "pm" and hour < 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0
            else:
                # If unspecified and hour is between 1 and 7, assume PM for workday/evening
                if 1 <= hour <= 7:
                    hour += 12

        start_dt = datetime.datetime(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
            hour=hour,
            minute=minute,
        )
        # Default duration 30 minutes
        end_dt = start_dt + datetime.timedelta(minutes=30)
        return start_dt, end_dt

