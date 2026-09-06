"""Tests for VESPER Mobile Companion Connectivity & Notification Ingestion Suite.

Verifies:
1. Mobile companion WebSocket handshake and device registration (telemetry, battery, name).
2. NotificationService priority triage (URGENT, HIGH, MEDIUM, LOW).
3. Gateway NOTIFICATION_RELAY ingestion, state synchronization, and NOTIFICATION_DIGEST broadcast.
4. TaskSpecialist mobile notification querying and Alfred persona response formatting.
5. Bidirectional cluster state synchronization with mobile companion.
"""

from __future__ import annotations

import asyncio
import pytest
from fastapi.testclient import TestClient

from backend.agent.specialists.task_specialist import TaskSpecialist
from backend.gateway.app import create_app
from backend.shared.events import Channel, EventType
from backend.sync.models import DeviceRegistration
from backend.sync.notification_service import NotificationPriority, NotificationService
from backend.sync.sync_manager import sync_manager


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


def test_notification_priority_classification(notif_service: NotificationService):
    """Verifies that incoming notifications are correctly triaged into priority buckets."""
    # 1. Urgent: OTP
    p1 = notif_service.classify_priority(
        package_name="com.google.android.apps.messaging",
        title="Bank Alert",
        text="Your one-time password OTP is 481920. Valid for 5 minutes.",
    )
    assert p1 == NotificationPriority.URGENT

    # 2. Urgent: Server outage
    p2 = notif_service.classify_priority(
        package_name="com.datadoghq.app",
        title="CRITICAL INCIDENT",
        text="Production server down in us-east-1.",
    )
    assert p2 == NotificationPriority.URGENT

    # 3. High: WhatsApp message
    p3 = notif_service.classify_priority(
        package_name="com.whatsapp",
        title="Alex Chen",
        text="Hey, are we still meeting at 3 PM?",
    )
    assert p3 == NotificationPriority.HIGH

    # 4. High: Slack direct message
    p4 = notif_service.classify_priority(
        package_name="com.slack",
        title="#general",
        text="New pull request opened on repository.",
    )
    assert p4 == NotificationPriority.HIGH

    # 5. Medium: Gmail email
    p5 = notif_service.classify_priority(
        package_name="com.google.android.gm",
        title="GitHub",
        text="Your weekly digest for team frontend",
    )
    assert p5 == NotificationPriority.MEDIUM

    # 6. Low: System / Promotional alert
    p6 = notif_service.classify_priority(
        package_name="com.some.random.game",
        title="Daily Bonus",
        text="Claim your free coins now!",
    )
    assert p6 == NotificationPriority.LOW


def test_notification_service_ingestion_and_filters(notif_service: NotificationService):
    """Verifies notification storage, unread tracking, filtering, and clearing."""
    n1 = notif_service.ingest_notification(
        payload={"package_name": "com.whatsapp", "title": "John", "text": "Are you there?"},
        source_device_id="phone_01",
        source_device_name="Mihir's Pixel",
    )
    n2 = notif_service.ingest_notification(
        payload={"package_name": "com.slack", "title": "Lead", "text": "Can you check main?"},
        source_device_id="phone_01",
        source_device_name="Mihir's Pixel",
    )

    assert notif_service.get_unread_count() == 2

    # Query recent
    recent = notif_service.get_recent_notifications(limit=10)
    assert len(recent) == 2
    assert recent[0].id == n2.id  # Newest first

    # Filter by app
    wa_items = notif_service.get_recent_notifications(app_filter="whatsapp")
    assert len(wa_items) == 1
    assert wa_items[0].app_name == "WhatsApp"

    # Mark as read
    notif_service.mark_as_read([n2.id])
    assert notif_service.get_unread_count() == 1

    unread_items = notif_service.get_recent_notifications(unread_only=True)
    assert len(unread_items) == 1
    assert unread_items[0].id == n1.id

    # Clear all
    notif_service.clear_all()
    assert notif_service.get_unread_count() == 0
    assert len(notif_service.get_recent_notifications()) == 0


