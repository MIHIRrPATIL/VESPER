"""VESPER Gateway Task & Agenda REST Endpoints.

Provides full CRUD, temporal classification (today, overdue, upcoming, completed),
and cross-device synchronization for tasks and time-anchored reminders.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.agent.tools.calendar_tool import GoogleCalendarTool
from backend.data.models import PriorityLevel, TaskCreate, TaskModel
from backend.data.repositories.tasks import TaskRepository
from backend.sync.sync_manager import sync_manager

logger = logging.getLogger("vesper.gateway.routes.tasks")
router = APIRouter(prefix="/api/tasks", tags=["Tasks"])
_cal_tool = GoogleCalendarTool()

# Resilient in-memory fallback cache if Supabase is offline or unconfigured
_FALLBACK_TASKS: List[Dict[str, Any]] = [
    {
        "id": "task_demo_1",
        "user_id": "default_user",
        "title": "Review PR #42 & verification test suite",
        "deadline": datetime.datetime.now().replace(hour=14, minute=30, second=0).isoformat(),
        "done": False,
        "priority": "high",
        "metadata": {"item_type": "task", "tag": "DEV"},
        "created_at": (datetime.datetime.now() - datetime.timedelta(hours=3)).isoformat(),
        "category": "today",
        "age_label": "Today • 14:30",
    },
    {
        "id": "task_demo_2",
        "user_id": "default_user",
        "title": "Synchronize Android node notification relay",
        "deadline": datetime.datetime.now().replace(hour=16, minute=0, second=0).isoformat(),
        "done": False,
        "priority": "normal",
        "metadata": {"item_type": "task", "tag": "SYNC"},
        "created_at": (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat(),
        "category": "today",
        "age_label": "Today • 16:00",
    },
    {
        "id": "task_demo_3",
        "user_id": "default_user",
        "title": "Quarterly infrastructure security audit and API key rotation",
        "deadline": (datetime.datetime.now() - datetime.timedelta(days=2)).replace(hour=18, minute=0).isoformat(),
        "done": False,
        "priority": "urgent",
        "metadata": {"item_type": "task", "tag": "SECURITY"},
        "created_at": (datetime.datetime.now() - datetime.timedelta(days=3)).isoformat(),
        "category": "overdue",
        "age_label": "2 days overdue",
    },
    {
        "id": "task_demo_4",
        "user_id": "default_user",
        "title": "Re-index graphify knowledge graph for mobile subproject",
        "deadline": (datetime.datetime.now() - datetime.timedelta(days=1)).replace(hour=11, minute=0).isoformat(),
        "done": False,
        "priority": "normal",
        "metadata": {"item_type": "task", "tag": "DOCS"},
        "created_at": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(),
        "category": "overdue",
        "age_label": "1 day overdue",
    },
    {
        "id": "task_demo_5",
        "user_id": "default_user",
        "title": "Deploy Caelestia QML lock-screen power sentry daemon",
        "deadline": (datetime.datetime.now() + datetime.timedelta(days=1)).replace(hour=10, minute=0).isoformat(),
        "done": False,
        "priority": "normal",
        "metadata": {"item_type": "task", "tag": "LINUX"},
        "created_at": datetime.datetime.now().isoformat(),
        "category": "upcoming",
        "age_label": "Tomorrow • 10:00",
    },
    {
        "id": "task_demo_6",
        "user_id": "default_user",
        "title": "Calibrate BlazeFace camera presence sentry",
        "deadline": datetime.datetime.now().replace(hour=18, minute=15, second=0).isoformat(),
        "done": True,
        "priority": "normal",
        "metadata": {"item_type": "task", "tag": "VISION"},
        "created_at": (datetime.datetime.now() - datetime.timedelta(hours=5)).isoformat(),
        "category": "completed",
        "age_label": "Completed today",
    },
]


class TaskCreateRequest(BaseModel):
    title: str
    deadline: Optional[datetime.datetime] = None
    priority: str = "normal"
    tag: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskToggleRequest(BaseModel):
    done: Optional[bool] = None


def _classify_task(
    task: Any,
    now: datetime.datetime,
    t_min: datetime.datetime,
    t_max: datetime.datetime,
) -> tuple[str, str]:
    """Classifies task as today, overdue, upcoming, or completed with an age label."""
    is_done = getattr(task, "done", False) if not isinstance(task, dict) else task.get("done", False)
    if is_done:
        return "completed", "Completed"

    raw_deadline = getattr(task, "deadline", None) if not isinstance(task, dict) else task.get("deadline")
    raw_created = getattr(task, "created_at", None) if not isinstance(task, dict) else task.get("created_at")

    local_tz = now.astimezone().tzinfo

    def parse_dt(v: Any) -> Optional[datetime.datetime]:
        if not v:
            return None
        if isinstance(v, str):
            try:
                dt = datetime.datetime.fromisoformat(v)
            except Exception:
                return None
        elif isinstance(v, datetime.datetime):
            dt = v
        elif isinstance(v, datetime.date):
            dt = datetime.datetime.combine(v, datetime.time.min)
        else:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=local_tz)
        return dt.astimezone(local_tz)

    deadline = parse_dt(raw_deadline)
    created = parse_dt(raw_created)

    if deadline is not None:
        if t_min <= deadline <= t_max:
            time_part = deadline.strftime("%H:%M")
            return "today", f"Today • {time_part}"
        elif deadline < t_min:
            days_overdue = max(1, (t_min.date() - deadline.date()).days)
            return "overdue", f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue"
        else:
            if deadline.date() == (t_min.date() + datetime.timedelta(days=1)):
                return "upcoming", f"Tomorrow • {deadline.strftime('%H:%M')}"
            return "upcoming", f"Due {deadline.strftime('%b %d')}"
    else:
        # No deadline
        if created is not None and created < t_min:
            days_ago = max(1, (t_min.date() - created.date()).days)
            return "overdue", f"{days_ago} day{'s' if days_ago != 1 else ''} overdue"
        elif created is not None and t_min <= created <= t_max:
            return "today", "Today"
        return "today", "Pending"


def _format_task_dict(task: Any, category: str, age_label: str) -> Dict[str, Any]:
    if isinstance(task, dict):
        d = dict(task)
        d["category"] = category
        d["age_label"] = age_label
        meta = d.get("metadata") or {}
        if "tag" not in d:
            d["tag"] = meta.get("tag", "TASK")
        return d

    data = task.model_dump() if hasattr(task, "model_dump") else getattr(task, "__dict__", {})
    data["category"] = category
    data["age_label"] = age_label
    meta = data.get("metadata") or {}
    data["tag"] = meta.get("tag", "TASK")
    return data


@router.get("")
@router.get("/")
async def list_tasks(
    include_completed: bool = Query(True),
    category_filter: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Lists tasks classified into today, overdue, upcoming, and completed categories."""
    now = datetime.datetime.now().astimezone()
    local_tz = now.tzinfo
    t_min = datetime.datetime.combine(now.date(), datetime.time.min).replace(tzinfo=local_tz)
    t_max = datetime.datetime.combine(now.date(), datetime.time.max).replace(tzinfo=local_tz)

    tasks_raw: List[Any] = []
    try:
        repo = TaskRepository()
        tasks_raw = await asyncio.to_thread(repo.list, user_id="default_user", include_completed=True, limit=100)
    except Exception as e:
        logger.warning(f"[TASKS] Supabase task query failed, using resilient fallback: {e}")

    if not tasks_raw:
        tasks_raw = _FALLBACK_TASKS

    categorized_all: List[Dict[str, Any]] = []
    today_list: List[Dict[str, Any]] = []
    overdue_list: List[Dict[str, Any]] = []
    upcoming_list: List[Dict[str, Any]] = []
    completed_list: List[Dict[str, Any]] = []

    for t in tasks_raw:
        cat, age = _classify_task(t, now, t_min, t_max)
        t_dict = _format_task_dict(t, cat, age)
        categorized_all.append(t_dict)

        if cat == "completed":
            completed_list.append(t_dict)
        elif cat == "today":
            today_list.append(t_dict)
        elif cat == "overdue":
            overdue_list.append(t_dict)
        elif cat == "upcoming":
            upcoming_list.append(t_dict)

    # Calculate statistics
    pending_count = len(today_list) + len(overdue_list) + len(upcoming_list)
    stats = {
        "total": len(categorized_all),
        "today_count": len(today_list),
        "overdue_count": len(overdue_list),
        "upcoming_count": len(upcoming_list),
        "completed_count": len(completed_list),
        "pending_count": pending_count,
    }

    # Update cluster sync state
    try:
        await sync_manager.update_state({"active_tasks_count": pending_count}, source_device_id="gateway_tasks")
    except Exception:
        pass

    # Optional filtering
    items_to_return = categorized_all
    if category_filter == "today":
        items_to_return = today_list
    elif category_filter == "overdue":
        items_to_return = overdue_list
    elif category_filter == "upcoming":
        items_to_return = upcoming_list
    elif category_filter == "completed":
        items_to_return = completed_list

    if not include_completed:
        items_to_return = [it for it in items_to_return if not it.get("done", False)]

    return {
        "status": "ok",
        "stats": stats,
        "today": today_list,
        "overdue": overdue_list,
        "upcoming": upcoming_list,
        "completed": completed_list,
        "tasks": items_to_return,
    }


