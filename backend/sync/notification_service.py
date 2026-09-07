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
    is_ongoing: bool = False
    is_in_place_update: bool = False
    is_call: bool = False
    call_phase: Optional[str] = None  # "INCOMING" | "ENDED" | "ONGOING"
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class NotificationService:
    """Manages notification ingestion, priority triage, in-place grouping, and retrieval."""

    _instance: Optional["NotificationService"] = None

    IGNORED_SYSTEM_PACKAGES = {
        "android",
        "com.android.systemui",
        "com.google.android.gms",
        "com.google.android.googlequicksearchbox",
        "com.samsung.android.bixby.wakeup",
        "com.vesper.companion",
        "host.exp.exponent",
    }

    SILENCED_ONGOING_PACKAGES = {
        "com.noisefit",
        "com.fitbit",
        "com.huami.watch",
        "com.garmin.android.apps.connectmobile",
        "com.samsung.android.app.watchmanager",
        "com.google.android.apps.fitness",
        "com.sec.android.app.shealth",
    }

    def __init__(self, max_history: int = 100, dedup_window_seconds: float = 60.0) -> None:
        self.max_history = max_history
        self.dedup_window_seconds = dedup_window_seconds
        self._notifications: List[MobileNotification] = []
        self._active_notifications: Dict[str, MobileNotification] = {}
        self._recent_hashes: Dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> "NotificationService":
        if cls._instance is None:
            cls._instance = NotificationService()
        return cls._instance

    @staticmethod
    def detect_call_event(package_name: str, title: str, text: str) -> tuple[bool, Optional[str]]:
        """Detects whether a notification corresponds to an active or ended call."""
        pkg = (package_name or "").lower()
        combined = f"{title or ''} {text or ''}".lower()

        telephony_packages = [
            "com.samsung.android.incallui",
            "com.samsung.android.app.telephonyui",
            "com.google.android.dialer",
            "com.android.server.telecom",
            "com.android.phone",
            "com.android.dialer",
        ]
        is_telephony_pkg = any(tp in pkg for tp in telephony_packages)

        ended_keywords = [
            "missed call", "call ended", "call declined", "call finished",
            "call disconnected", "call rejected", "missed video call", "missed voice call"
        ]
        if any(ek in combined for ek in ended_keywords):
            return True, "ENDED"

        incoming_keywords = [
            "incoming call", "incoming video call", "incoming voice call",
            "call from", "calling...", "is calling", "ringing",
            "incoming audio call", "whatsapp call", "slack call", "telegram call"
        ]
        if is_telephony_pkg or any(ik in combined for ik in incoming_keywords):
            return True, "INCOMING"

        return False, None

    @staticmethod
    def classify_priority(package_name: str, title: str, text: str) -> str:
        """Classifies incoming mobile alerts into 4 triage levels."""
        pkg = (package_name or "").lower()
        combined = f"{title or ''} {text or ''}".lower()

        telephony_packages = [
            "com.samsung.android.incallui",
            "com.samsung.android.app.telephonyui",
            "com.google.android.dialer",
            "com.android.server.telecom",
            "com.android.phone",
            "com.android.dialer",
        ]
        if any(tp in pkg for tp in telephony_packages):
            return NotificationPriority.URGENT

        # 1. Urgent (OTPs, Alarms, Incoming Calls, Server Outages, Fraud Alerts)
        urgent_keywords = [
            "otp", "verification code", "security code", "auth code",
            "server down", "critical alert", "emergency", "incident", "pagerduty",
            "incoming call", "missed call", "fraud alert", "unauthorized",
            "card blocked", "account locked", "suspicious transaction"
        ]
        if any(kw in combined for kw in urgent_keywords):
            return NotificationPriority.URGENT

        # 2. High (Direct communication apps, SMS, Banking & Payment Alerts)
        high_packages = [
            "com.whatsapp", "org.telegram.messenger", "com.slack",
            "com.discord", "com.google.android.apps.messaging",
            "com.facebook.orca", "im.vector.app", "com.samsung.android.incallui",
            "com.samsung.android.messaging", "com.android.mms", "com.android.messaging",
            "com.google.android.apps.nbu.paisa.user", "com.phonepe.app", "net.one97.paytm"
        ]
        financial_keywords = [
            "debited", "credited", "bank", "payment of", "sent to", "received from",
            "transaction alert", "wire transfer", "upi transaction", "withdrawal", "balance alert"
        ]
        is_high_app = any(hp in pkg for hp in high_packages) or any(app in combined for app in ["whatsapp", "telegram", "slack", "discord", "paytm", "gpay", "phonepe"])
        is_financial = any(fk in combined for fk in financial_keywords) or any(b in pkg for b in ["bank", "hdfc", "sbi", "icici", "axis", "kotak"])
        if is_high_app or is_financial:
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
        allow_duplicate: bool = False,
    ) -> Optional[MobileNotification]:
        """Ingests, triages, deduplicates, and groups notifications like the OS shade."""
        import re

        pkg = (payload.get("package_name") or payload.get("app") or "unknown").strip()
        title = (payload.get("title") or "").strip()
        text = (payload.get("text") or "").strip()
        subtext = (payload.get("subtext") or "").strip()
        app = payload.get("app_name") or self._resolve_app_name(pkg)

        # 1. Filter empty/blank alerts
        if not title and not text:
            return None

        # 2. Filter Android system noise
        if pkg.lower() in self.IGNORED_SYSTEM_PACKAGES or pkg.lower().startswith("com.android.internal"):
            return None

        # 3. Filter Android summary notifications (e.g. '2 more notifications', '30 messages from 9 chats')
        if "more notifications" in title.lower() or "more notifications" in text.lower():
            return None
        if re.search(r'\b\d+\s+messages?\s+from\s+\d+\s+chats?\b', text, re.IGNORECASE) or \
           re.search(r'\b\d+\s+new\s+messages?\b', text, re.IGNORECASE):
            return None

        # 3b. Filter user's own outgoing synced messages (e.g. WhatsApp 'You: message')
        if title.lower() in ("you", "me"):
            return None

        # 3c. Filter standalone status ticks
        if text.lower() in ("just now", "now", "online"):
            return None

        # 4. Filter or silence persistent foreground service keep-alives (e.g. "NoiseFit is running")
        is_persistent_running = (
            "is running" in text.lower() or
            "is running" in title.lower() or
            "running in background" in text.lower() or
            "running in the background" in text.lower() or
            "tap for info" in text.lower() or
            "touch for more information" in text.lower() or
            "syncing in background" in text.lower()
        )
        is_known_tracker = pkg.lower() in self.SILENCED_ONGOING_PACKAGES

        if is_persistent_running and is_known_tracker:
            logger.debug(f"[NotificationService] Filtered background sync keep-alive from {pkg}: \"{title}\"")
            return None

        # 5. Clean up stale hashes and prepare timestamp
        now = time.time()
        self._recent_hashes = {
            k: ts for k, ts in self._recent_hashes.items() if (now - ts) < 300.0
        }

        # 6. Check for progress bar updates (e.g. Chrome file downloads)
        is_progress = bool(
            re.search(r'\d+(\.\d+)?\s*(MB|KB|GB|B|%)\s*/', text, re.IGNORECASE) or
            ("downloading" in text.lower()) or
            re.search(r'\d+%\s*•', text)
        )
        is_complete = bool(
            "complete" in text.lower() or
            "finished" in text.lower() or
            "download complete" in title.lower()
        )

        # 7. Detect call events (Ringing / Incoming vs Ended / Missed)
        is_call, call_phase = self.detect_call_event(pkg, title, text)
        if payload.get("is_call") is not None:
            is_call = bool(payload.get("is_call"))
        if payload.get("call_phase"):
            call_phase = str(payload.get("call_phase")).upper()

        # 8. Generate OS-style Notification Identity Key
        notif_id = str(payload.get("notification_id") or payload.get("id") or "").strip()
        if notif_id and notif_id != "0":
            key = f"{source_device_id}:{pkg.lower()}:{notif_id}"
        else:
            # Group by device, app package, and title (conversations, downloads, alerts)
            key = f"{source_device_id}:{pkg.lower()}:{title.lower()}"

        # 9. Check if this notification already exists in the active notification panel
        if key in self._active_notifications:
            existing = self._active_notifications[key]

            # If the text is identical and within dedup window, suppress redundant event
            if existing.text == text and not allow_duplicate:
                return None

            # UPDATE IN PLACE (OS Notification Shade behavior)
            existing.text = text
            existing.subtext = subtext
            existing.timestamp = payload.get("post_time") or now
            existing.is_in_place_update = True
            existing.is_call = is_call
            existing.call_phase = call_phase
            existing.raw_payload = payload

            # Move to top of active list
            if existing in self._notifications:
                self._notifications.remove(existing)
            self._notifications.insert(0, existing)

            if is_complete:
                logger.info(
                    f"[NotificationService] Completed alert from {app} ({source_device_name}): "
                    f"\"{title}\" - {text[:60]}"
                )
            elif is_progress or is_persistent_running:
                logger.debug(
                    f"[NotificationService] In-place progress update for {pkg}: \"{title}\" - {text[:40]}"
                )
            else:
                logger.info(
                    f"[NotificationService] Updated active alert [{existing.priority}] from {app} ({source_device_name}): "
                    f"\"{title}\" - {text[:60]}"
                )
            return existing

        # 10. Brand New Notification: Classify Priority & Register
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
            timestamp=payload.get("post_time") or now,
            is_ongoing=is_persistent_running,
            is_in_place_update=False,
            is_call=is_call,
            call_phase=call_phase,
            raw_payload=payload,
        )

        self._active_notifications[key] = notif
        self._notifications.insert(0, notif)

        # Evict oldest if exceeding max history
        if len(self._notifications) > self.max_history:
            evicted = self._notifications.pop()
            # Remove from active map if present
            evicted_key = None
            for k, v in self._active_notifications.items():
                if v.id == evicted.id:
                    evicted_key = k
                    break
            if evicted_key:
                self._active_notifications.pop(evicted_key, None)

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

    def get_grouped_notifications(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns active notifications grouped by application like the OS notification panel."""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for n in self._notifications:
            app_key = n.app_name or self._resolve_app_name(n.package_name)
            if app_key not in grouped:
                grouped[app_key] = []
            grouped[app_key].append(n.to_dict())
        return grouped

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
        self._active_notifications.clear()
        self._recent_hashes.clear()

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
            "com.android.chrome": "Chrome",
            "com.sec.android.app.sbrowser": "Samsung Internet",
            "in.swiggy.android": "Swiggy",
            "com.application.zomato": "Zomato",
        }
        return mapping.get(package_name.lower(), package_name.split(".")[-1].capitalize())


notification_service = NotificationService.get_instance()

