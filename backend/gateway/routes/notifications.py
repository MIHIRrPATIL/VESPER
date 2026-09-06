"""VESPER Gateway Notification REST Endpoints.

Provides administrative, inspection, and simulation endpoints for mobile
companion notifications ingested across the cluster.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.shared.events import Channel, EventType, ServerEnvelope
from backend.sync.notification_service import notification_service
from backend.sync.sync_manager import sync_manager

logger = logging.getLogger("vesper.gateway.routes.notifications")
router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


class TestNotificationRequest(BaseModel):
    package_name: str = "com.whatsapp"
    app_name: Optional[str] = None
    title: str = "Test Notification"
    text: str = "Hello from VESPER Mobile Companion"
    subtext: Optional[str] = None
    priority: Optional[str] = None
    device_id: str = "test_device"
    device_name: str = "Pixel 8 Pro"


class MarkReadRequest(BaseModel):
    notification_ids: Optional[List[str]] = None


@router.get("")
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    min_priority: Optional[str] = Query(None),
    app_filter: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Lists ingested notifications with optional filtering."""
    items = notification_service.get_recent_notifications(
        limit=limit,
        unread_only=unread_only,
        min_priority=min_priority,
        app_filter=app_filter,
    )
    return {
        "status": "ok",
        "unread_count": notification_service.get_unread_count(),
        "total_returned": len(items),
        "notifications": [item.to_dict() for item in items],
    }


@router.post("/test")
async def ingest_test_notification(req: TestNotificationRequest) -> Dict[str, Any]:
    """Simulates ingesting a mobile notification (useful for testing and Expo Go)."""
    notif = notification_service.ingest_notification(
        payload=req.model_dump(),
        source_device_id=req.device_id,
        source_device_name=req.device_name,
    )

    # Sync state count and preview
    recent = [n.to_dict() for n in notification_service.get_recent_notifications(limit=5)]
    await sync_manager.sync_notifications(
        unread_count=notification_service.get_unread_count(),
        recent=recent,
    )

    return {
        "status": "ok",
        "message": "Notification ingested and triaged",
        "notification": notif.to_dict(),
    }


@router.post("/read")
async def mark_notifications_read(req: MarkReadRequest) -> Dict[str, Any]:
    """Marks notifications as read."""
    updated = notification_service.mark_as_read(req.notification_ids)
    recent = [n.to_dict() for n in notification_service.get_recent_notifications(limit=5)]
    await sync_manager.sync_notifications(
        unread_count=notification_service.get_unread_count(),
        recent=recent,
    )
    return {
        "status": "ok",
        "marked_count": updated,
        "unread_count": notification_service.get_unread_count(),
    }


@router.post("/clear")
async def clear_notifications() -> Dict[str, Any]:
    """Clears all notifications."""
    notification_service.clear_all()
    await sync_manager.sync_notifications(unread_count=0, recent=[])
    return {
        "status": "ok",
        "message": "All notifications cleared",
        "unread_count": 0,
    }
