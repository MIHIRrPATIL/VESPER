"""Tests for Proactive Executive Briefing Manager and Fast-Path Routing."""

import datetime
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agent.fast_path import FastPathEngine
from backend.agent.proactive.briefing_manager import (
    BriefingManager,
    _get_day_suffix,
    _get_time_of_day_salutation,
)
from backend.agent.proactive_agent import ProactiveAgent


def test_day_suffix_ordinals():
    assert _get_day_suffix(1) == "st"
    assert _get_day_suffix(2) == "nd"
    assert _get_day_suffix(3) == "rd"
    assert _get_day_suffix(4) == "th"
    assert _get_day_suffix(11) == "th"
    assert _get_day_suffix(12) == "th"
    assert _get_day_suffix(13) == "th"
    assert _get_day_suffix(21) == "st"
    assert _get_day_suffix(22) == "nd"
    assert _get_day_suffix(23) == "rd"
    assert _get_day_suffix(31) == "st"


def test_time_of_day_salutations():
    # Morning: 5 to 11
    assert _get_time_of_day_salutation(6) == "Good morning, sir."
    assert _get_time_of_day_salutation(11) == "Good morning, sir."
    # Afternoon: 12 to 16
    assert _get_time_of_day_salutation(12) == "Good afternoon, sir."
    assert _get_time_of_day_salutation(15) == "Good afternoon, sir."
    # Evening: 17 to 21
    assert _get_time_of_day_salutation(18) == "Good evening, sir."
    assert _get_time_of_day_salutation(21) == "Good evening, sir."
    # Late night: 22+ or < 5
    assert "late hour" in _get_time_of_day_salutation(23)
    assert "late hour" in _get_time_of_day_salutation(2)


def test_fast_path_briefing_rules():
    fp = FastPathEngine()
    phrases = [
        "briefing",
        "daily briefing",
        "morning briefing",
        "evening briefing",
        "executive briefing",
        "give me a briefing",
        "give me my briefing",
        "what is my schedule",
        "what's my schedule today",
        "today's schedule",
        "today's agenda",
        "summarize recent activities",
        "summarize my activities",
    ]
    for p in phrases:
        res = fp.evaluate(p)
        assert res.matched is True, f"Failed on: {p}"
        assert res.intent == "proactive"
        assert res.action == "briefing"
        assert len(res.speech_text) > 0


def test_fast_path_identity_and_memory():
    fp = FastPathEngine()

    # 1. Store Name
    res1 = fp.evaluate("always remember alfred that my name is mihir")
    assert res1.matched is True
    assert res1.intent == "memory"
    assert res1.action == "store_name"
    assert "mihir" in res1.speech_text.lower()

    # 2. Recall Name
    res2 = fp.evaluate("what is my name?")
    assert res2.matched is True
    assert res2.intent == "memory"
    assert res2.action == "recall_name"
    assert "mihir" in res2.speech_text.lower()

    # 3. User Profile Dossier Recall
    res3 = fp.evaluate("what have you learned about me so far?")
    assert res3.matched is True
    assert res3.intent == "memory"
    assert res3.action == "get_user_profile"
    assert len(res3.speech_text) > 0

    # 4. Generic Remember
    res4 = fp.evaluate("always remember alfred that I prefer black coffee without sugar")
    assert res4.matched is True
    assert res4.intent == "memory"
    assert res4.action == "store_memory"

    # 5. Dismissals
    res5 = fp.evaluate("nothing alfred, keep playing the music")
    assert res5.matched is True
    assert res5.intent == "system"
    assert res5.action == "dismiss"


@pytest.mark.asyncio
async def test_briefing_manager_minimal_fallback():
    mgr = BriefingManager()
    fallback = mgr._build_minimal_fallback_briefing()
    assert "Executive Briefing" in fallback["title"]
    assert "sir" in fallback["speech"]
    assert "All VESPER services" in fallback["speech"]
    assert len(fallback["hud_cards"]) == 1


