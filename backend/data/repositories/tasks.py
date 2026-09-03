"""Task Repository for Supabase.

Provides CRUD operations and status filtering for tasks.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from supabase import Client

from backend.data.client import get_supabase_client
from backend.data.models import TaskCreate, TaskModel

logger = logging.getLogger("vesper.data.tasks")


class TaskRepository:
    """Repository handling all task database queries via Supabase."""

    def __init__(self, client: Optional[Client] = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        if self._client is not None:
            return self._client
        return get_supabase_client()

    def create(self, task: TaskCreate) -> TaskModel:
        """Creates a new task in Supabase."""
        data = {
            "user_id": task.user_id,
            "title": task.title,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "priority": task.priority.value,
            "metadata": task.metadata,
        }
        res = self.client.table("tasks").insert(data).execute()
        if not res.data:
            raise RuntimeError("Failed to insert task into Supabase.")
        return TaskModel.model_validate(res.data[0])

    def get(self, task_id: str) -> Optional[TaskModel]:
        """Fetches a single task by ID."""
        res = self.client.table("tasks").select("*").eq("id", task_id).execute()
        if res.data:
            return TaskModel.model_validate(res.data[0])
        return None

    def list(
        self,
        user_id: str = "default_user",
        include_completed: bool = False,
        limit: int = 50,
    ) -> list[TaskModel]:
        """Lists tasks for a user, optionally filtering out completed ones."""
        query = self.client.table("tasks").select("*").eq("user_id", user_id)
        if not include_completed:
            query = query.eq("done", False)
        res = query.order("created_at", desc=True).limit(limit).execute()
        return [TaskModel.model_validate(row) for row in res.data]

    def mark_done(self, task_id: str, done: bool = True) -> bool:
        """Marks a task as completed or uncompleted."""
        res = self.client.table("tasks").update({"done": done}).eq("id", task_id).execute()
        return len(res.data) > 0

    def update(self, task_id: str, updates: dict[str, Any]) -> Optional[TaskModel]:
        """Updates arbitrary fields on a task."""
        res = self.client.table("tasks").update(updates).eq("id", task_id).execute()
        if res.data:
            return TaskModel.model_validate(res.data[0])
        return None

    def delete(self, task_id: str) -> bool:
        """Deletes a task by ID."""
        res = self.client.table("tasks").delete().eq("id", task_id).execute()
        return len(res.data) > 0
