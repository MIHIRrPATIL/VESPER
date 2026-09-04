"""VESPER Active Task Registry for Instant Cancellation & Barge-In.

Tracks in-flight asyncio.Task instances by correlation_id (UUID) and session_id,
allowing out-of-band INTERRUPT signals to abort tasks in <30ms.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("vesper.gateway.tasks")


class TaskRegistry:
    """Manages active asynchronous tasks and executes instant cancellations."""

    def __init__(self) -> None:
        # Maps correlation_id (request UUID) -> asyncio.Task
        self._tasks: dict[str, asyncio.Task] = {}
        # Maps correlation_id -> session_id for session-level cleanup
        self._task_sessions: dict[str, str] = {}

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    def register(
        self,
        correlation_id: str,
        task: asyncio.Task,
        session_id: Optional[str] = None,
    ) -> None:
        """Registers an in-flight asyncio task for tracking and cancellation."""
        self._tasks[correlation_id] = task
        if session_id:
            self._task_sessions[correlation_id] = session_id

        # Auto-remove upon completion
        def _cleanup_callback(_: asyncio.Task) -> None:
            self._tasks.pop(correlation_id, None)
            self._task_sessions.pop(correlation_id, None)

        task.add_done_callback(_cleanup_callback)
        logger.debug(f"[TASKS] Registered task for correlation_id='{correlation_id}'")

    def cancel(self, correlation_id: str) -> bool:
        """Cancels a specific in-flight task immediately. Returns True if cancelled."""
        task = self._tasks.get(correlation_id)
        if task and not task.done():
            task.cancel()
            logger.info(f"[TASKS] Successfully issued cancellation for task '{correlation_id}'")
            return True
        return False

    def cancel_session(self, session_id: str) -> int:
        """Cancels all active tasks initiated by a given client session."""
        cancelled_count = 0
        for cid, sid in list(self._task_sessions.items()):
            if sid == session_id:
                if self.cancel(cid):
                    cancelled_count += 1
        logger.info(f"[TASKS] Cancelled {cancelled_count} task(s) for session '{session_id}'")
        return cancelled_count

    def has_active_session_tasks(self, session_id: str) -> bool:
        """Returns True if any uncompleted tasks exist for this session."""
        for cid, sid in self._task_sessions.items():
            if sid == session_id:
                task = self._tasks.get(cid)
                if task and not task.done():
                    return True
        return False

    def cancel_all(self) -> int:
        """Cancels all currently active tasks across all sessions."""
        cancelled_count = 0
        for cid, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                cancelled_count += 1
        self._tasks.clear()
        self._task_sessions.clear()
        return cancelled_count
