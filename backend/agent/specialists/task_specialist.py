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
    ) -> None:
        self.repo = repo or TaskRepository()
        self.triage_worker = triage_worker or AsyncTaskTriageWorker()
        self.calendar = calendar_tool or GoogleCalendarTool()

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

                # 2. Persist in Supabase task repo as reminder
                task_obj = self.repo.create(
                    TaskCreate(
                        title=f"Reminder: {reminder_text} ({cal_event.get('start', time_str)})",
                        priority=priority,
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

                if action_type == "reminder" or (action_type == "event" and extracted_time):
                    norm_title = normalize_title(title)
                    time_found = str(params.get("time") or extracted_time or "today").strip()
                    if action_type == "event":
                        return await self.execute("schedule_event", {"summary": norm_title, "time": time_found})
                    return await self.execute("set_reminder", {"reminder": norm_title, "time": time_found, "priority": params.get("priority")})

                # Clean conversational noise and trailing dates
                title = normalize_title(title)

                p_str = params.get("priority", "normal").lower()
                priority = PriorityLevel.NORMAL
                if "urgent" in p_str or "high" in p_str:
                    priority = PriorityLevel.HIGH
                elif "low" in p_str:
                    priority = PriorityLevel.LOW

                # Instant creation in Supabase (<30ms)
                task_obj = self.repo.create(
                    TaskCreate(
                        title=title,
                        priority=priority,
                        metadata={"item_type": "task"},
                    )
                )

                # Fire Async AI Triage in background
                asyncio.create_task(
                    self.triage_worker.triage_task_in_background(task_obj.id, task_obj.title)
                )

                return SpecialistResult(
                    success=True,
                    action=action,
                    data={"task_id": task_obj.id, "title": task_obj.title, "priority": task_obj.priority},
                    speech_summary=f"Added '{task_obj.title}' to your task list, sir.",
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

                time_display = self._format_spoken_datetime(cal_event.get("start")) or start_time
                speech = f"Scheduled '{summary}' {time_display} on your Google Calendar, sir."
                return SpecialistResult(
                    success=True,
                    action="schedule_event",
                    data=cal_event,
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
                    task_items = [{"id": t.id, "title": t.title, "priority": t.priority, "done": t.done} for t in filtered]
                    if not task_items:
                        speech = "You have no tasks scheduled for today, sir."
                    else:
                        titles = ", ".join([f"'{t['title']}'" for t in task_items[:3]])
                        speech = f"You have {len(task_items)} task{'s' if len(task_items) != 1 else ''} scheduled for today: {titles}."
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
                success = self.repo.mark_done(task_id, done=True)
                if success:
                    return SpecialistResult(
                        success=True,
                        action=action,
                        data={"task_id": task_id, "done": True},
                        speech_summary="Marked the item as completed, sir.",
                        card_payload={"type": "task_completed", "id": task_id},
                    )
                return SpecialistResult(success=False, action=action, error=f"Task '{task_id}' not found.")

            # ── 7b. Delete Task / Reminder ────────────────────────────────────
            elif act in ["delete_task", "remove_task", "delete_reminder", "remove_reminder", "delete"]:
                task_id = str(params.get("task_id") or params.get("id") or "").strip()
                title_query = str(params.get("title") or params.get("query") or params.get("reminder") or "").lower().strip()

                tasks = self.repo.list(include_completed=True, limit=50)
                target = None
                if task_id:
                    target = next((t for t in tasks if t.id == task_id), None)
                elif title_query:
                    target = next((t for t in tasks if title_query in t.title.lower()), None)

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
                return SpecialistResult(success=False, action=action, error="No matching task found to delete.")

            # ── 7c. Clear All Reminders ───────────────────────────────────────
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
                pure_tasks = [t for t in all_pending if not (t.metadata and t.metadata.get("item_type") == "reminder")]

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

            # ── 8. List Mobile Notifications ──────────────────────────────────
            elif act in [
                "list_mobile_notifications",
                "get_mobile_notifications",
                "check_notifications",
                "list_notifications",
                "mobile_notifications",
                "phone_notifications",
            ]:
                from backend.sync.notification_service import notification_service

                limit = int(params.get("limit") or 5)
                unread_only = bool(params.get("unread_only", False))
                app_filter = params.get("app") or params.get("app_filter")

                notifs = notification_service.get_recent_notifications(
                    limit=limit,
                    unread_only=unread_only,
                    app_filter=app_filter,
                )

                if not notifs:
                    speech = "You have no pending mobile notifications at present, sir."
                    return SpecialistResult(
                        success=True,
                        action=action,
                        speech_summary=speech,
                        data={"notifications": [], "unread_count": 0},
                        card_payload={
                            "type": "NOTIFICATION_DIGEST",
                            "title": "Mobile Notifications",
                            "count": 0,
                            "items": [],
                        },
                    )

                urgent_or_high = [n for n in notifs if n.priority in ("URGENT", "HIGH")]
                if urgent_or_high:
                    top_n = urgent_or_high[0]
                    speech = f"You have {len(notifs)} recent alerts, sir. Notably, a high-priority notification from {top_n.app_name}: '{top_n.title}' - {top_n.text}."
                else:
                    top_n = notifs[0]
                    speech = f"You have {len(notifs)} mobile notifications, sir. Most recently from {top_n.app_name}: '{top_n.title}'."

                return SpecialistResult(
                    success=True,
                    action=action,
                    speech_summary=speech,
                    data={
                        "notifications": [n.to_dict() for n in notifs],
                        "unread_count": notification_service.get_unread_count(),
                    },
                    card_payload={
                        "type": "NOTIFICATION_DIGEST",
                        "title": "Mobile Alerts",
                        "count": len(notifs),
                        "items": [n.to_dict() for n in notifs],
                    },
                )

            return SpecialistResult(success=False, action=action, error=f"Unsupported action '{action}' on tasks.")

        except Exception as e:
            logger.exception(f"[Tasks] Error executing action '{action}': {e}")
            return SpecialistResult(success=False, action=action, error=str(e))
