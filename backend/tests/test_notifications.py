"""Comprehensive tests for VESPER Notification Triage, In-Place Updates, and Grouping.

Tests:
1. Priority classification across URGENT, HIGH, MEDIUM, LOW.
2. Persistent background keep-alive suppression (NoiseFit, Fitbit, Wearable trackers).
3. In-place notification updating for progress bars (Chrome downloads).
4. OS-style grouped notification retrieval (/api/notifications/grouped).
5. Gateway WebSocket NOTIFICATION_RELAY in-place update flags.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.gateway.app import create_app
from backend.sync.notification_service import (
    MobileNotification,
    NotificationPriority,
    NotificationService,
)


@pytest.fixture
def client():
    """Creates a TestClient with full lifespan context."""
    test_app = create_app()
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def notif_service() -> NotificationService:
    service = NotificationService.get_instance()
    service.clear_all()
    return service


def test_persistent_keepalive_suppression(notif_service: NotificationService):
    """Verifies that persistent fitness trackers and background syncs are suppressed."""
    # 1. NoiseFit "is running" keep-alive
    res1 = notif_service.ingest_notification(
        payload={
            "package_name": "com.noisefit",
            "title": "NoiseFit is running",
            "text": "last sync at 10:30 AM",
        },
        source_device_id="samsung_s23",
        source_device_name="Mihir's S23",
    )
    assert res1 is None
    assert notif_service.get_unread_count() == 0

    # 2. Fitbit background sync keep-alive
    res2 = notif_service.ingest_notification(
        payload={
            "package_name": "com.fitbit",
            "title": "Fitbit",
            "text": "Syncing in background. Tap for info.",
        },
        source_device_id="samsung_s23",
        source_device_name="Mihir's S23",
    )
    assert res2 is None
    assert notif_service.get_unread_count() == 0

    # 3. Legitimate user-facing alert from NoiseFit should NOT be filtered
    res3 = notif_service.ingest_notification(
        payload={
            "package_name": "com.noisefit",
            "title": "Goal Reached!",
            "text": "You achieved your 10,000 steps goal for today.",
        },
        source_device_id="samsung_s23",
        source_device_name="Mihir's S23",
    )
    assert res3 is not None
    assert res3.title == "Goal Reached!"
    assert notif_service.get_unread_count() == 1


def test_inplace_notification_update_for_downloads(notif_service: NotificationService):
    """Verifies that rapid download progress updates mutate existing notification in-place."""
    dev_id = "samsung_s23"
    pkg = "com.android.chrome"
    title = "application-987995ed-….apk"

    # Tick 1: Download starts at 40.41 MB
    n1 = notif_service.ingest_notification(
        payload={
            "package_name": pkg,
            "title": title,
            "text": "40.41 MB/69.76 MB",
        },
        source_device_id=dev_id,
        source_device_name="Mihir's S23",
    )
    assert n1 is not None
    assert n1.text == "40.41 MB/69.76 MB"
    assert n1.is_in_place_update is False
    assert notif_service.get_unread_count() == 1
    assert len(notif_service.get_recent_notifications()) == 1
    original_id = n1.id

    # Tick 2: Progress at 41.86 MB
    n2 = notif_service.ingest_notification(
        payload={
            "package_name": pkg,
            "title": title,
            "text": "41.86 MB/69.76 MB",
        },
        source_device_id=dev_id,
        source_device_name="Mihir's S23",
    )
    assert n2 is not None
    assert n2.id == original_id
    assert n2.text == "41.86 MB/69.76 MB"
    assert n2.is_in_place_update is True
    # Count should STILL be 1 (NOT 2)
    assert notif_service.get_unread_count() == 1
    assert len(notif_service.get_recent_notifications()) == 1

    # Tick 3: Progress at 44.63 MB
    n3 = notif_service.ingest_notification(
        payload={
            "package_name": pkg,
            "title": title,
            "text": "44.63 MB/69.76 MB",
        },
        source_device_id=dev_id,
        source_device_name="Mihir's S23",
    )
    assert n3 is not None
    assert n3.id == original_id
    assert n3.text == "44.63 MB/69.76 MB"
    assert notif_service.get_unread_count() == 1
    assert len(notif_service.get_recent_notifications()) == 1

    # Tick 4: Download complete
    n4 = notif_service.ingest_notification(
        payload={
            "package_name": pkg,
            "title": title,
            "text": "Download complete",
        },
        source_device_id=dev_id,
        source_device_name="Mihir's S23",
    )
    assert n4 is not None
    assert n4.id == original_id
    assert n4.text == "Download complete"
    assert notif_service.get_unread_count() == 1
    assert len(notif_service.get_recent_notifications()) == 1


def test_system_noise_and_blank_filtered(notif_service: NotificationService):
    """Verifies that Android system noise and blank payloads are dropped."""
    # Blank
    assert notif_service.ingest_notification({}, "dev1") is None
    assert notif_service.ingest_notification({"title": "", "text": ""}, "dev1") is None

    # System UI
    res_sys = notif_service.ingest_notification(
        {"package_name": "com.android.systemui", "title": "USB debugging", "text": "connected"},
        "dev1",
    )
    assert res_sys is None

    # Google Play Services
    res_gms = notif_service.ingest_notification(
        {"package_name": "com.google.android.gms", "title": "Google Play", "text": "updating"},
        "dev1",
    )
    assert res_gms is None


def test_grouped_notifications_rest_endpoint(client: TestClient, notif_service: NotificationService):
    """Verifies /api/notifications/grouped returns notifications grouped by app."""
    # Ingest multiple notifications across different apps
    notif_service.ingest_notification(
        {"package_name": "com.whatsapp", "title": "Mom", "text": "Call me back"},
        "s23",
    )
    notif_service.ingest_notification(
        {"package_name": "com.whatsapp", "title": "Dev Team", "text": "Meeting at 4"},
        "s23",
    )
    notif_service.ingest_notification(
        {"package_name": "com.slack", "title": "CI/CD", "text": "Build #42 passed"},
        "s23",
    )

    resp = client.get("/api/notifications/grouped")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert data["unread_count"] == 3
    assert data["total_apps"] == 2
    assert "WhatsApp" in data["grouped"]
    assert "Slack" in data["grouped"]
    assert len(data["grouped"]["WhatsApp"]) == 2
    assert len(data["grouped"]["Slack"]) == 1


def test_websocket_notification_inplace_flag(client: TestClient, notif_service: NotificationService):
    """Verifies that WebSocket broadcast includes is_update flag for ambient HUD."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_json({
            "channel": "CONTROL",
            "type": "CLIENT_HELLO",
            "payload": {"client_id": "test_phone", "client_type": "MOBILE_ANDROID"},
        })
        ws.receive_json()

        # Send initial notification
        ws.send_json({
            "channel": "NOTIFY",
            "type": "NOTIFICATION_RELAY",
            "payload": {
                "package_name": "com.android.chrome",
                "title": "large_file.iso",
                "text": "10 MB/100 MB",
            },
        })

        env1 = ws.receive_json()
        assert env1["channel"] == "NOTIFY"
        assert env1["type"] == "NOTIFICATION_DIGEST"
        assert env1["payload"]["is_update"] is False
        assert env1["payload"]["notification"]["text"] == "10 MB/100 MB"

        # Send updated progress tick
        ws.send_json({
            "channel": "NOTIFY",
            "type": "NOTIFICATION_RELAY",
            "payload": {
                "package_name": "com.android.chrome",
                "title": "large_file.iso",
                "text": "35 MB/100 MB",
            },
        })

        env2 = ws.receive_json()
        assert env2["channel"] == "NOTIFY"
        assert env2["type"] == "NOTIFICATION_DIGEST"
        assert env2["payload"]["is_update"] is True
        assert env2["payload"]["notification"]["text"] == "35 MB/100 MB"