@router.post("")
@router.post("/")
async def create_task(req: TaskCreateRequest) -> Dict[str, Any]:
    """Creates a new user task in Supabase with metadata and priority."""
    meta = dict(req.metadata)
    if req.tag:
        meta["tag"] = req.tag.upper()

    try:
        prio_enum = PriorityLevel(req.priority.lower())
    except ValueError:
        prio_enum = PriorityLevel.NORMAL

    task_create = TaskCreate(
        title=req.title,
        deadline=req.deadline,
        priority=prio_enum,
        metadata=meta,
    )

    created_dict: Dict[str, Any] = {}
    try:
        repo = TaskRepository()
        model = await asyncio.to_thread(repo.create, task_create)
        created_dict = model.model_dump()

        # Auto-sync to Google Calendar
        try:
            cal_res = await _cal_tool.sync_task_event(
                task_id=model.id,
                title=model.title,
                deadline=model.deadline,
                done=model.done,
                priority=model.priority.value if hasattr(model.priority, "value") else str(model.priority),
                is_reminder=(meta.get("item_type") == "reminder"),
            )
            cal_id = cal_res.get("id")
            if cal_id:
                meta["calendar_event_id"] = cal_id
                meta["synced_to_calendar"] = True
                await asyncio.to_thread(repo.update, model.id, {"metadata": meta})
                created_dict["metadata"] = meta
        except Exception as ce:
            logger.warning(f"[TASKS] Google Calendar auto-sync failed for task '{model.id}': {ce}")

    except Exception as e:
        logger.warning(f"[TASKS] Supabase insert failed; writing to local fallback cache: {e}")
        new_id = f"task_{int(time.time()*1000)}"
        created_dict = {
            "id": new_id,
            "user_id": "default_user",
            "title": req.title,
            "deadline": req.deadline.isoformat() if req.deadline else None,
            "done": False,
            "priority": req.priority.lower(),
            "metadata": meta,
            "created_at": datetime.datetime.now().isoformat(),
        }
        try:
            cal_res = await _cal_tool.sync_task_event(
                task_id=new_id,
                title=req.title,
                deadline=req.deadline,
                done=False,
                priority=req.priority.lower(),
                is_reminder=(meta.get("item_type") == "reminder"),
            )
            if cal_res.get("id"):
                meta["calendar_event_id"] = cal_res["id"]
                meta["synced_to_calendar"] = True
                created_dict["metadata"] = meta
        except Exception as ce:
            logger.warning(f"[TASKS] Google Calendar fallback auto-sync failed: {ce}")
        _FALLBACK_TASKS.insert(0, created_dict)

    now = datetime.datetime.now().astimezone()
    local_tz = now.tzinfo
    t_min = datetime.datetime.combine(now.date(), datetime.time.min).replace(tzinfo=local_tz)
    t_max = datetime.datetime.combine(now.date(), datetime.time.max).replace(tzinfo=local_tz)
    cat, age = _classify_task(created_dict, now, t_min, t_max)
    formatted = _format_task_dict(created_dict, cat, age)

    return {"status": "created", "task": formatted}


