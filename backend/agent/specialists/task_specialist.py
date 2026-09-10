"""VESPER Task, Reminder, and Calendar Specialist Agent.

Cleanly diagnoses and orchestrates:
  1. Tasks: Actionable todos without specific alarms (Supabase tasks).
  2. Reminders: Time-bound alerts (e.g. "remind me at 5:30 today to pick up mom")
     anchored with due timestamps and synced to Google Calendar.
  3. Calendar Events: Scheduled meetings and appointments with start/end times and Google Calendar integration.
  4. Daily Agenda: Consolidated briefing combining upcoming meetings, today's reminders, and pending tasks.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
from typing import Any, Dict, List, Optional

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.agent.specialists.task_triage import AsyncTaskTriageWorker
from backend.agent.tools.calendar_tool import GoogleCalendarTool
from backend.agent.title_normalizer import classify_action_type, extract_time_phrase, normalize_title
from backend.data.models import PriorityLevel, TaskCreate, TaskModel
from backend.data.repositories.tasks import TaskRepository
from backend.voice.tts.normalizer import SpeechNormalizer

logger = logging.getLogger("vesper.agent.specialists.tasks")


class TaskSpecialist(BaseSpecialist):
    """Specialist sub-agent managing tasks, time-anchored reminders, and Google Calendar events."""

    @staticmethod
    def _format_spoken_datetime(dt_str: Optional[str]) -> str:
        if not dt_str:
            return ""
        return SpeechNormalizer.format_spoken_datetime(dt_str)

    @classmethod
    def _format_event_list_speech(
        cls, events: List[Dict[str, Any]], context_label: Optional[str] = None
    ) -> str:
        """Formats upcoming events into articulate, natural spoken English without robotic repetition."""
        if not events:
            filter_label = f" for {context_label}" if context_label else ""
            return f"Your calendar has no events scheduled{filter_label}, sir."

        # Group events by summary to prevent repeating identical titles (e.g. recurring syncs)
        groups: Dict[str, List[str]] = {}
        for ev in events[:5]:
            title = ev.get("summary") or "Scheduled Event"
            time_str = ev.get("spoken_time") or cls._format_spoken_datetime(ev.get("start") or ev.get("time"))
            groups.setdefault(title, []).append(time_str)

        entries = []
        for title, times in groups.items():
            if len(times) == 1:
                entries.append(f"'{title}' {times[0]}")
            elif len(times) == 2:
                entries.append(f"'{title}' {times[0]} and {times[1]}")
            else:
                formatted_times = ", ".join(times[:-1]) + f", and {times[-1]}"
                entries.append(f"'{title}' {formatted_times}")

        if len(entries) == 1:
            joined = entries[0]
        elif len(entries) == 2:
            joined = f"{entries[0]}, and {entries[1]}"
        else:
            joined = ", ".join(entries[:-1]) + f", and {entries[-1]}"

        if context_label:
            return f"On your schedule for {context_label}: {joined}."
        return f"Upcoming on your calendar: {joined}."

    @staticmethod
    def _resolve_filter_range(
        date_val: Optional[str] = None,
        start_val: Optional[str] = None,
        end_val: Optional[str] = None,
    ) -> tuple[Optional[datetime.datetime], Optional[datetime.datetime]]:
        """Resolves conversational date filters or ranges into timezone-aware datetimes."""
        import re

        now = datetime.datetime.now().astimezone()
        today = now.date()
        local_tz = now.tzinfo

        def parse_single_date(s: str) -> datetime.date:
            s_clean = s.lower().strip()
            if s_clean in ["today", "now"]:
                return today
            if s_clean == "tomorrow":
                return today + datetime.timedelta(days=1)
            if s_clean == "yesterday":
                return today - datetime.timedelta(days=1)
            days_map = {
                "monday": 0, "tuesday": 1, "wednesday": 2,
                "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
            }
            for day_name, day_idx in days_map.items():
                if day_name in s_clean:
                    days_ahead = (day_idx - today.weekday() + 7) % 7
                    if days_ahead == 0 and "next" in s_clean:
                        days_ahead = 7
                    return today + datetime.timedelta(days=days_ahead)
            m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s_clean)
            if m:
                try:
                    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    pass
            return today

        if start_val or end_val:
            d_start = parse_single_date(start_val) if start_val else today
            d_end = parse_single_date(end_val) if end_val else d_start + datetime.timedelta(days=7)
            t_min = datetime.datetime.combine(d_start, datetime.time.min, tzinfo=local_tz)
            t_max = datetime.datetime.combine(d_end, datetime.time.max, tzinfo=local_tz)
            return t_min, t_max

        if date_val:
            s_clean = date_val.lower().strip()
            if "this week" in s_clean:
                days_to_sunday = 6 - today.weekday()
                t_min = datetime.datetime.combine(today, datetime.time.min, tzinfo=local_tz)
                t_max = datetime.datetime.combine(today + datetime.timedelta(days=days_to_sunday), datetime.time.max, tzinfo=local_tz)
                return t_min, t_max
            elif "next week" in s_clean:
                next_mon = today + datetime.timedelta(days=(7 - today.weekday()))
                next_sun = next_mon + datetime.timedelta(days=6)
                t_min = datetime.datetime.combine(next_mon, datetime.time.min, tzinfo=local_tz)
                t_max = datetime.datetime.combine(next_sun, datetime.time.max, tzinfo=local_tz)
                return t_min, t_max
            else:
                d = parse_single_date(s_clean)
                t_min = datetime.datetime.combine(d, datetime.time.min, tzinfo=local_tz)
                t_max = datetime.datetime.combine(d, datetime.time.max, tzinfo=local_tz)
                return t_min, t_max

        return None, None

    @staticmethod
    def _classify_task_timing(
        task: Any,
        t_min: Optional[datetime.datetime],
        t_max: Optional[datetime.datetime],
        local_tz: Any,
    ) -> str:
        """Classifies a task's timing relative to a time window [t_min, t_max].

        Returns:
            - 'scheduled': task.deadline falls within [t_min, t_max]
            - 'created_window': task has no deadline, but task.created_at falls within [t_min, t_max]
            - 'overdue': task.deadline < t_min
            - 'backlog': task has no deadline, but task.created_at < t_min
            - 'future': task.deadline > t_max or task.created_at > t_max
            - 'current': when no filter window is specified or dates are absent
        """
        if not t_min or not t_max:
            return "current"

        def _to_tz(dt_val: Any) -> Optional[datetime.datetime]:
            if not dt_val:
                return None
            if isinstance(dt_val, str):
                try:
                    dt_val = datetime.datetime.fromisoformat(dt_val)
                except Exception:
                    return None
            if isinstance(dt_val, datetime.date) and not isinstance(dt_val, datetime.datetime):
                dt_val = datetime.datetime.combine(dt_val, datetime.time.min)
            if isinstance(dt_val, datetime.datetime):
                if dt_val.tzinfo is None:
                    return dt_val.replace(tzinfo=local_tz)
                return dt_val.astimezone(local_tz)
            return None

        deadline = _to_tz(getattr(task, "deadline", None))
        created = _to_tz(getattr(task, "created_at", None))

        if deadline is not None:
            if t_min <= deadline <= t_max:
                return "scheduled"
            elif deadline < t_min:
                return "overdue"
            else:
                return "future"

        if created is not None:
            if t_min <= created <= t_max:
                return "created_window"
            elif created < t_min:
                # Tasks from prior days without a deadline are backlog items
                return "backlog"
            else:
                return "future"

        return "created_window"

    async def _fetch_calendar_events(
        self,
        max_results: int = 10,
        time_min: Optional[datetime.datetime] = None,
        time_max: Optional[datetime.datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Safely queries calendar events supporting both time-filtered and legacy/mock signatures."""
        try:
            return await self.calendar.list_upcoming_events(
                max_results=max_results, time_min=time_min, time_max=time_max
            )
        except TypeError:
            return await self.calendar.list_upcoming_events(max_results=max_results)

    def __init__(
        self,
        repo: Optional[TaskRepository] = None,
        triage_worker: Optional[AsyncTaskTriageWorker] = None,
        calendar_tool: Optional[GoogleCalendarTool] = None,
        notif_service: Optional[Any] = None,
    ) -> None:
        self.repo = repo or TaskRepository()
        self.triage_worker = triage_worker or AsyncTaskTriageWorker()
        self.calendar = calendar_tool or GoogleCalendarTool()
        self.notif_service = notif_service

    @property
    def name(self) -> str:
        return "tasks"

    @property
    def description(self) -> str:
        return (
            "Manages tasks (todos), time-bound reminders, and scheduled Google Calendar events. "
            "Cleanly distinguishes between todos, timed reminders, and calendar appointments."
        )

    def get_capabilities(self) -> str:
        return (
            "Create and list todos/tasks, set time-anchored reminders (e.g. 'at 5:30 today'), "
            "schedule Google Calendar events/meetings, and retrieve the full daily briefing."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "add_task",
                "description": "Creates a general todo or task without a specific time anchor (e.g. 'buy groceries', 'finish presentation').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title or description of the task."},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Priority level.",
                        },
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "set_reminder",
                "description": "Sets a time-anchored reminder for a specific hour or date (e.g. 'pick up mom at 5:30 today', 'call doctor tomorrow at 10am').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reminder": {"type": "string", "description": "What to remind you about (e.g. 'pick up my mom')."},
                        "time": {"type": "string", "description": "Specific time anchor (e.g. '5:30 today', '5:30 PM', 'tomorrow at 10am')."},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Optional priority.",
                        },
                    },
                    "required": ["reminder", "time"],
                },
            },
            {
                "name": "list_reminders",
                "description": "Lists pending time-anchored reminders that were set for today or upcoming days.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum reminders to return (default: 5)."},
                    },
                },
            },
            {
                "name": "schedule_event",
                "description": "Schedules a calendar event, meeting, or appointment on Google Calendar.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Meeting or event title (e.g. 'Design review with Alex')."},
                        "start_time": {"type": "string", "description": "Start time (e.g. 'tomorrow at 3pm', '5:30 today')."},
                        "end_time": {"type": "string", "description": "Optional end time."},
                        "location": {"type": "string", "description": "Meeting location or link."},
                        "description": {"type": "string", "description": "Meeting description or agenda."},
                    },
                    "required": ["summary", "start_time"],
                },
            },
            {
                "name": "list_tasks",
                "description": "Lists current pending todo tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_completed": {
                            "type": "boolean",
                            "description": "Whether to include completed tasks.",
                        },
                        "limit": {"type": "integer", "description": "Maximum tasks to return (default: 5)."},
                    },
                },
            },
            {
                "name": "list_calendar_events",
                "description": "Lists scheduled appointments and events from Google Calendar. Can filter by day (e.g. 'today', 'tomorrow', 'this week', 'next week') or date range (start_date, end_date).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Optional single day or relative term (e.g. 'today', 'tomorrow', 'this week', 'next week', 'YYYY-MM-DD').",
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Optional start of date filter range (e.g. 'today', 'Monday', '2026-09-05').",
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Optional end of date filter range (e.g. 'Friday', '2026-09-12').",
                        },
                        "max_results": {"type": "integer", "description": "Maximum events to fetch (default: 10)."},
                    },
                },
            },
            {
                "name": "complete_task",
                "description": "Marks an existing task or reminder as completed by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Unique ID of the task to complete."},
                    },
                    "required": ["task_id"],
                },
            },
            {
                "name": "delete_task",
                "description": "Deletes a task or reminder by ID or title.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Unique ID of the task to delete."},
                        "title": {"type": "string", "description": "Optional title match."},
                    },
                },
            },
            {
                "name": "update_task",
                "description": "Renames, updates, or reschedules an existing task, reminder, or calendar event by title, time anchor (e.g. '9 o'clock event'), or ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Title or time identifier of the existing task or event (e.g. '9 o'clock event', 'Event', 'Attend the 8 o'clock')."},
                        "task_id": {"type": "string", "description": "Optional unique ID if known."},
                        "new_title": {"type": "string", "description": "New title or summary for the task/event (e.g. 'AWS Workshop')."},
                        "new_time": {"type": "string", "description": "Optional new time or date if rescheduling (e.g. '10:00 AM', 'tomorrow at 3pm'). Leave empty if only renaming."},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Optional updated priority.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "clear_reminders",
                "description": "Deletes or clears all active reminders and their synced calendar entries.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "get_daily_agenda",
                "description": "Retrieves the consolidated daily briefing: today's calendar events, active reminders, and pending tasks. Supports querying a specific target day.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Target date for the daily briefing (e.g. 'today', 'tomorrow', 'YYYY-MM-DD'). Defaults to 'today'.",
                        },
                    },
                },
            },
            {
                "name": "list_mobile_notifications",
                "description": "Retrieves recent, urgent, or unread notifications received from the mobile companion app (WhatsApp, Slack, Telegram, Gmail, server alerts).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum number of notifications to return (default: 5)"},
                        "unread_only": {"type": "boolean", "description": "Whether to return unread alerts only (default: false)"},
                        "app": {"type": "string", "description": "Optional app name or package filter (e.g. 'whatsapp', 'slack', 'gmail')"},
                    },
                },
            },
            {
                "name": "search_mobile_notifications",
                "description": "Searches stored mobile notifications (WhatsApp, Telegram, Slack, SMS, Gmail) by sender/contact name, app, or keyword content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keyword, topic, or question to search for in notification content."},
                        "sender": {"type": "string", "description": "Sender, contact, or group name (e.g. 'Tia Shah', 'Mom')."},
                        "app": {"type": "string", "description": "Optional app name or package filter (e.g. 'whatsapp', 'slack', 'gmail')."},
                        "limit": {"type": "integer", "description": "Maximum number of notifications to return (default: 5)."},
                    },
                },
            },
        ]

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        try:
            act = action.lower().strip()

            # ── 1. Set Reminder ───────────────────────────────────────────────
            if act in ["set_reminder", "add_reminder", "reminder", "remind"]:
                reminder_text = str(params.get("reminder") or params.get("title") or "").strip()
                time_str = str(params.get("time") or params.get("time_str") or "").strip()
                if not reminder_text and params.get("text"):
                    reminder_text = str(params["text"]).strip()

                if not reminder_text:
                    return SpecialistResult(success=False, action=action, error="Reminder content is required.")

                # Clean and normalize reminder text, stripping duplicate trailing times or filler
                reminder_text = normalize_title(reminder_text)
                if not time_str:
                    time_str = "today"

                p_str = params.get("priority", "normal").lower()
                priority = PriorityLevel.HIGH if ("high" in p_str or "urgent" in p_str) else PriorityLevel.NORMAL

                # 1. Schedule on Google Calendar so it has an alert/time block
                cal_event = await self.calendar.create_event(
                    summary=f"Reminder: {reminder_text}",
                    start_time_str=time_str,
                    description=f"Automated reminder set by Alfred: {reminder_text}",
                )

                # 2. Persist in Supabase task repo as reminder with parsed deadline
                parsed_deadline: Optional[datetime.datetime] = None
                start_val = cal_event.get("start")
                if start_val:
                    try:
                        parsed_deadline = datetime.datetime.fromisoformat(start_val)
                    except Exception:
                        pass
                if not parsed_deadline and time_str:
                    t_min, _ = self._resolve_filter_range(date_val=time_str)
                    parsed_deadline = t_min

                task_obj = self.repo.create(
                    TaskCreate(
                        title=f"Reminder: {reminder_text} ({cal_event.get('start', time_str)})",
                        priority=priority,
                        deadline=parsed_deadline,
                        metadata={
                            "item_type": "reminder",
                            "reminder_text": reminder_text,
                            "time_str": time_str,
                            "formatted_time": cal_event.get("start"),
                            "calendar_event_id": cal_event.get("id"),
                        },
                    )
                )

                time_display = self._format_spoken_datetime(cal_event.get("start")) or time_str
                speech = f"Very well, sir. I have set a reminder for {time_display}: '{reminder_text}', and logged it onto your calendar."
                return SpecialistResult(
                    success=True,
                    action="set_reminder",
                    data={
                        "task_id": task_obj.id,
                        "reminder": reminder_text,
                        "time": time_display,
                        "calendar_event": cal_event,
                    },
                    speech_summary=speech,
                    card_payload={
                        "type": "reminder_card",
                        "reminder": reminder_text,
                        "time": time_display,
                        "calendar_id": cal_event.get("id"),
                    },
                )

            # ── 2. Add Task (Todo) ───────────────────────────────────────────
            elif act in ["add_task", "create_task", "create", "new_task", "add"]:
                title = str(params.get("title") or params.get("task") or "").strip()
                if not title:
                    return SpecialistResult(success=False, action=action, error="Task title is required.")

                # If the title clearly requests a reminder with a time anchor, or is classified as reminder, delegate to set_reminder!
                action_type = classify_action_type(title)
                extracted_time = extract_time_phrase(title)
                time_param = params.get("time") or params.get("start_time") or extracted_time

                if action_type == "reminder" or (action_type == "event" and time_param):
                    norm_title = normalize_title(title)
                    time_found = str(time_param or "today").strip()
                    if action_type == "event":
                        return await self.execute("schedule_event", {"summary": norm_title, "start_time": time_found})
                    return await self.execute("set_reminder", {"reminder": norm_title, "time": time_found, "priority": params.get("priority")})

                # Clean conversational noise and trailing dates
                title = normalize_title(title)

                p_str = params.get("priority", "normal").lower()
                priority = PriorityLevel.NORMAL
                if "urgent" in p_str or "high" in p_str:
                    priority = PriorityLevel.HIGH
                elif "low" in p_str:
                    priority = PriorityLevel.LOW

                # Check if a time parameter is present to set deadline
                parsed_deadline: Optional[datetime.datetime] = None
                if time_param and str(time_param).lower() not in ("today", "none", ""):
                    try:
                        s_dt, _ = self.calendar._parse_event_time(str(time_param))
                        parsed_deadline = s_dt
                    except Exception as te:
                        logger.debug(f"[Tasks] Could not parse task time '{time_param}': {te}")

                # Instant creation in Supabase (<30ms)
                task_obj = self.repo.create(
                    TaskCreate(
                        title=title,
                        priority=priority,
                        deadline=parsed_deadline,
                        metadata={
                            "item_type": "task",
                            "time_str": str(time_param) if time_param else None,
                        },
                    )
                )

                # Auto-sync task to Google Calendar
                try:
                    cal_res = await self.calendar.sync_task_event(
                        task_id=task_obj.id,
                        title=task_obj.title,
                        deadline=task_obj.deadline,
                        done=task_obj.done,
                        priority=task_obj.priority.value if hasattr(task_obj.priority, "value") else str(task_obj.priority),
                        is_reminder=False,
                    )
                    if cal_res.get("id"):
                        new_meta = dict(task_obj.metadata or {})
                        new_meta["calendar_event_id"] = cal_res["id"]
                        new_meta["synced_to_calendar"] = True
                        self.repo.update(task_obj.id, {"metadata": new_meta})
                except Exception as ce:
                    logger.warning(f"[TaskSpecialist] Calendar auto-sync failed for task {task_obj.id}: {ce}")

                # Fire Async AI Triage in background
                asyncio.create_task(
                    self.triage_worker.triage_task_in_background(task_obj.id, task_obj.title)
                )

                time_note = ""
                if parsed_deadline:
                    time_note = f" for {self._format_spoken_datetime(parsed_deadline.isoformat())}"

                return SpecialistResult(
                    success=True,
                    action=action,
                    data={"task_id": task_obj.id, "title": task_obj.title, "priority": task_obj.priority, "deadline": str(parsed_deadline)},
                    speech_summary=f"Added '{task_obj.title}'{time_note} to your task list, sir.",
                    card_payload={
                        "type": "task_created",
                        "title": task_obj.title,
                        "priority": task_obj.priority,
                        "id": task_obj.id,
                    },
                )

            # ── 3. Schedule Calendar Event ────────────────────────────────────
            elif act in ["schedule_event", "create_event", "add_event", "schedule_meeting"]:
                summary = str(params.get("summary") or params.get("title") or "").strip()
                start_time = str(params.get("start_time") or params.get("time") or "").strip()
                if not summary:
                    return SpecialistResult(success=False, action=action, error="Event summary is required.")
                if not start_time:
                    return SpecialistResult(success=False, action=action, error="Start time is required.")

                summary = normalize_title(summary)
                end_time = params.get("end_time")
                location = params.get("location")
                description = params.get("description")

                cal_event = await self.calendar.create_event(
                    summary=summary,
                    start_time_str=start_time,
                    end_time_str=end_time,
                    description=description,
                    location=location,
                )

                # Persist in local repo as event so it can be updated or deleted seamlessly
                parsed_deadline: Optional[datetime.datetime] = None
                try:
                    s_dt, _ = self.calendar._parse_event_time(start_time, end_time)
                    parsed_deadline = s_dt
                except Exception:
                    pass

                task_obj = self.repo.create(
                    TaskCreate(
                        title=summary,
                        priority=PriorityLevel.NORMAL,
                        deadline=parsed_deadline,
                        metadata={
                            "item_type": "event",
                            "start_time_str": start_time,
                            "calendar_event_id": cal_event.get("id"),
                        },
                    )
                )

                time_display = self._format_spoken_datetime(cal_event.get("start")) or start_time
                speech = f"Scheduled '{summary}' {time_display} on your Google Calendar, sir."
                return SpecialistResult(
                    success=True,
                    action="schedule_event",
                    data={**cal_event, "task_id": task_obj.id},
                    speech_summary=speech,
                    card_payload={"type": "calendar_event_card", "event": cal_event},
                )

            # ── 4. List Reminders ─────────────────────────────────────────────
            elif act in ["list_reminders", "get_reminders", "reminders", "check_reminders"]:
                limit = int(params.get("limit", 5))
                tasks = self.repo.list(include_completed=False, limit=20)
                reminders = [
                    t for t in tasks
                    if (t.metadata and t.metadata.get("item_type") == "reminder") or "reminder" in t.title.lower()
                ][:limit]

                if not reminders:
                    # Fallback to the most recently created task if any exists
                    if tasks:
                        latest = tasks[0]
                        speech = f"You asked me to record '{latest.title}', sir."
                        return SpecialistResult(
                            success=True,
                            action="list_reminders",
                            data={"reminders": [{"id": latest.id, "title": latest.title}]},
                            speech_summary=speech,
                            card_payload={"type": "reminder_list", "reminders": [{"title": latest.title}]},
                        )
                    return SpecialistResult(
                        success=True,
                        action="list_reminders",
                        data={"reminders": [], "count": 0},
                        speech_summary="You have no active reminders logged at the moment, sir.",
                    )

                items = [{"id": r.id, "title": r.title, "time": r.metadata.get("formatted_time", "") if r.metadata else ""} for r in reminders]
                titles = ", ".join([f"'{it['title']}'" for it in items[:3]])
                speech = f"You have {len(items)} active reminder{'s' if len(items) != 1 else ''}, sir: {titles}."

                return SpecialistResult(
                    success=True,
                    action="list_reminders",
                    data={"reminders": items, "count": len(items)},
                    speech_summary=speech,
                    card_payload={"type": "reminder_list", "reminders": items},
                )

            # ── 5. List Tasks ─────────────────────────────────────────────────
            elif act in ["list_tasks", "get_tasks", "list", "show_tasks"]:
                include_done = params.get("include_completed", False)
                limit = int(params.get("limit", 5))
                date_param = str(params.get("date") or "").strip().lower()
                query_param = str(params.get("query") or (context or {}).get("query") or "").strip().lower()
                is_today = date_param == "today" or "today" in query_param

                all_tasks = self.repo.list(include_completed=include_done, limit=50)
                if is_today:
                    local_tz = datetime.datetime.now().astimezone().tzinfo
                    t_min, t_max = self._resolve_filter_range(date_val="today")
                    filtered = [
                        t for t in all_tasks
                        if self._classify_task_timing(t, t_min, t_max, local_tz) in ("scheduled", "created_window")
                    ][:limit]
                    overdue_list = [
                        t for t in all_tasks
                        if self._classify_task_timing(t, t_min, t_max, local_tz) == "overdue"
                    ]
                    task_items = [{"id": t.id, "title": t.title, "priority": t.priority, "done": t.done} for t in filtered]
                    if not task_items:
                        if overdue_list:
                            speech = f"You have no tasks scheduled specifically for today, sir, though you have {len(overdue_list)} overdue item{'s' if len(overdue_list) != 1 else ''} from earlier."
                        else:
                            speech = "You have no tasks scheduled for today, sir."
                    else:
                        titles = ", ".join([f"'{t['title']}'" for t in task_items[:3]])
                        extra = f" You also have {len(overdue_list)} overdue item{'s' if len(overdue_list) != 1 else ''}." if overdue_list else ""
                        speech = f"You have {len(task_items)} task{'s' if len(task_items) != 1 else ''} scheduled for today: {titles}.{extra}"
                else:
                    tasks = all_tasks[:limit]
                    task_items = [{"id": t.id, "title": t.title, "priority": t.priority, "done": t.done} for t in tasks]
                    if not task_items:
                        speech = "You have no pending tasks on your list at the moment, sir."
                    else:
                        titles = ", ".join([f"'{t['title']}'" for t in task_items[:3]])
                        speech = f"You have {len(task_items)} pending tasks, including {titles}."

                return SpecialistResult(
                    success=True,
                    action=action,
                    data={"tasks": task_items, "count": len(task_items)},
                    speech_summary=speech,
                    card_payload={"type": "task_list", "tasks": task_items},
                )

            # ── 6. List Calendar Events ───────────────────────────────────────
            elif act in ["list_calendar_events", "get_calendar_events", "list_events", "calendar", "events"]:
                max_res = int(params.get("max_results", 10))
                date_filter = params.get("date") or params.get("day")
                start_filter = params.get("start_date") or params.get("from") or params.get("start")
                end_filter = params.get("end_date") or params.get("to") or params.get("end")

                t_min, t_max = self._resolve_filter_range(date_val=date_filter, start_val=start_filter, end_val=end_filter)
                events = await self._fetch_calendar_events(max_results=max_res, time_min=t_min, time_max=t_max)
                is_sandbox = any(e.get("source") == "sandbox" for e in events)

                formatted_events = [
                    {
                        "id": e.get("id"),
                        "summary": e.get("summary"),
                        "start": e.get("start"),
                        "spoken_time": self._format_spoken_datetime(e.get("start")),
                        "location": e.get("location", ""),
                    }
                    for e in events
                ]

                if not formatted_events:
                    filter_label = f" for {date_filter}" if date_filter else ""
                    speech = f"Your calendar has no events scheduled{filter_label}, sir."
                else:
                    speech = self._format_event_list_speech(formatted_events)

                res_data: dict[str, Any] = {"events": formatted_events, "count": len(formatted_events)}
                if is_sandbox:
                    res_data["source"] = "sandbox"

                return SpecialistResult(
                    success=True,
                    action="list_calendar_events",
                    data=res_data,
                    speech_summary=speech,
                    card_payload={"type": "calendar_events_list", "events": formatted_events},
                )

            # ── 7. Complete Task ──────────────────────────────────────────────
            elif act in ["complete_task", "mark_done", "complete", "finish_task"]:
                task_id = str(params.get("task_id") or params.get("id") or "").strip()
                target = self.repo.get(task_id) if task_id else None
                if not target:
                    title_query = str(params.get("title") or params.get("query") or params.get("task") or "").lower().strip()
                    if title_query:
                        tasks = self.repo.list(include_completed=False, limit=50)
                        target = next((t for t in tasks if title_query in t.title.lower()), None)

                if target:
                    self.repo.mark_done(target.id, done=True)
                    # Update linked Google Calendar event
                    try:
                        cal_id = target.metadata.get("calendar_event_id") if target.metadata else None
                        await self.calendar.sync_task_event(
                            task_id=target.id,
                            title=target.title,
                            deadline=target.deadline,
                            done=True,
                            priority=target.priority.value if hasattr(target.priority, "value") else str(target.priority),
                            is_reminder=(target.metadata.get("item_type") == "reminder" if target.metadata else False),
                            calendar_event_id=cal_id,
                        )
                    except Exception as ce:
                        logger.warning(f"[TaskSpecialist] Failed to update calendar on task completion: {ce}")

                    return SpecialistResult(
                        success=True,
                        action=action,
                        data={"task_id": target.id, "done": True, "title": target.title},
                        speech_summary=f"Marked '{target.title}' as completed, sir.",
                        card_payload={"type": "task_completed", "id": target.id, "title": target.title},
                    )
                return SpecialistResult(success=False, action=action, error=f"Task '{task_id}' not found.")

            # ── 7b. Delete Task / Reminder / Event ────────────────────────────
            elif act in [
                "delete_task", "remove_task", "delete_reminder", "remove_reminder",
                "delete", "delete_event", "remove_event", "cancel_event",
            ]:
                task_id = str(params.get("task_id") or params.get("id") or "").strip()
                title_query = str(
                    params.get("title")
                    or params.get("query")
                    or params.get("reminder")
                    or params.get("event")
                    or params.get("task")
                    or ""
                ).lower().strip()

                tasks = self.repo.list(include_completed=True, limit=50)
                target = None
                if task_id:
                    target = next((t for t in tasks if t.id == task_id), None)
                elif title_query:
                    # 1. Title keyword matching
                    q_kw = re.sub(r"\b(the|event|task|meeting|reminder)\b", "", title_query).strip()
                    for t in tasks:
                        t_lower = t.title.lower()
                        if title_query in t_lower or t_lower in title_query or (q_kw and q_kw in t_lower):
                            target = t
                            break

                    # 2. Time-based matching if query contains time (e.g. "8 o'clock")
                    if not target:
                        m_time = re.search(r"(\d{1,2})", title_query)
                        if m_time:
                            hour_val = int(m_time.group(1))
                            for t in tasks:
                                if t.deadline and getattr(t.deadline, "hour", None) in (hour_val, (hour_val + 12) % 24):
                                    target = t
                                    break
                                elif f"{hour_val}" in t.title.lower() or (t.metadata and f"{hour_val}" in str(t.metadata.get("time_str", ""))):
                                    target = t
                                    break

                if target:
                    # Clean up linked calendar event if exists
                    cal_id = target.metadata.get("calendar_event_id") if target.metadata else None
                    if cal_id:
                        await self.calendar.delete_event(cal_id)
                    self.repo.delete(target.id)
                    return SpecialistResult(
                        success=True,
                        action=action,
                        data={"task_id": target.id, "title": target.title},
                        speech_summary=f"Deleted '{target.title}', sir.",
                        card_payload={"type": "task_deleted", "id": target.id, "title": target.title},
                    )

                # Fallback: Check Google Calendar events directly
                if title_query:
                    cal_events = await self._fetch_calendar_events(max_results=20)
                    for ev in cal_events:
                        ev_summary = str(ev.get("summary", "")).lower()
                        if title_query in ev_summary or ev_summary in title_query:
                            await self.calendar.delete_event(ev.get("id"))
                            return SpecialistResult(
                                success=True,
                                action=action,
                                data={"calendar_id": ev.get("id"), "title": ev.get("summary")},
                                speech_summary=f"Removed '{ev.get('summary')}' from your calendar, sir.",
                                card_payload={"type": "task_deleted", "title": ev.get("summary")},
                            )
                    m_time = re.search(r"(\d{1,2})", title_query)
                    if m_time:
                        hour_val = int(m_time.group(1))
                        for ev in cal_events:
                            ev_start = str(ev.get("start", "")).lower()
                            if f"{hour_val}:" in ev_start or f"{hour_val} " in ev_start:
                                await self.calendar.delete_event(ev.get("id"))
                                return SpecialistResult(
                                    success=True,
                                    action=action,
                                    data={"calendar_id": ev.get("id"), "title": ev.get("summary")},
                                    speech_summary=f"Removed '{ev.get('summary')}' from your calendar, sir.",
                                    card_payload={"type": "task_deleted", "title": ev.get("summary")},
                                )

                return SpecialistResult(success=False, action=action, error="No matching task found to delete.")

            # ── 7c. Update / Rename / Reschedule Task or Event ────────────────
            elif act in [
                "update_task", "rename_task", "reschedule_task", "edit_task",
                "update_event", "rename_event", "reschedule_event", "modify_task",
            ]:
                task_id = str(params.get("task_id") or params.get("id") or "").strip()
                query_str = str(
                    params.get("query")
                    or params.get("old_title")
                    or params.get("event")
                    or params.get("task")
                    or ""
                ).strip()
                new_title = str(params.get("new_title") or params.get("title") or "").strip()
                new_time = str(params.get("new_time") or params.get("time") or params.get("start_time") or "").strip()

                if params.get("new_title"):
                    new_title = str(params["new_title"]).strip()
                elif query_str and not new_title:
                    m_to = re.search(r"\bto\s+([A-Za-z0-9\s]+)$", query_str, re.IGNORECASE)
                    if m_to:
                        new_title = m_to.group(1).strip()
                        query_str = query_str[:m_to.start()].strip()

                if new_title:
                    new_title = normalize_title(new_title)

                target = None
                tasks = self.repo.list(include_completed=False, limit=50)

                # 1. Match by ID
                if task_id:
                    target = next((t for t in tasks if t.id == task_id), None)

                # 2. Match by title or time in Supabase repo
                if not target and query_str:
                    q_clean = query_str.lower()
                    q_kw = re.sub(r"\b(the|event|task|meeting|reminder)\b", "", q_clean).strip()
                    for t in tasks:
                        t_title = t.title.lower()
                        if q_clean in t_title or (q_kw and q_kw in t_title):
                            target = t
                            break

                    if not target:
                        m_hour = re.search(r"(\d{1,2})", q_clean)
                        if m_hour:
                            target_hour = int(m_hour.group(1))
                            for t in tasks:
                                if t.deadline:
                                    h = getattr(t.deadline, "hour", None)
                                    if h in (target_hour, (target_hour + 12) % 24):
                                        target = t
                                        break
                                elif f"{target_hour}" in t.title.lower() or (t.metadata and f"{target_hour}" in str(t.metadata.get("time_str", ""))):
                                    target = t
                                    break

                if target:
                    updates: Dict[str, Any] = {}
                    updated_title = target.title
                    if new_title:
                        updated_title = new_title
                        updates["title"] = updated_title

                    # Resolve deadline
                    deadline_to_sync = target.deadline
                    if new_time:
                        try:
                            s_dt, _ = self.calendar._parse_event_time(new_time)
                            deadline_to_sync = s_dt
                            updates["deadline"] = s_dt
                        except Exception as te:
                            logger.debug(f"[Tasks] Could not parse new time '{new_time}': {te}")
                    elif deadline_to_sync is None and query_str:
                        # Auto-heal: If deadline was missing, parse time from query (e.g. "9 o'clock")
                        m_hour = re.search(r"(\d{1,2})\s*(?:o'?clock|am|pm)?", query_str.lower())
                        if m_hour:
                            try:
                                s_dt, _ = self.calendar._parse_event_time(m_hour.group(0))
                                deadline_to_sync = s_dt
                                updates["deadline"] = s_dt
                            except Exception:
                                pass

                    if updates:
                        self.repo.update(target.id, updates)

                    # Update on Google Calendar
                    cal_id = target.metadata.get("calendar_event_id") if target.metadata else None
                    try:
                        cal_res = await self.calendar.sync_task_event(
                            task_id=target.id,
                            title=updated_title,
                            deadline=deadline_to_sync,
                            done=target.done,
                            priority=target.priority.value if hasattr(target.priority, "value") else str(target.priority),
                            is_reminder=(target.metadata.get("item_type") == "reminder" if target.metadata else False),
                            calendar_event_id=cal_id,
                        )
                        if cal_res.get("id") and not cal_id:
                            new_meta = dict(target.metadata or {})
                            new_meta["calendar_event_id"] = cal_res["id"]
                            self.repo.update(target.id, {"metadata": new_meta})
                    except Exception as ce:
                        logger.warning(f"[Tasks] Calendar sync failed on update: {ce}")

                    spoken_time = self._format_spoken_datetime(deadline_to_sync.isoformat()) if deadline_to_sync else ""
                    time_phrase = f" scheduled for {spoken_time}" if spoken_time else ""
                    speech = f"I have updated the entry to '{updated_title}'{time_phrase}, sir."
                    return SpecialistResult(
                        success=True,
                        action="update_task",
                        data={"task_id": target.id, "title": updated_title, "deadline": str(deadline_to_sync)},
                        speech_summary=speech,
                        card_payload={
                            "type": "task_updated",
                            "id": target.id,
                            "title": updated_title,
                            "time": spoken_time,
                        },
                    )

                # 3. Check Google Calendar events if not in local repo
                if not target and query_str:
                    cal_events = await self._fetch_calendar_events(max_results=20)
                    matched_event = None
                    q_clean = query_str.lower()
                    for ev in cal_events:
                        ev_summary = str(ev.get("summary", "")).lower()
                        if q_clean in ev_summary or ev_summary in q_clean:
                            matched_event = ev
                            break
                    if not matched_event:
                        m_hour = re.search(r"(\d{1,2})", q_clean)
                        if m_hour:
                            target_h = int(m_hour.group(1))
                            for ev in cal_events:
                                ev_start = str(ev.get("start", "")).lower()
                                if f"{target_h}:" in ev_start or f"{target_h} " in ev_start:
                                    matched_event = ev
                                    break

                    if matched_event:
                        ev_id = matched_event.get("id")
                        updated_title = new_title or matched_event.get("summary", "Event")
                        await self.calendar.update_event(
                            event_id=ev_id,
                            summary=updated_title,
                            start_time_str=new_time if new_time else None,
                        )
                        time_display = self._format_spoken_datetime(matched_event.get("start"))
                        speech = f"I have updated the calendar event to '{updated_title}' ({time_display}), sir."
                        return SpecialistResult(
                            success=True,
                            action="update_task",
                            data={"event_id": ev_id, "title": updated_title},
                            speech_summary=speech,
                            card_payload={"type": "calendar_event_updated", "id": ev_id, "title": updated_title},
                        )

                return SpecialistResult(
                    success=False,
                    action=action,
                    error=f"Could not find any existing task or event matching '{query_str}' to update.",
                )

            # ── 7d. Clear All Reminders ───────────────────────────────────────
            elif act in ["clear_reminders", "delete_all_reminders", "clear_all_reminders", "delete_reminders"]:
                tasks = self.repo.list(include_completed=True, limit=100)
                reminders = [
                    t for t in tasks
                    if (t.metadata and t.metadata.get("item_type") == "reminder") or "reminder" in t.title.lower()
                ]
                deleted_count = 0
                for r in reminders:
                    cal_id = r.metadata.get("calendar_event_id") if r.metadata else None
                    if cal_id:
                        await self.calendar.delete_event(cal_id)
                    self.repo.delete(r.id)
                    deleted_count += 1

                return SpecialistResult(
                    success=True,
                    action=action,
                    data={"deleted_count": deleted_count},
                    speech_summary=f"I have removed all {deleted_count} active reminders and their calendar entries, sir.",
                    card_payload={"type": "reminders_cleared", "count": deleted_count},
                )

            # ── 8. Consolidated Daily Agenda ──────────────────────────────────
            elif act in ["get_daily_agenda", "daily_agenda", "agenda", "schedule"]:
                target_date_str = str(params.get("date") or "").strip()
                if not target_date_str or target_date_str.lower() == "today":
                    # Check if query or context specifies a different date/range
                    q_ctx = str(params.get("query") or (context or {}).get("query") or "").lower()
                    if "next week" in q_ctx:
                        target_date_str = "next week"
                    elif "this week" in q_ctx:
                        target_date_str = "this week"
                    elif "tomorrow" in q_ctx:
                        target_date_str = "tomorrow"
                    elif "yesterday" in q_ctx:
                        target_date_str = "yesterday"
                    else:
                        for day_name in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                            if day_name in q_ctx:
                                target_date_str = f"next {day_name}" if "next" in q_ctx else day_name
                                break
                    target_date_str = target_date_str or "today"

                t_min, t_max = self._resolve_filter_range(date_val=target_date_str)
                local_tz = datetime.datetime.now().astimezone().tzinfo

                all_pending = self.repo.list(include_completed=False, limit=50)
                # Fetch events specifically within target date window
                events = await self._fetch_calendar_events(max_results=10, time_min=t_min, time_max=t_max)
                is_sandbox = any(e.get("source") == "sandbox" for e in events)

                reminders = [t for t in all_pending if (t.metadata and t.metadata.get("item_type") == "reminder")]
                pure_tasks = [t for t in all_pending if not (t.metadata and t.metadata.get("item_type") in ("reminder", "event"))]

                today_tasks = [
                    t for t in pure_tasks
                    if self._classify_task_timing(t, t_min, t_max, local_tz) in ("scheduled", "created_window")
                ][:5]
                overdue_tasks = [
                    t for t in pure_tasks
                    if self._classify_task_timing(t, t_min, t_max, local_tz) == "overdue"
                ]
                backlog_tasks = [
                    t for t in pure_tasks
                    if self._classify_task_timing(t, t_min, t_max, local_tz) == "backlog"
                ]
                today_reminders = [
                    r for r in reminders
                    if self._classify_task_timing(r, t_min, t_max, local_tz) in ("scheduled", "created_window")
                ][:5]

                task_list = [{"title": t.title, "priority": t.priority} for t in today_tasks]
                reminder_list = [{"title": r.title} for r in today_reminders]
                event_list = [
                    {
                        "summary": e.get("summary"),
                        "time": e.get("start"),
                        "spoken_time": self._format_spoken_datetime(e.get("start")),
                    }
                    for e in events
                ]

                speech_parts = []
                day_label = "today" if target_date_str.lower() in ["today", ""] else target_date_str
                prep = "for " if day_label in ["next week", "this week"] else ""
                if event_list:
                    agenda_speech = self._format_event_list_speech(event_list, context_label=day_label)
                    speech_parts.append(agenda_speech)
                else:
                    # Look ahead beyond this date window for the next upcoming event so Alfred can inform user
                    next_events = await self._fetch_calendar_events(max_results=1, time_min=t_max)
                    if next_events:
                        nxt = next_events[0]
                        nxt_spoken = self._format_spoken_datetime(nxt.get("start"))
                        speech_parts.append(f"You have no events scheduled {prep}{day_label}, sir. Your next event is '{nxt['summary']}' {nxt_spoken}.")
                    else:
                        speech_parts.append(f"You have no events scheduled {prep}{day_label}, sir.")

                if reminder_list:
                    speech_parts.append(f"You have {len(reminder_list)} active reminder{'s' if len(reminder_list) != 1 else ''} for {day_label}.")
                if task_list:
                    titles = ", ".join([f"'{t['title']}'" for t in task_list[:3]])
                    speech_parts.append(f"You have {len(task_list)} pending task{'s' if len(task_list) != 1 else ''} scheduled for {day_label}: {titles}.")
                    if overdue_tasks:
                        speech_parts.append(f"You also have {len(overdue_tasks)} overdue task{'s' if len(overdue_tasks) != 1 else ''}.")
                    elif backlog_tasks:
                        speech_parts.append(f"Additionally, you have {len(backlog_tasks)} older task{'s' if len(backlog_tasks) != 1 else ''} in your general backlog.")
                else:
                    if overdue_tasks:
                        speech_parts.append(f"You have no tasks scheduled for {day_label}, sir, though you have {len(overdue_tasks)} overdue task{'s' if len(overdue_tasks) != 1 else ''}.")
                    elif backlog_tasks:
                        speech_parts.append(f"You have no tasks scheduled for {day_label}, sir (with {len(backlog_tasks)} older task{'s' if len(backlog_tasks) != 1 else ''} in your general backlog).")
                    elif not speech_parts:
                        speech_parts.append(f"Your schedule and task list for {day_label} are currently all clear, sir.")

                speech = " ".join(speech_parts)
                agenda_data: dict[str, Any] = {
                    "tasks": task_list,
                    "reminders": reminder_list,
                    "calendar_events": event_list,
                    "overdue_count": len(overdue_tasks),
                    "backlog_count": len(backlog_tasks),
                }
                if is_sandbox:
                    agenda_data["source"] = "sandbox"

                return SpecialistResult(
                    success=True,
                    action=action,
                    data=agenda_data,
                    speech_summary=speech,
                    card_payload={
                        "type": "daily_agenda",
                        "tasks": task_list,
                        "reminders": reminder_list,
                        "events": event_list,
                        "overdue_count": len(overdue_tasks),
                        "backlog_count": len(backlog_tasks),
                    },
                )

            # ── 8. List or Search Mobile Notifications ────────────────────────
            elif act in [
                "search_mobile_notifications",
                "search_notifications",
                "list_mobile_notifications",
                "get_mobile_notifications",
                "check_notifications",
                "list_notifications",
                "mobile_notifications",
                "phone_notifications",
            ]:
                limit = int(params.get("limit") or 5)
                unread_only = bool(params.get("unread_only", False))
                app_filter = params.get("app") or params.get("app_filter")
                search_query = str(params.get("query") or params.get("text") or "").strip()
                sender_query = str(params.get("sender") or params.get("contact") or params.get("from") or "").strip()

                is_search = act in ("search_mobile_notifications", "search_notifications") or bool(search_query) or bool(sender_query)

                raw_notifications = []
                unread_count = 0

                service = self.notif_service
                if service is None:
                    from backend.sync.notification_service import notification_service
                    service = notification_service

                content_query = search_query
                # If query is asking whether user's name is in the notification, do not require the phrase 'my name' in the notification text
                if any(phrase in search_query.lower() for phrase in ("my name", "is my name", "check if there is my name", "is my name in")):
                    content_query = re.sub(r"\b(can\s+you\s+)?(check\s+if\s+there\s+is\s+my\s+name|is\s+my\s+name\s+in(\s+the\s+notification)?|my\s+name(\s+in)?)\b", "", search_query, flags=re.IGNORECASE).strip()

                if is_search:
                    local_notifs = service.search_notifications(
                        query=content_query if content_query else None,
                        sender_filter=sender_query,
                        app_filter=app_filter,
                        limit=limit,
                    )
                    raw_notifications = [n.to_dict() for n in local_notifs]
                    unread_count = service.get_unread_count()
                else:
                    local_notifs = service.get_recent_notifications(
                        limit=limit,
                        unread_only=unread_only,
                        app_filter=app_filter,
                    )
                    raw_notifications = [n.to_dict() for n in local_notifs]
                    unread_count = service.get_unread_count()

                # 3. Cross-reference unread emails for complete communication situational awareness (only when listing general notifications)
                email_brief = ""
                unread_email_count = 0
                if not is_search:
                    try:
                        from backend.agent.specialists.email_specialist import EmailSpecialist
                        email_spec = EmailSpecialist()
                        email_res = await email_spec.list_unread_emails(max_results=3)
                        if email_res.success and email_res.data:
                            unread_email_count = int(email_res.data.get("count", 0))
                            email_list = email_res.data.get("emails", [])
                            if unread_email_count > 0:
                                senders = ", ".join([str(it.get("sender", "")).split("<")[0].strip() for it in email_list[:2] if it.get("sender")])
                                email_brief = f" Additionally, you have {unread_email_count} unread emails in your inbox, notably from {senders}."
                    except Exception as em_err:
                        logger.debug(f"[Tasks] Email cross-reference notice: {em_err}")

                # 4. Synthesize British butler speech summary
                if is_search:
                    if not raw_notifications:
                        target = sender_query or search_query or "your query"
                        speech = (
                            f"Sir, I checked the notifications forwarded from your mobile companion for '{target}', "
                            "but found no matching alert. Please note that I only have access to notification banners received while your "
                            "phone was connected, and do not have access to your full WhatsApp chat history or database."
                        )
                        return SpecialistResult(
                            success=True,
                            action=action,
                            speech_summary=speech,
                            data={
                                "notifications": [],
                                "found": False,
                                "note": "Only pushed notifications from the mobile companion app are stored.",
                            },
                            card_payload={
                                "type": "NOTIFICATION_DIGEST",
                                "title": "Mobile Notification Search",
                                "count": 0,
                                "items": [],
                                "note": "No matching notification found in local store.",
                            },
                        )

                    # Determine if user is asking if their name appears
                    user_name = "Mihir Patil"
                    try:
                        from backend.agent.fast_path import _CACHED_USER_PROFILE
                        user_name = _CACHED_USER_PROFILE.get("name", "Mihir")
                    except Exception:
                        pass

                    first_name = user_name.split()[0].lower()
                    full_name_lower = user_name.lower()
                    check_name = any(w in search_query.lower() for w in ("my name", "name", "shortlist", "listed")) or any(w in str(params).lower() for w in ("my name", "name"))

                    if check_name:
                        name_found = any(
                            (first_name in n.get("text", "").lower() or full_name_lower in n.get("text", "").lower() or
                             first_name in n.get("title", "").lower() or full_name_lower in n.get("title", "").lower())
                            for n in raw_notifications
                        )
                        matched_title = raw_notifications[0].get("title") or raw_notifications[0].get("app_name", "the message")
                        clean_title = matched_title.split(":")[0].strip()
                        if name_found:
                            speech = f"Yes, sir. I examined the notification regarding {clean_title}, and your name ({user_name}) is present."
                        else:
                            speech = f"I examined the notification regarding {clean_title}, sir, but your name ({user_name}) does not appear in the message text."

                        return SpecialistResult(
                            success=True,
                            action=action,
                            speech_summary=speech,
                            data={
                                "notifications": raw_notifications,
                                "name_found": name_found,
                                "checked_name": user_name,
                                "matched_count": len(raw_notifications),
                            },
                            card_payload={
                                "type": "NOTIFICATION_DIGEST",
                                "title": f"Notification Search: {sender_query or search_query}",
                                "count": len(raw_notifications),
                                "items": raw_notifications,
                            },
                        )

                    top_n = raw_notifications[0]
                    speech = (
                        f"I found a notification from {top_n.get('app_name', 'Mobile')} regarding '{top_n.get('title', '')}', sir: "
                        f"\"{top_n.get('text', '')[:120]}\"."
                    )
                    return SpecialistResult(
                        success=True,
                        action=action,
                        speech_summary=speech,
                        data={
                            "notifications": raw_notifications,
                            "matched_count": len(raw_notifications),
                        },
                        card_payload={
                            "type": "NOTIFICATION_DIGEST",
                            "title": f"Notification Match: {sender_query or search_query}",
                            "count": len(raw_notifications),
                            "items": raw_notifications,
                        },
                    )

                if not raw_notifications:
                    if unread_email_count > 0:
                        speech = f"You have no pending mobile notifications at present, sir.{email_brief}"
                    else:
                        speech = "You have no pending mobile notifications or unread communications at present, sir."

                    return SpecialistResult(
                        success=True,
                        action=action,
                        speech_summary=speech,
                        data={"notifications": [], "unread_count": 0, "unread_emails": unread_email_count},
                        card_payload={
                            "type": "NOTIFICATION_DIGEST",
                            "title": "Mobile Notifications",
                            "count": 0,
                            "items": [],
                            "unread_emails": unread_email_count,
                        },
                    )

                urgent_or_high = [n for n in raw_notifications if n.get("priority") in ("URGENT", "HIGH")]
                if urgent_or_high:
                    top_n = urgent_or_high[0]
                    speech = (
                        f"You have {len(raw_notifications)} mobile notifications awaiting your attention, sir. "
                        f"Notably, a high-priority alert from {top_n.get('app_name', 'Mobile')}: "
                        f"'{top_n.get('title', '')}' - {top_n.get('text', '')[:90]}.{email_brief}"
                    )
                else:
                    top_n = raw_notifications[0]
                    speech = (
                        f"You have {len(raw_notifications)} mobile notifications, sir. "
                        f"Most recently from {top_n.get('app_name', 'Mobile')}: '{top_n.get('title', '')}'.{email_brief}"
                    )

                return SpecialistResult(
                    success=True,
                    action=action,
                    speech_summary=speech,
                    data={
                        "notifications": raw_notifications,
                        "unread_count": unread_count,
                        "unread_emails": unread_email_count,
                    },
                    card_payload={
                        "type": "NOTIFICATION_DIGEST",
                        "title": "Mobile Alerts",
                        "count": len(raw_notifications),
                        "items": raw_notifications,
                        "unread_emails": unread_email_count,
                    },
                )

            return SpecialistResult(success=False, action=action, error=f"Unsupported action '{action}' on tasks.")

        except Exception as e:
            logger.exception(f"[Tasks] Error executing action '{action}': {e}")
            return SpecialistResult(success=False, action=action, error=str(e))
