"""Bulk synchronization script: Sync all Supabase tasks and reminders to Google Calendar."""

import asyncio
import logging
from backend.data.repositories.tasks import TaskRepository
from backend.agent.tools.calendar_tool import GoogleCalendarTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vesper.sync_script")

async def main():
    repo = TaskRepository()
    cal = GoogleCalendarTool()
    tasks = repo.list(user_id="default_user", include_completed=True, limit=100)
    print(f"Discovered {len(tasks)} tasks in Supabase repository.")
    
    synced = 0
    for t in tasks:
        meta = dict(t.metadata or {})
        cal_id = meta.get("calendar_event_id")
        print(f"Syncing task: '{t.title}' (ID: {t.id}, Existing Cal ID: {cal_id}, Done: {t.done})...")
        res = await cal.sync_task_event(
            task_id=t.id,
            title=t.title,
            deadline=t.deadline,
            done=t.done,
            priority=t.priority.value if hasattr(t.priority, "value") else str(t.priority),
            is_reminder=(meta.get("item_type") == "reminder"),
            calendar_event_id=cal_id,
        )
        if res.get("id"):
            meta["calendar_event_id"] = res["id"]
            meta["synced_to_calendar"] = True
            repo.update(t.id, {"metadata": meta})
            print(f"  -> Successfully synced to Google Calendar: {res['id']}")
            synced += 1
        else:
            print(f"  -> Sync failed: {res}")
            
    print(f"Completed bulk sync. Total synchronized: {synced}/{len(tasks)}")

if __name__ == "__main__":
    asyncio.run(main())
