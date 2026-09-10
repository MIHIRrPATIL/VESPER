"""Tests for VESPER Gateway Tasks REST Endpoints.

Verifies:
1. GET /api/tasks lists categorized tasks (today, overdue, upcoming, completed).
2. Overdue task identification with proper elapsed age formatting.
3. POST /api/tasks creates task with priority and metadata tags.
4. PATCH /api/tasks/{task_id}/toggle toggles completion status.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.gateway.app import app as gateway_app


@pytest.mark.asyncio
async def test_get_tasks_categorization():
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/tasks")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "stats" in data
        assert "today" in data
        assert "overdue" in data
        assert "upcoming" in data
        assert "completed" in data
        assert "tasks" in data

        # Overdue tasks should have age_label
        for task in data["overdue"]:
            assert "overdue" in task["age_label"].lower()


@pytest.mark.asyncio
async def test_create_and_toggle_task():
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Create a task
        create_res = await client.post(
            "/api/tasks",
            json={
                "title": "Automated Unit Test Task",
                "priority": "high",
                "tag": "TEST",
            },
        )
        assert create_res.status_code == 200
        created = create_res.json()["task"]
        task_id = created["id"]
        assert created["title"] == "Automated Unit Test Task"
        assert created["done"] is False

        # 2. Toggle the task to completed
        toggle_res = await client.patch(
            f"/api/tasks/{task_id}/toggle",
            json={"done": True},
        )
        assert toggle_res.status_code == 200
        updated = toggle_res.json()["task"]
        assert updated["done"] is True
