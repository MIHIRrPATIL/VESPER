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

    async def list_upcoming_events(
        self,
        max_results: int = 10,
        time_min: Optional[datetime.datetime] = None,
        time_max: Optional[datetime.datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Lists upcoming calendar events with optional time boundaries."""
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

                local_tz = datetime.datetime.now().astimezone().tzinfo
                if time_min:
                    t_min = time_min if time_min.tzinfo else time_min.replace(tzinfo=local_tz)
                    time_min_iso = t_min.astimezone(datetime.timezone.utc).isoformat()
                else:
                    time_min_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

                params: dict[str, Any] = {
                    "calendarId": "primary",
                    "timeMin": time_min_iso,
                    "maxResults": max_results,
                    "singleEvents": True,
                    "orderBy": "startTime",
                }
                if time_max:
                    t_max = time_max if time_max.tzinfo else time_max.replace(tzinfo=local_tz)
                    params["timeMax"] = t_max.astimezone(datetime.timezone.utc).isoformat()

                events_result = service.events().list(**params).execute()

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

    async def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start_time_str: Optional[str] = None,
        end_time_str: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates an existing Google Calendar event via PATCH."""
        if not TOKEN_PATH.exists() or not event_id:
            return {"id": event_id, "status": "mock_updated", "summary": summary}

        def _update_sync() -> Dict[str, Any]:
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

                body: Dict[str, Any] = {}
                if summary is not None:
                    body["summary"] = summary
                if description is not None:
                    body["description"] = description

                local_tz = datetime.datetime.now().astimezone().tzinfo
                if start_date:
                    body["start"] = {"date": start_date}
                    body["end"] = {"date": end_date or start_date}
                elif start_time_str:
                    s_dt, e_dt = self._parse_event_time(start_time_str, end_time_str)
                    s_dt = s_dt if s_dt.tzinfo else s_dt.replace(tzinfo=local_tz)
                    e_dt = e_dt if e_dt.tzinfo else e_dt.replace(tzinfo=local_tz)
                    body["start"] = {"dateTime": s_dt.isoformat()}
                    body["end"] = {"dateTime": e_dt.isoformat()}

                updated = service.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
                logger.info(f"[Calendar] Successfully updated event {event_id}: '{summary}'")
                return {
                    "id": updated.get("id"),
                    "summary": updated.get("summary", summary),
                    "status": "updated",
                    "html_link": updated.get("htmlLink", "https://calendar.google.com"),
                }
            except Exception as e:
                logger.warning(f"[Calendar] Error updating event {event_id}: {e}")
                return {"id": event_id, "status": "error", "error": str(e)}

        import asyncio
        return await asyncio.to_thread(_update_sync)

    async def sync_task_event(
        self,
        task_id: str,
        title: str,
        deadline: Optional[Any] = None,
        done: bool = False,
        priority: str = "normal",
        is_reminder: bool = False,
        calendar_event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronizes a task or reminder with Google Calendar.
        
        - If calendar_event_id exists, updates the event summary, completion prefix, and timing.
        - If calendar_event_id is None, creates a new event and returns its ID.
        - Untimed tasks are synced as clean All-Day Events.
        - Timed tasks/reminders are scheduled at their target deadline.
        """
        clean_title = title.strip()
        for prefix in ["Task:", "Reminder:", "✓ [Completed] Task:", "✓ [Completed] Reminder:", "✓ [Completed]"]:
            if clean_title.startswith(prefix):
                clean_title = clean_title[len(prefix):].strip()

        item_label = "Reminder" if is_reminder else "Task"
        if done:
            event_summary = f"✓ [Completed] {item_label}: {clean_title}"
        else:
            event_summary = f"{item_label}: {clean_title}"

        now = datetime.datetime.now().astimezone()
        local_tz = now.tzinfo
        today_iso = now.date().isoformat()
        tomorrow_iso = (now.date() + datetime.timedelta(days=1)).isoformat()

        deadline_dt: Optional[datetime.datetime] = None
        if deadline:
            if isinstance(deadline, str):
                try:
                    deadline_dt = datetime.datetime.fromisoformat(deadline)
                except Exception:
                    pass
            elif isinstance(deadline, datetime.datetime):
                deadline_dt = deadline
            elif isinstance(deadline, datetime.date):
                deadline_dt = datetime.datetime.combine(deadline, datetime.time(hour=12, minute=0))

        if deadline_dt:
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=local_tz)
            else:
                deadline_dt = deadline_dt.astimezone(local_tz)

        description = (
            f"VESPER {item_label}\n"
            f"Task ID: {task_id}\n"
            f"Priority: {priority.upper()}\n"
            f"Status: {'COMPLETED' if done else 'PENDING'}\n"
            f"Last Synced: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

        if calendar_event_id:
            if deadline_dt:
                start_iso = deadline_dt.isoformat()
                end_iso = (deadline_dt + datetime.timedelta(minutes=30)).isoformat()
                up_res = await self.update_event(
                    event_id=calendar_event_id,
                    summary=event_summary,
                    description=description,
                    start_time_str=start_iso,
                    end_time_str=end_iso,
                )
            else:
                up_res = await self.update_event(
                    event_id=calendar_event_id,
                    summary=event_summary,
                    description=description,
                    start_date=today_iso,
                    end_date=tomorrow_iso,
                )
            if up_res.get("status") not in ["error", "fallback_error"]:
                return up_res
            logger.info(f"[Calendar] Event '{calendar_event_id}' could not be updated ({up_res.get('error')}); creating new event.")

        if not TOKEN_PATH.exists():
            mock_id = f"event_mock_{task_id}_{int(now.timestamp())}"
            return {
                "id": mock_id,
                "summary": event_summary,
                "status": "mock_created",
            }

        def _insert_sync() -> Dict[str, Any]:
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

                body: Dict[str, Any] = {
                    "summary": event_summary,
                    "description": description,
                }

                if deadline_dt:
                    s_iso = deadline_dt.isoformat()
                    e_iso = (deadline_dt + datetime.timedelta(minutes=30)).isoformat()
                    body["start"] = {"dateTime": s_iso}
                    body["end"] = {"dateTime": e_iso}
                else:
                    body["start"] = {"date": today_iso}
                    body["end"] = {"date": tomorrow_iso}


                created = service.events().insert(calendarId="primary", body=body).execute()
                logger.info(f"[Calendar] Created event for {item_label} '{clean_title}': ID {created.get('id')}")
                return {
                    "id": created.get("id"),
                    "summary": created.get("summary", event_summary),
                    "status": "confirmed",
                    "html_link": created.get("htmlLink", "https://calendar.google.com"),
                }
            except Exception as e:
                logger.warning(f"[Calendar] Error creating event for {item_label} '{clean_title}': {e}")
                return {
                    "id": f"event_fallback_{task_id}",
                    "summary": event_summary,
                    "status": "fallback_error",
                    "error": str(e),
                }

        import asyncio
        return await asyncio.to_thread(_insert_sync)

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
                # If unspecified, check natural language time qualifiers
                if any(w in text for w in ("tonight", "evening", "night", "afternoon")) and hour < 12:
                    hour += 12
                elif any(w in text for w in ("morning",)) and hour == 12:
                    hour = 0
                elif 1 <= hour <= 7:
                    # Common afternoon/evening hours (e.g., 5:30 -> 17:30)
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