def test_http_notification_relay_endpoint(client: TestClient, notif_service: NotificationService):
    """Verifies that /api/notifications/relay accepts live alerts over HTTP and broadcasts."""
    resp = client.post(
        "/api/notifications/relay",
        json={
            "package_name": "com.whatsapp",
            "app_name": "WhatsApp",
            "title": "Mihir",
            "text": "Meeting at 4pm today",
            "device_id": "mobile_companion_s23",
            "device_name": "Galaxy S23",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["delivered"] is True
    assert data["notification"]["title"] == "Mihir"
    assert notif_service.get_unread_count() >= 1


def test_call_event_detection(notif_service: NotificationService):
    """Verifies that incoming and ended calls are accurately detected and prioritized."""
    # 1. Samsung in-call UI incoming call
    is_call, phase = NotificationService.detect_call_event(
        "com.samsung.android.incallui", "Mom", "Incoming call..."
    )
    assert is_call is True
    assert phase == "INCOMING"
    prio = NotificationService.classify_priority("com.samsung.android.incallui", "Mom", "Incoming call...")
    assert prio == NotificationPriority.URGENT

    # 2. Google Dialer incoming video call
    is_call, phase = NotificationService.detect_call_event(
        "com.google.android.dialer", "Sarah Connor", "Incoming video call"
    )
    assert is_call is True
    assert phase == "INCOMING"

    # 3. WhatsApp incoming voice call
    is_call, phase = NotificationService.detect_call_event(
        "com.whatsapp", "Alex Chen", "Incoming WhatsApp Call"
    )
    assert is_call is True
    assert phase == "INCOMING"

    # 4. Ended / Missed call
    is_call, phase = NotificationService.detect_call_event(
        "com.google.android.dialer", "Missed call", "Missed call from Sarah Connor"
    )
    assert is_call is True
    assert phase == "ENDED"

    # 5. Ingest notification via service
    notif = notif_service.ingest_notification(
        payload={
            "package_name": "com.samsung.android.incallui",
            "title": "Sarah Connor",
            "text": "Incoming voice call...",
        },
        source_device_id="samsung_s23",
    )
    assert notif is not None
    assert notif.is_call is True
    assert notif.call_phase == "INCOMING"
    assert notif.priority == NotificationPriority.URGENT


def test_websocket_call_event_broadcast(client: TestClient):
    """Verifies that incoming call notifications carry is_call flag and CALL_STATE is broadcast."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_json({
            "channel": "CONTROL",
            "type": "CLIENT_HELLO",
            "payload": {"client_id": "test_phone", "client_type": "MOBILE_ANDROID"},
        })
        ws.receive_json()

        # Send incoming call NOTIFICATION_RELAY
        ws.send_json({
            "channel": "NOTIFY",
            "type": "NOTIFICATION_RELAY",
            "payload": {
                "package_name": "com.google.android.dialer",
                "title": "Incoming Call: Sarah Connor",
                "text": "Ringing...",
            },
        })

        env = ws.receive_json()
        assert env["channel"] == "NOTIFY"
        assert env["type"] == "NOTIFICATION_DIGEST"
        assert env["payload"]["is_call"] is True
        assert env["payload"]["call_phase"] == "INCOMING"

        # Send direct CALL_STATE event
        ws.send_json({
            "channel": "NOTIFY",
            "type": "CALL_STATE",
            "payload": {
                "state": "OFFHOOK",
                "number": "+15550192834",
            },
        })

        call_env = ws.receive_json()
        assert call_env["channel"] == "NOTIFY"
        assert call_env["type"] == "CALL_STATE"
        assert call_env["payload"]["state"] == "OFFHOOK"


def test_notification_search_service():
    """Verifies that NotificationService searches notifications by sender, query, and app."""
    svc = NotificationService()
    svc.ingest_notification(
        payload={
            "package_name": "com.whatsapp",
            "title": "DJSCE 2027 Placement Announcements: ~ Tia Shah",
            "text": "UBS shortlist: Raiyyan Patel, Nandini Nema, Vinay Vora.",
        },
        source_device_id="phone_1",
    )
    svc.ingest_notification(
        payload={
            "package_name": "com.slack",
            "title": "Engineering",
            "text": "Deployment scheduled for tonight.",
        },
        source_device_id="phone_1",
    )

    # Search by sender
    matches = svc.search_notifications(sender_filter="Tia Shah")
    assert len(matches) == 1
    assert "Tia Shah" in matches[0].title

    # Search by app
    wa_matches = svc.search_notifications(app_filter="whatsapp")
    assert len(wa_matches) == 1

    # Search by keyword
    shortlist_matches = svc.search_notifications(query="shortlist")
    assert len(shortlist_matches) == 1

    # Search non-existent
    empty = svc.search_notifications(query="nonexistent string 12345")
    assert len(empty) == 0


@pytest.mark.asyncio
async def test_task_specialist_notification_name_check():
    """Verifies that TaskSpecialist search_mobile_notifications truthfully checks user name."""
    from backend.agent.specialists.task_specialist import TaskSpecialist
    svc = NotificationService()
    svc.ingest_notification(
        payload={
            "package_name": "com.whatsapp",
            "title": "DJSCE 2027 Announcements: ~ Tia Shah",
            "text": "UBS shortlist: Raiyyan Siraj Patel, Nandini Nema, Vinay Vora.",
        },
        source_device_id="phone_1",
    )

    spec = TaskSpecialist(notif_service=svc)
    # Query checking if user's name (Mihir) is in the shortlist
    res = await spec.execute(
        "search_mobile_notifications",
        {"query": "is my name in the notification", "sender": "Tia Shah", "app": "whatsapp"},
    )
    assert res.success is True
    assert res.data["name_found"] is False
    assert "does not appear" in res.speech_summary or "not mentioned" in res.speech_summary

    # When user's name is in the shortlist
    svc.ingest_notification(
        payload={
            "package_name": "com.whatsapp",
            "title": "DJSCE 2027 Announcements: ~ Tia Shah",
            "text": "UBS shortlist: Raiyyan Patel, Mihir Patil, Nandini Nema.",
        },
        source_device_id="phone_1",
    )
    res_found = await spec.execute(
        "search_mobile_notifications",
        {"query": "is my name in the notification", "sender": "Tia Shah", "app": "whatsapp"},
    )
    assert res_found.success is True
    assert res_found.data["name_found"] is True
    assert "is present" in res_found.speech_summary

    # When no matching notification exists in store (honest boundary fallback)
    res_empty = await spec.execute(
        "search_mobile_notifications",
        {"query": "Unknown Project", "sender": "Unknown Sender"},
    )
    assert res_empty.success is True
    assert res_empty.data["found"] is False
    assert "Sir, I checked the notifications forwarded from your mobile companion" in res_empty.speech_summary
    assert "do not have access to your full WhatsApp chat history or database" in res_empty.speech_summary


@pytest.mark.asyncio
async def test_planner_routes_notification_query_to_search():
    """Verifies that queries about notifications/WhatsApp messages route to tasks search, not vision OCR."""
    from backend.agent.planner import SwarmPlanner
    from backend.agent.registry import SpecialistRegistry
    from backend.agent.specialists.task_specialist import TaskSpecialist
    from backend.agent.specialists.vision_specialist import VisionSpecialist

    reg = SpecialistRegistry()
    reg.register(TaskSpecialist())
    reg.register(VisionSpecialist())

    planner = SwarmPlanner()
    plan, _ = await planner.create_plan(
        "Can you check if there is my name in the notification that Tia Shah sent on WhatsApp?",
        registry=reg,
    )
    assert plan is not None
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step["agent"] == "tasks"
    assert step["action"] == "search_mobile_notifications"
    assert step["params"].get("app") == "whatsapp"
    assert "Tia Shah" in step["params"].get("sender", "")



