"""Unit tests for Google Calendar auto-synchronization with tasks and reminders."""

import pytest
import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from backend.agent.tools.calendar_tool import GoogleCalendarTool
from backend.gateway.app import app


@pytest.mark.asyncio
async def test_sync_task_event_mock():
    """Test sync_task_event creates and updates events properly."""
    tool = GoogleCalendarTool()

    fake_path = MagicMock(spec=Path)
    fake_path.exists.return_value = False

    with patch("backend.agent.tools.calendar_tool.TOKEN_PATH", fake_path):
        # 1. Create untimed task
        res = await tool.sync_task_event(
            task_id="test_task_1",
            title="Inspect telemetry node",
            deadline=None,
            done=False,
            priority="high",
            is_reminder=False,
        )
        assert res["status"] == "mock_created"
        assert "Inspect telemetry node" in res["summary"]

        # 2. Update with completion
        mock_id = res["id"]
        res_comp = await tool.sync_task_event(
            task_id="test_task_1",
            title="Inspect telemetry node",
            deadline=None,
            done=True,
            priority="high",
            is_reminder=False,
            calendar_event_id=mock_id,
        )
        assert res_comp["status"] == "mock_updated"
        assert res_comp["summary"].startswith("✓ [Completed] Task:")


def test_gateway_tasks_calendar_integration():
    """Test gateway /api/tasks endpoints sync with Google Calendar."""
    client = TestClient(app)

    with patch("backend.gateway.routes.tasks._cal_tool.sync_task_event", new_callable=AsyncMock) as mock_sync, \
         patch("backend.gateway.routes.tasks._cal_tool.delete_event", new_callable=AsyncMock) as mock_delete:

        mock_sync.return_value = {
            "id": "gcal_ev_123",
            "summary": "Task: Verify gateway endpoints",
            "status": "confirmed",
        }
        mock_delete.return_value = True

        # 1. Create Task
        resp = client.post(
            "/api/tasks/",
            json={
                "title": "Verify gateway endpoints",
                "priority": "urgent",
                "tag": "TEST",
                "metadata": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        task = data["task"]
        task_id = task["id"]
        assert mock_sync.called

        # 2. Toggle Task
        resp_toggle = client.patch(f"/api/tasks/{task_id}/toggle", json={"done": True})
        assert resp_toggle.status_code == 200
        toggle_data = resp_toggle.json()
        assert toggle_data["task"]["done"] is True

        # 3. Bulk Sync
        resp_bulk = client.post("/api/tasks/sync-calendar")
        assert resp_bulk.status_code == 200
        bulk_data = resp_bulk.json()
        assert bulk_data["status"] == "ok"
        assert bulk_data["synced_count"] >= 1

        # 4. Delete Task
        resp_del = client.delete(f"/api/tasks/{task_id}")
        assert resp_del.status_code == 200
        assert resp_del.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_specialist_tasks_calendar_integration():
    """Test TaskSpecialist syncs to Google Calendar on add_task and complete_task."""
    from backend.agent.specialists.task_specialist import TaskSpecialist
    from backend.data.models import PriorityLevel, TaskModel

    specialist = TaskSpecialist()

    fake_task = TaskModel(
        id="task_spec_test_1",
        user_id="default_user",
        title="Deploy edge sentry node",
        done=False,
        priority=PriorityLevel.HIGH,
        metadata={"item_type": "task"},
        created_at=datetime.datetime.now().astimezone(),
        updated_at=datetime.datetime.now().astimezone(),
    )

    with patch.object(specialist.repo, "create", return_value=fake_task), \
         patch.object(specialist.repo, "update", return_value=fake_task), \
         patch.object(specialist.repo, "get", return_value=fake_task), \
         patch.object(specialist.repo, "mark_done", return_value=True), \
         patch.object(specialist.calendar, "sync_task_event", new_callable=AsyncMock) as mock_sync:

        mock_sync.return_value = {"id": "cal_ev_specialist_1", "status": "confirmed"}

        # 1. Add Task via specialist
        res_add = await specialist.execute("add_task", {"title": "Deploy edge sentry node", "priority": "high"})
        assert res_add.success is True
        assert mock_sync.called

        # 2. Complete Task via specialist
        res_done = await specialist.execute("complete_task", {"task_id": "task_spec_test_1"})
        assert res_done.success is True
        assert mock_sync.call_count >= 2
