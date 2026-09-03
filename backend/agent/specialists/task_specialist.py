"""VESPER Task Specialist Agent.

Wraps TaskRepository (Supabase) to provide task management tools to Alfred:
  - `add_task`: Fast task creation + async background AI priority triage.
  - `list_tasks`: Status-filtered task lists.
  - `complete_task`: Mark tasks as done.
  - `delete_task`: Remove tasks.
  - `get_daily_agenda`: Combines tasks and Google Calendar schedule for Alfred's daily briefing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.agent.specialists.task_triage import AsyncTaskTriageWorker
from backend.agent.tools.calendar_tool import GoogleCalendarTool
from backend.data.models import PriorityLevel, TaskCreate, TaskModel
from backend.data.repositories.tasks import TaskRepository

logger = logging.getLogger("vesper.agent.specialists.tasks")


class TaskSpecialist(BaseSpecialist):
    """Specialist sub-agent managing tasks, todos, deadlines, and daily agenda."""

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
        return "Manages todo items, task deadlines, status updates, priorities, and daily calendar schedule."

    def get_capabilities(self) -> str:
        return "Create, list, complete, and prioritize tasks, and get your daily agenda with Google Calendar."

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "add_task",
                "description": "Creates a new task with title and optional priority. Triages priority in background.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "The title or description of the task."},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Optional explicit priority level.",
                        },
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "list_tasks",
                "description": "Lists current pending tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_completed": {
                            "type": "boolean",
                            "description": "Whether to include completed tasks (default: False).",
                        },
                        "limit": {"type": "integer", "description": "Maximum tasks to return (default 5)."},
                    },
                },
            },
            {
                "name": "complete_task",
                "description": "Marks an existing task as completed by task ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "The ID of the task to complete."},
                    },
                    "required": ["task_id"],
                },
            },
            {
                "name": "get_daily_agenda",
                "description": "Retrieves your full daily briefing: pending tasks plus scheduled Google Calendar events.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        try:
            act = action.lower().strip()
            if act in ["add_task", "create_task", "create", "new_task", "add"]:
                title = str(params.get("title") or params.get("task") or "").strip()
                if not title:
                    return SpecialistResult(success=False, action=action, error="Task title is required.")

                p_str = params.get("priority", "normal").lower()
                priority = PriorityLevel.NORMAL
                if "urgent" in p_str or "high" in p_str:
                    priority = PriorityLevel.HIGH
                elif "low" in p_str:
                    priority = PriorityLevel.LOW

                # 1. Instant creation in Supabase (<30ms)
                task_obj = self.repo.create(TaskCreate(title=title, priority=priority))

                # 2. Fire Async AI Triage in background without blocking voice response!
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

            elif act in ["complete_task", "mark_done", "complete", "finish_task"]:
                task_id = str(params.get("task_id") or params.get("id") or "").strip()
                success = self.repo.mark_done(task_id, done=True)
                if success:
                    return SpecialistResult(
                        success=True,
                        action=action,
                        data={"task_id": task_id, "done": True},
                        speech_summary="Marked the task as completed, sir.",
                        card_payload={"type": "task_completed", "id": task_id},
                    )
                return SpecialistResult(success=False, action=action, error=f"Task '{task_id}' not found.")

            elif act in ["get_daily_agenda", "daily_agenda", "agenda", "schedule"]:
                pending_tasks = self.repo.list(include_completed=False, limit=5)
                events = await self.calendar.list_upcoming_events(max_results=3)

                task_list = [{"title": t.title, "priority": t.priority} for t in pending_tasks]
                event_list = [{"summary": e.get("summary"), "time": e.get("start")} for e in events]

                speech_parts = []
                if event_list:
                    ev = event_list[0]
                    speech_parts.append(f"Your next meeting is '{ev['summary']}' at {ev['time']}.")
                if task_list:
                    speech_parts.append(f"You have {len(task_list)} pending tasks on your agenda.")
                else:
                    speech_parts.append("Your task agenda is currently clear.")

                speech = " ".join(speech_parts) if speech_parts else "All clear for today, sir."

                return SpecialistResult(
                    success=True,
                    action=action,
                    data={"tasks": task_list, "calendar_events": event_list},
                    speech_summary=speech,
                    card_payload={
                        "type": "daily_agenda",
                        "tasks": task_list,
                        "events": event_list,
                    },
                )

            return SpecialistResult(success=False, action=action, error=f"Unsupported action '{action}' on tasks.")

        except Exception as e:
            logger.exception(f"[Tasks] Error executing action '{action}': {e}")
            return SpecialistResult(success=False, action=action, error=str(e))
