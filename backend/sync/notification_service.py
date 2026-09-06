"""VESPER Centralized Notification Management & Triage Service.

Maintains an in-memory bounded ring buffer of ingested notifications from
mobile companions (Android, iOS) and edge nodes, evaluates alert urgency/priority,
and provides query interfaces for the Alfred Swarm and Desktop HUD.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("vesper.sync.notifications")


class NotificationPriority:
    URGENT = "URGENT"  # OTPs, server down, incoming phone call, emergency
    HIGH = "HIGH"      # Direct messaging (WhatsApp, Telegram, Slack, Discord)
    MEDIUM = "MEDIUM"  # Calendar alerts, personal emails (Gmail)
    LOW = "LOW"        # Promotions, media status, system updates


class MobileNotification(BaseModel):
    """Normalized mobile notification envelope."""
    id: str = Field(default_factory=lambda: f"notif_{uuid.uuid4().hex[:10]}")
    device_id: str
    device_name: str = "Mobile Device"
    package_name: str = "unknown"
    app_name: str = "App"
    title: str = ""
    text: str = ""
    subtext: Optional[str] = ""
    priority: str = NotificationPriority.MEDIUM
    timestamp: float = Field(default_factory=time.time)
    is_read: bool = False
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class NotificationService:
    """Manages notification ingestion, priority triage, and retrieval."""

    _instance: Optional["NotificationService"] = None

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._notifications: List[MobileNotification] = []

    @classmethod
    def get_instance(cls) -> "NotificationService":
        if cls._instance is None:
            cls._instance = NotificationService()
        return cls._instance

    @staticmethod
    def classify_priority(package_name: str, title: str, text: str) -> str:
        """Classifies incoming mobile alerts into 4 triage levels."""
        pkg = (package_name or "").lower()
        combined = f"{title or ''} {text or ''}".lower()

        # 1. Urgent (OTPs, Alarms, Incoming Calls, Server Outages)
        urgent_keywords = [
            "otp", "verification code", "security code", "auth code",
            "server down", "critical alert", "emergency", "incident", "pagerduty",
            "incoming call", "missed call"
        ]
        if any(kw in combined for kw in urgent_keywords):
            return NotificationPriority.URGENT

        # 2. High (Direct communication apps)
        high_packages = [
            "com.whatsapp", "org.telegram.messenger", "com.slack",
            "com.discord", "com.google.android.apps.messaging",
            "com.facebook.orca", "im.vector.app"
        ]
        if any(hp in pkg for hp in high_packages) or any(app in combined for app in ["whatsapp", "telegram", "slack", "discord"]):
            return NotificationPriority.HIGH

        # 3. Medium (Emails, Calendar appointments)
        medium_packages = [
            "com.google.android.gm", "com.google.android.calendar",
            "com.microsoft.office.outlook", "com.apple.mobilemail"
        ]
        if any(mp in pkg for mp in medium_packages) or any(term in combined for term in ["calendar", "meeting", "reminder", "appointment"]):
            return NotificationPriority.MEDIUM

        # 4. Low (Everything else: marketing, battery warnings, background sync)
        return NotificationPriority.LOW

    def ingest_notification(
        self,
        payload: Dict[str, Any],
        source_device_id: str,
        source_device_name: str = "Mobile Device",
    ) -> MobileNotification:
        """Ingests, triages, and stores a notification from a mobile companion."""
        pkg = payload.get("package_name") or payload.get("app") or "unknown"
        app = payload.get("app_name") or self._resolve_app_name(pkg)
        title = payload.get("title", "")
        text = payload.get("text", "")
        subtext = payload.get("subtext", "")

        # Priority classification
        explicit_prio = payload.get("priority")
        if explicit_prio and explicit_prio.upper() in (
            NotificationPriority.URGENT,
            NotificationPriority.HIGH,
            NotificationPriority.MEDIUM,
            NotificationPriority.LOW,
        ):
            prio = explicit_prio.upper()
        else:
            prio = self.classify_priority(pkg, title, text)

        notif = MobileNotification(
            device_id=source_device_id,
            device_name=source_device_name,
            package_name=pkg,
            app_name=app,
            title=title,
            text=text,
            subtext=subtext,
            priority=prio,
            timestamp=payload.get("post_time") or time.time(),
            raw_payload=payload,
        )

        self._notifications.insert(0, notif)
        if len(self._notifications) > self.max_history:
            self._notifications.pop()

        logger.info(
            f"[NotificationService] Ingested alert [{prio}] from {app} ({source_device_name}): "
            f"\"{title}\" - {text[:60]}"
        )
        return notif

    def get_recent_notifications(
        self,
        limit: int = 10,
        unread_only: bool = False,
        min_priority: Optional[str] = None,
        app_filter: Optional[str] = None,
    ) -> List[MobileNotification]:
        """Retrieves recent notifications with optional filtering."""
        results: List[MobileNotification] = []
        for n in self._notifications:
            if unread_only and n.is_read:
                continue
            if app_filter and app_filter.lower() not in n.app_name.lower() and app_filter.lower() not in n.package_name.lower():
                continue
            if min_priority:
                prio_order = [NotificationPriority.LOW, NotificationPriority.MEDIUM, NotificationPriority.HIGH, NotificationPriority.URGENT]
                try:
                    min_idx = prio_order.index(min_priority)
                    curr_idx = prio_order.index(n.priority)
                    if curr_idx < min_idx:
                        continue
                except ValueError:
                    pass
            results.append(n)
            if len(results) >= limit:
                break
        return results

    def mark_as_read(self, notification_ids: Optional[List[str]] = None) -> int:
        """Marks notifications as read. If IDs omitted, marks all as read."""
        count = 0
        target_ids = set(notification_ids) if notification_ids else None
        for n in self._notifications:
            if target_ids is None or n.id in target_ids:
                if not n.is_read:
                    n.is_read = True
                    count += 1
        return count

    def get_unread_count(self) -> int:
        return sum(1 for n in self._notifications if not n.is_read)

    def clear_all(self) -> None:
        self._notifications.clear()

    @staticmethod
    def _resolve_app_name(package_name: str) -> str:
        """Maps common Android/iOS package names to friendly names."""
        mapping = {
            "com.whatsapp": "WhatsApp",
            "org.telegram.messenger": "Telegram",
            "com.slack": "Slack",
            "com.discord": "Discord",
            "com.google.android.gm": "Gmail",
            "com.google.android.calendar": "Google Calendar",
            "com.spotify.music": "Spotify",
            "com.twitter.android": "X / Twitter",
            "com.instagram.android": "Instagram",
            "com.linkedin.android": "LinkedIn",
            "com.github.android": "GitHub",
        }
        return mapping.get(package_name.lower(), package_name.split(".")[-1].capitalize())


notification_service = NotificationService.get_instance()