@pytest.mark.asyncio
async def test_briefing_composition():
    mgr = BriefingManager()
    fixed_now = datetime.datetime(2026, 9, 9, 10, 15)

    events = [
        {"summary": "Team Sync", "start": "11:00 AM"},
        {"summary": "Design Architecture", "start": "02:00 PM"},
    ]

    class MockTask:
        def __init__(self, title, priority):
            self.title = title
            self.priority = priority

    tasks = [
        MockTask("Review pull request", "high"),
        MockTask("Clean desk", "low"),
    ]

    class MockAudit:
        def __init__(self, text):
            self.verbatim_text = text

    audit_entries = [
        MockAudit("Expense logged at Swiggy"),
        MockAudit("Zen mode enabled"),
    ]

    speech, md, card = mgr._compose_briefing(
        now=fixed_now,
        events=events,
        tasks=tasks,
        audit_entries=audit_entries,
        staged_pending=[],
        sys_health={"status": "NOMINAL", "cpu_percent": 12.0, "ram_percent": 45.0},
    )

    # Butler checks
    assert "Good morning, sir" in speech
    assert "Wednesday, September 9th" in speech
    assert "Team Sync" in speech
    assert "Review pull request" in speech
    assert "Expense logged at Swiggy" in speech
    assert "All VESPER services are initialized" in speech

    # Markdown checks
    assert "### Executive Intelligence Briefing" in md
    assert "Team Sync" in md
    assert "[HIGH] Review pull request" in md

    # Card checks
    assert card["type"] == "briefing"
    assert card["events_count"] == 2
    assert card["tasks_count"] == 2


@pytest.mark.asyncio
async def test_proactive_agent_deliver_briefing_dedup(tmp_path):
    agent = ProactiveAgent()
    agent._state_file_path = tmp_path / "last_briefing.json"
    send_mock = AsyncMock()
    agent.set_send_to_session_callback(send_mock)

    # Deliver once
    await agent.deliver_startup_briefing(session_id="sess_test_123")
    assert send_mock.call_count == 1

    # Deliver second time without force within cooldown -> should deduplicate
    await agent.deliver_startup_briefing(session_id="sess_test_123")
    assert send_mock.call_count == 1

    # Deliver with force=True -> should send
    await agent.deliver_startup_briefing(session_id="sess_test_123", force=True)
    assert send_mock.call_count == 2


@pytest.mark.asyncio
async def test_startup_briefing_1h_cooldown(tmp_path, monkeypatch):
    agent = ProactiveAgent()
    agent._state_file_path = tmp_path / "cooldown_test.json"
    send_mock = AsyncMock()
    agent.set_send_to_session_callback(send_mock)

    current_t = 1000000.0
    monkeypatch.setattr(time, "time", lambda: current_t)

    # 1. Initial delivery at T=1,000,000s
    await agent.deliver_startup_briefing(session_id="sess_1")
    assert send_mock.call_count == 1

    # 2. Restart/attempt 30 minutes later (T + 1800s) -> within 3600s cooldown -> skipped
    agent_restarted = ProactiveAgent()
    agent_restarted._state_file_path = tmp_path / "cooldown_test.json"
    agent_restarted.set_send_to_session_callback(send_mock)

    current_t += 1800.0
    await agent_restarted.deliver_startup_briefing(session_id="sess_1")
    assert send_mock.call_count == 1  # Not incremented

    # 3. Explicit force delivery -> bypasses cooldown
    await agent_restarted.deliver_startup_briefing(session_id="sess_1", force=True)
    assert send_mock.call_count == 2

    # 4. Attempt 61 minutes after last delivery (T + 3660s) -> succeeds automatically
    current_t += 3661.0
    await agent_restarted.deliver_startup_briefing(session_id="sess_1")
    assert send_mock.call_count == 3


