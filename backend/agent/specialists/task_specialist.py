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
from backend.data.models import PriorityLevel, TaskCreate, TaskModel
from backend.data.repositories.tasks import TaskRepository

logger = logging.getLogger("vesper.agent.specialists.tasks")


class TaskSpecialist(BaseSpecialist):
    """Specialist sub-agent managing tasks, time-anchored reminders, and Google Calendar events."""

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
                "description": "Lists upcoming scheduled appointments and events from Google Calendar.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {"type": "integer", "description": "Maximum events to fetch (default: 5)."},
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
                "description": "Retrieves the consolidated daily briefing: today's calendar events, active reminders, and pending tasks.",
                "parameters": {"type": "object", "properties": {}},
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

                time_display = cal_event.get("start") or time_str
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

                # If the title clearly requests a reminder with a time anchor, delegate to set_reminder!
                import re
                time_match = re.search(r"(?:at|by|for)\s+(\d{1,2}[:.]?\d{0,2}\s*(?:am|pm)?\s*(?:today|tomorrow)?)", title, re.IGNORECASE)
                if ("remind" in title.lower() or "reminder" in title.lower()) and time_match:
                    reminder_clean = re.sub(r"(?:remind me to|add a reminder (?:at|to|that)?|reminder:?)", "", title, flags=re.IGNORECASE).strip()
                    time_found = time_match.group(1).strip()
                    return await self.execute("set_reminder", {"reminder": reminder_clean, "time": time_found, "priority": params.get("priority")})

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

                time_display = cal_event.get("start", start_time)
                speech = f"Scheduled '{summary}' for {time_display} on your Google Calendar, sir."
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
                limit = params.get("limit", 5)

                tasks = self.repo.list(include_completed=include_done, limit=limit)
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
            elif act in ["list_calendar_events", "get_calendar_events", "list_events", "calendar"]:
                max_res = int(params.get("max_results", 5))
                events = await self.calendar.list_upcoming_events(max_results=max_res)
                is_sandbox = any(e.get("source") == "sandbox" for e in events)
                if not events:
                    speech = "Your calendar has no upcoming events scheduled, sir."
                else:
                    ev_strings = [f"'{e['summary']}' at {e['start']}" for e in events[:2]]
                    speech = f"Upcoming on your calendar: {', '.join(ev_strings)}."

                res_data: dict[str, Any] = {"events": events, "count": len(events)}
                if is_sandbox:
                    res_data["source"] = "sandbox"

                return SpecialistResult(
                    success=True,
                    action="list_calendar_events",
                    data=res_data,
                    speech_summary=speech,
                    card_payload={"type": "calendar_events_list", "events": events},
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
                pending_tasks = self.repo.list(include_completed=False, limit=5)
                events = await self.calendar.list_upcoming_events(max_results=3)
                is_sandbox = any(e.get("source") == "sandbox" for e in events)

                reminders = [t for t in pending_tasks if (t.metadata and t.metadata.get("item_type") == "reminder")]
                pure_tasks = [t for t in pending_tasks if not (t.metadata and t.metadata.get("item_type") == "reminder")]

                task_list = [{"title": t.title, "priority": t.priority} for t in pure_tasks]
                reminder_list = [{"title": r.title} for r in reminders]
                event_list = [{"summary": e.get("summary"), "time": e.get("start")} for e in events]

                speech_parts = []
                if event_list:
                    ev = event_list[0]
                    speech_parts.append(f"Your next scheduled event is '{ev['summary']}' at {ev['time']}.")
                if reminder_list:
                    speech_parts.append(f"You have {len(reminder_list)} active reminder{'s' if len(reminder_list) != 1 else ''}.")
                if task_list:
                    speech_parts.append(f"You have {len(task_list)} pending task{'s' if len(task_list) != 1 else ''} on your agenda.")
                elif not speech_parts:
                    speech_parts.append("Your schedule and task list are currently all clear, sir.")

                speech = " ".join(speech_parts)
                agenda_data: dict[str, Any] = {"tasks": task_list, "reminders": reminder_list, "calendar_events": event_list}
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
                    },
                )

            return SpecialistResult(success=False, action=action, error=f"Unsupported action '{action}' on tasks.")

        except Exception as e:
            logger.exception(f"[Tasks] Error executing action '{action}': {e}")
            return SpecialistResult(success=False, action=action, error=str(e))