@router.patch("/{task_id}/toggle")
async def toggle_task_done(task_id: str, req: Optional[TaskToggleRequest] = None) -> Dict[str, Any]:
    """Toggles or updates the completion status of a task."""
    target_done: Optional[bool] = req.done if req else None

    # Check fallback cache first
    for item in _FALLBACK_TASKS:
        if item["id"] == task_id:
            new_done = not item["done"] if target_done is None else target_done
            item["done"] = new_done
            item["updated_at"] = datetime.datetime.now().isoformat()

            # Sync update to Google Calendar
            try:
                cal_id = item.get("metadata", {}).get("calendar_event_id")
                cal_res = await _cal_tool.sync_task_event(
                    task_id=item["id"],
                    title=item["title"],
                    deadline=item.get("deadline"),
                    done=new_done,
                    priority=item.get("priority", "normal"),
                    is_reminder=(item.get("metadata", {}).get("item_type") == "reminder"),
                    calendar_event_id=cal_id,
                )
                if cal_res.get("id"):
                    item.setdefault("metadata", {})["calendar_event_id"] = cal_res["id"]
                    item["metadata"]["synced_to_calendar"] = True
            except Exception as ce:
                logger.warning(f"[TASKS] Google Calendar sync toggle failed for fallback task '{task_id}': {ce}")

            now = datetime.datetime.now().astimezone()
            local_tz = now.tzinfo
            t_min = datetime.datetime.combine(now.date(), datetime.time.min).replace(tzinfo=local_tz)
            t_max = datetime.datetime.combine(now.date(), datetime.time.max).replace(tzinfo=local_tz)
            cat, age = _classify_task(item, now, t_min, t_max)
            return {"status": "ok", "task": _format_task_dict(item, cat, age)}

    # Attempt Supabase query
    try:
        repo = TaskRepository()
        existing = await asyncio.to_thread(repo.get, task_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        new_done = not existing.done if target_done is None else target_done
        success = await asyncio.to_thread(repo.mark_done, task_id, new_done)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update task completion state")

        updated = await asyncio.to_thread(repo.get, task_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Updated task not found")

        # Sync update to Google Calendar
        try:
            cal_id = updated.metadata.get("calendar_event_id") if updated.metadata else None
            cal_res = await _cal_tool.sync_task_event(
                task_id=updated.id,
                title=updated.title,
                deadline=updated.deadline,
                done=new_done,
                priority=updated.priority.value if hasattr(updated.priority, "value") else str(updated.priority),
                is_reminder=(updated.metadata.get("item_type") == "reminder" if updated.metadata else False),
                calendar_event_id=cal_id,
            )
            if cal_res.get("id") and (not cal_id or cal_id != cal_res.get("id")):
                new_meta = dict(updated.metadata or {})
                new_meta["calendar_event_id"] = cal_res["id"]
                new_meta["synced_to_calendar"] = True
                await asyncio.to_thread(repo.update, updated.id, {"metadata": new_meta})
                updated = await asyncio.to_thread(repo.get, task_id)
        except Exception as ce:
            logger.warning(f"[TASKS] Google Calendar sync toggle failed for task '{task_id}': {ce}")

        now = datetime.datetime.now().astimezone()
        local_tz = now.tzinfo
        t_min = datetime.datetime.combine(now.date(), datetime.time.min).replace(tzinfo=local_tz)
        t_max = datetime.datetime.combine(now.date(), datetime.time.max).replace(tzinfo=local_tz)
        cat, age = _classify_task(updated, now, t_min, t_max)
        return {"status": "ok", "task": _format_task_dict(updated, cat, age)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TASKS] Error toggling task '{task_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> Dict[str, Any]:
    """Deletes a task by ID and removes any linked Google Calendar event."""
    # Check fallback cache first
    for i, item in enumerate(_FALLBACK_TASKS):
        if item["id"] == task_id:
            cal_id = item.get("metadata", {}).get("calendar_event_id")
            if cal_id:
                try:
                    await _cal_tool.delete_event(cal_id)
                except Exception as ce:
                    logger.warning(f"[TASKS] Failed to delete calendar event '{cal_id}': {ce}")
            _FALLBACK_TASKS.pop(i)
            return {"status": "deleted", "task_id": task_id}

    try:
        repo = TaskRepository()
        existing = await asyncio.to_thread(repo.get, task_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        cal_id = existing.metadata.get("calendar_event_id") if existing.metadata else None
        if cal_id:
            try:
                await _cal_tool.delete_event(cal_id)
            except Exception as ce:
                logger.warning(f"[TASKS] Failed to delete Google Calendar event '{cal_id}': {ce}")

        success = await asyncio.to_thread(repo.delete, task_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete task from repository")

        return {"status": "deleted", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TASKS] Error deleting task '{task_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-calendar")
async def bulk_sync_calendar() -> Dict[str, Any]:
    """Bulk synchronizes all pending and completed tasks to Google Calendar."""
    synced_count = 0
    errors = []

    try:
        repo = TaskRepository()
        tasks = await asyncio.to_thread(repo.list, user_id="default_user", include_completed=True, limit=100)
    except Exception as e:
        logger.warning(f"[TASKS] Failed to list tasks from Supabase for sync: {e}")
        tasks = _FALLBACK_TASKS

    for t in tasks:
        try:
            if isinstance(t, dict):
                t_id = t["id"]
                t_title = t["title"]
                t_deadline = t.get("deadline")
                t_done = t.get("done", False)
                t_prio = t.get("priority", "normal")
                meta = dict(t.get("metadata") or {})
                is_rem = meta.get("item_type") == "reminder"
                cal_id = meta.get("calendar_event_id")

                res = await _cal_tool.sync_task_event(
                    task_id=t_id,
                    title=t_title,
                    deadline=t_deadline,
                    done=t_done,
                    priority=t_prio,
                    is_reminder=is_rem,
                    calendar_event_id=cal_id,
                )
                if res.get("id"):
                    meta["calendar_event_id"] = res["id"]
                    meta["synced_to_calendar"] = True
                    t["metadata"] = meta
                    synced_count += 1
            else:
                meta = dict(t.metadata or {})
                is_rem = meta.get("item_type") == "reminder"
                cal_id = meta.get("calendar_event_id")

                res = await _cal_tool.sync_task_event(
                    task_id=t.id,
                    title=t.title,
                    deadline=t.deadline,
                    done=t.done,
                    priority=t.priority.value if hasattr(t.priority, "value") else str(t.priority),
                    is_reminder=is_rem,
                    calendar_event_id=cal_id,
                )
                if res.get("id"):
                    meta["calendar_event_id"] = res["id"]
                    meta["synced_to_calendar"] = True
                    await asyncio.to_thread(repo.update, t.id, {"metadata": meta})
                    synced_count += 1
        except Exception as e:
            err_msg = f"Task {getattr(t, 'id', None) or t.get('id')}: {e}"
            logger.warning(f"[TASKS] Error syncing task to calendar: {err_msg}")
            errors.append(err_msg)

    return {
        "status": "ok",
        "synced_count": synced_count,
        "total_attempted": len(tasks),
        "errors": errors,
    }