def test_mobile_companion_websocket_handshake_and_registration(client: TestClient):
    """Verifies mobile client WebSocket connection, registration, and battery telemetry."""
    with client.websocket_connect("/ws") as ws:
        # 1. Send CLIENT_HELLO
        hello_frame = {
            "channel": "CONTROL",
            "type": "CLIENT_HELLO",
            "payload": {
                "client_id": "pixel_8_pro_mihir",
                "client_type": "MOBILE_ANDROID",
                "version": "2.0.0",
                "capabilities": ["display", "notification_relay", "audio_capture"],
            },
        }
        ws.send_json(hello_frame)

        # 2. Receive SERVER_HELLO
        res_hello = ws.receive_json()
        assert res_hello["channel"] == "CONTROL"
        assert res_hello["type"] == "SERVER_HELLO"
        assert res_hello["status"] == "ok"

        # 3. Send DEVICE_REGISTER with phone name & battery
        reg_frame = {
            "channel": "SYNC",
            "type": "DEVICE_REGISTER",
            "payload": {
                "device_id": "pixel_8_pro_mihir",
                "device_type": "mobile_android",
                "device_name": "Mihir's Pixel 8 Pro",
                "has_display": True,
                "has_camera": True,
                "has_microphone": True,
                "battery_level": 82,
                "is_charging": False,
                "network_type": "wifi",
            },
        }
        ws.send_json(reg_frame)

        # 4. Receive STATE_SNAPSHOT
        res_snap = ws.receive_json()
        assert res_snap["channel"] == "SYNC"
        assert res_snap["type"] == "STATE_SNAPSHOT"

        # Check sync manager has device
        snap = sync_manager.get_snapshot()
        assert "pixel_8_pro_mihir" in snap.active_devices
        dev = snap.active_devices["pixel_8_pro_mihir"]
        assert dev.device_name == "Mihir's Pixel 8 Pro"
        assert dev.device_type == "mobile_android"
        assert dev.battery_level == 82


def test_mobile_notification_relay_over_websocket(client: TestClient):
    """Verifies that NOTIFICATION_RELAY sends over WebSocket, triages, and broadcasts NOTIFICATION_DIGEST."""
    with client.websocket_connect("/ws") as ws:
        # Handshake
        ws.send_json({
            "channel": "CONTROL",
            "type": "CLIENT_HELLO",
            "payload": {
                "client_id": "galaxy_s24_dev",
                "client_type": "MOBILE_ANDROID",
                "version": "2.0.0",
            },
        })
        ws.receive_json()  # SERVER_HELLO

        # Register device
        ws.send_json({
            "channel": "SYNC",
            "type": "DEVICE_REGISTER",
            "payload": {
                "device_id": "galaxy_s24_dev",
                "device_type": "mobile_android",
                "device_name": "Galaxy S24",
            },
        })
        # Receive STATE_SNAPSHOT
        res_snap = ws.receive_json()
        assert res_snap["channel"] == "SYNC"

        # Receive broadcast DEVICE_REGISTER
        res_broadcast = ws.receive_json()
        assert res_broadcast["channel"] == "SYNC"
        assert res_broadcast["type"] == "DEVICE_REGISTER"

        # Emit NOTIFICATION_RELAY
        notif_payload = {
            "package_name": "com.whatsapp",
            "title": "Sarah Jenkins",
            "text": "Project design docs have been approved!",
            "post_time": 1788649000.0,
        }
        ws.send_json({
            "channel": "NOTIFY",
            "type": "NOTIFICATION_RELAY",
            "payload": notif_payload,
        })

        # Receive broadcast NOTIFICATION_DIGEST
        digest_env = ws.receive_json()
        assert digest_env["channel"] == "NOTIFY"
        assert digest_env["type"] == "NOTIFICATION_DIGEST"
        assert digest_env["payload"]["device_name"] == "Galaxy S24"
        assert digest_env["payload"]["notification"]["priority"] == "HIGH"
        assert digest_env["payload"]["notification"]["app_name"] == "WhatsApp"
        assert digest_env["payload"]["unread_count"] >= 1


@pytest.mark.asyncio
async def test_task_specialist_list_mobile_notifications(notif_service: NotificationService):
    """Verifies that Alfred's TaskSpecialist lists and articulates mobile alerts."""
    notif_service.clear_all()
    notif_service.ingest_notification(
        payload={"package_name": "com.whatsapp", "title": "David", "text": "Are you coming to the sync?"},
        source_device_id="pixel_8",
        source_device_name="Pixel 8",
    )

    specialist = TaskSpecialist()
    res = await specialist.execute("list_mobile_notifications", {})

    assert res.success is True
    assert "David" in res.speech_summary or "WhatsApp" in res.speech_summary
    assert res.data["unread_count"] == 1
    assert res.card_payload is not None
    assert res.card_payload["type"] == "NOTIFICATION_DIGEST"
    assert len(res.card_payload["items"]) == 1


def test_notification_rest_endpoints(client: TestClient):
    """Verifies /api/notifications REST endpoints for testing and client querying."""
    # Ingest test notification via REST
    resp_post = client.post(
        "/api/notifications/test",
        json={
            "package_name": "org.telegram.messenger",
            "app_name": "Telegram",
            "title": "DevOps Channel",
            "text": "Deployment 2.4.1 completed successfully.",
            "device_name": "Test Phone",
        },
    )
    assert resp_post.status_code == 200
    data = resp_post.json()
    assert data["status"] == "ok"
    assert data["notification"]["app_name"] == "Telegram"

    # List notifications
    resp_get = client.get("/api/notifications?limit=5")
    assert resp_get.status_code == 200
    list_data = resp_get.json()
    assert list_data["unread_count"] >= 1
    assert any(n["app_name"] == "Telegram" for n in list_data["notifications"])

    # Clear notifications
    resp_clear = client.post("/api/notifications/clear")
    assert resp_clear.status_code == 200
    assert resp_clear.json()["unread_count"] == 0