@pytest.mark.asyncio
async def test_overdue_task_classification():
    mgr = BriefingManager()
    fixed_now = datetime.datetime(2026, 9, 9, 10, 0, tzinfo=datetime.timezone.utc)

    class MockTaskItem:
        def __init__(self, title, priority="normal", deadline=None, created_at=None, metadata=None):
            self.title = title
            self.priority = priority
            self.deadline = deadline
            self.created_at = created_at
            self.metadata = metadata or {}

    # Task 1: Due today -> today_tasks
    t_today = MockTaskItem(
        title="Today Meeting Presentation",
        deadline=fixed_now + datetime.timedelta(hours=4),
        created_at=fixed_now - datetime.timedelta(hours=1),
    )
    # Task 2: Created 2 days ago without deadline and undone -> overdue_tasks
    t_overdue_created = MockTaskItem(
        title="Pick up my mom",
        priority="high",
        created_at=fixed_now - datetime.timedelta(days=2),
    )
    # Task 3: Deadline was yesterday -> overdue_tasks
    t_overdue_deadline = MockTaskItem(
        title="Submit quarterly report",
        priority="high",
        deadline=fixed_now - datetime.timedelta(days=1),
        created_at=fixed_now - datetime.timedelta(days=3),
    )
    # Task 4: Stale reminder from 4 days ago -> overdue reminder
    t_overdue_reminder = MockTaskItem(
        title="Call landlord",
        created_at=fixed_now - datetime.timedelta(days=4),
        metadata={"item_type": "reminder"},
    )
    # Task 5: Scheduled for next week -> backlog_tasks
    t_future = MockTaskItem(
        title="Doctor appointment",
        deadline=fixed_now + datetime.timedelta(days=7),
        created_at=fixed_now - datetime.timedelta(hours=2),
    )

    tasks = [t_today, t_overdue_created, t_overdue_deadline, t_overdue_reminder, t_future]

    speech, md, card = mgr._compose_briefing(
        now=fixed_now,
        events=[],
        tasks=tasks,
        audit_entries=[],
        staged_pending=[],
        sys_health={"status": "NOMINAL"},
    )

    # 1. Today tasks verify
    assert card["today_tasks_count"] == 1
    assert "Today Meeting Presentation" in speech
    assert "1 task scheduled" in speech

    # 2. Overdue tasks verify
    assert card["overdue_tasks_count"] == 3
    assert "[OVERDUE]" in md
    assert "Pick up my mom" in md
    assert "2 days overdue" in md
    assert "Submit quarterly report" in md
    assert "Call landlord" in md
    assert "overdue item" in speech

    # 3. Future tasks verify
    assert "#### Upcoming Tasks (Future)" in md
    assert "Doctor appointment" in md


def test_websocket_startup_briefing_delivery(tmp_path):
    import json
    from starlette.testclient import TestClient
    from backend.gateway.app import create_app
    from backend.shared.events import Channel, EventType, ClientType
    from backend.agent.proactive_agent import proactive_agent

    # Ensure clean cooldown state for this test
    proactive_agent._last_briefing_time = 0.0
    proactive_agent._state_file_path = tmp_path / "ws_briefing.json"

    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # Send CLIENT_HELLO with startup_briefing capability and desktop terminal client_id
            ws.send_text(json.dumps({
                "uuid": "hello-briefing-01",
                "channel": Channel.CONTROL.value,
                "type": EventType.CLIENT_HELLO.value,
                "payload": {
                    "client_id": "vesper-desktop-terminal",
                    "client_type": ClientType.DESK_HUD.value,
                    "capabilities": ["control", "startup_briefing"],
                },
            }))
            raw_hello = ws.receive_text()
            server_hello = json.loads(raw_hello)
            assert server_hello["type"] == EventType.SERVER_HELLO.value

            # Await startup briefing frame delivered directly upon connection
            raw_briefing = ws.receive_text()
            briefing_env = json.loads(raw_briefing)
            assert briefing_env["channel"] == Channel.NOTIFY.value
            assert briefing_env["type"] == EventType.NOTIFICATION_DIGEST.value
            p = briefing_env["payload"]
            assert p.get("proactive") is True
            assert p.get("type") == "startup_briefing"
            assert len(p.get("speech", "")) > 0
            assert "sir" in p["speech"].lower()
