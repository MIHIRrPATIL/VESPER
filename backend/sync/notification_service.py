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
    category: str = "GENERAL"  # "URGENT" | "DIRECT" | "FINANCIAL" | "PROMO" | "SYSTEM" | "GENERAL"
    is_promo: bool = False
    otp_code: Optional[str] = None
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
        if any(ik in combined for ik in incoming_keywords):
            return True, "INCOMING"

        ongoing_keywords = ["ongoing call", "call in progress", "active call", "on call"]
        if any(ok in combined for ok in ongoing_keywords):
            return True, "ACTIVE"

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

    @staticmethod
    def detect_category(package_name: str, title: str, text: str) -> tuple[str, bool, Optional[str]]:
        """Categorizes notification into (category, is_promo, otp_code).
        Categories: URGENT, DIRECT, FINANCIAL, PROMO, SYSTEM, GENERAL.
        """
        import re
        pkg = (package_name or "").lower()
        t = (title or "").strip()
        body = (text or "").strip()
        combined = f"{t} {body}".lower()

        # 1. Check for OTP / Security verification code
        otp_code: Optional[str] = None
        cleaned_no_amounts = re.sub(r"(?:rs\.?|inr|₹|\$)\s*[\d,]+(?:\.\d+)?", "", combined, flags=re.I)
        otp_match = re.search(r"\b(?:otp|secret code|verification code|security code)\b.*?\b(\d{4,8})\b", cleaned_no_amounts, re.IGNORECASE)
        if not otp_match:
            otp_match = re.search(r"\b(?:code|pin|verification)\b[^\w\d]*(?:is\s+)?(\d{4,8})\b", cleaned_no_amounts, re.IGNORECASE)
        if not otp_match:
            otp_match = re.search(r"\b(\d{4,8})\b.*?\b(?:is your (?:otp|verification|secret code)|for your account)\b", cleaned_no_amounts, re.IGNORECASE)
        if otp_match:
            otp_code = otp_match.group(1)

        if otp_code:
            return "URGENT", False, otp_code

        # 2. Urgent (Calls, Outages, Fraud, Security)
        urgent_keywords = [
            "incoming call", "missed call", "emergency", "incident", "pagerduty",
            "server down", "card blocked", "fraud alert", "account locked", "unauthorized", "sos"
        ]
        if any(kw in combined for kw in urgent_keywords):
            return "URGENT", False, None

        # 3. Check for Promotional / Marketing
        promo_tokens = [
            "offer", "discount", "coupon", "promo", "flat ", "save extra", "sale",
            "shop now", "order now", "buy now", "cashback offer", "free delivery",
            "win up to", "congratulations", "voucher", "points will expire", "credits will expire",
            "hurry", "limited period deal", "apply now for loan", "exclusive deal", "special price"
        ]
        is_ad_header = bool(re.match(r"^(?:AD|DM|TM|QP|XY|BA|BW)-", t, re.IGNORECASE))
        has_promo_link = bool(re.search(r"\b(?:1kx\.in|bit\.ly|tinyurl|myntr\.it|fkrt\.it)/", combined))
        has_promo_pct = bool(re.search(r"\b\d+%\s*(?:off|discount|cashback)\b", combined))

        if (is_ad_header or has_promo_link or has_promo_pct or any(pt in combined for pt in promo_tokens)) and not any(
            bk in combined for bk in ["debited", "credited", "spent", "received", "autopay", "auto-debit", "sip", "emi", "salary"]
        ):
            return "PROMO", True, None

        # 4. Financial / Transactions (Debits, Credits, Autopay, SIP, UPI, Bank SMS)
        financial_keywords = [
            "debited", "credited", "spent", "paid", "sent", "transferred", "txn of",
            "purchase of", "deducted", "autopay", "auto-debit", "auto debit", "sip",
            "emi", "withdrawn", "payment of", "received", "refund", "salary",
            "cashback credited", "deposited", "standing instruction", "upi ref", "vpa",
            "balance alert", "bank alert", "a/c balance"
        ]
        is_financial_pkg = any(b in pkg for b in ["bank", "hdfc", "sbi", "icici", "axis", "kotak", "paytm", "phonepe", "gpay", "cred"])
        if any(fk in combined for fk in financial_keywords) or is_financial_pkg:
            return "FINANCIAL", False, None

        # 5. Direct Personal Messaging & Telephony
        direct_packages = [
            "com.whatsapp", "org.telegram.messenger", "com.slack",
            "com.discord", "com.google.android.apps.messaging",
            "com.facebook.orca", "im.vector.app", "com.samsung.android.messaging",
            "com.android.mms", "com.android.messaging", "org.thoughtcrime.securesms"
        ]
        if any(dp in pkg for dp in direct_packages) or any(app in combined for app in ["whatsapp", "telegram", "slack", "discord", "signal"]):
            return "DIRECT", False, None

        # 6. System / Tools
        if any(sp in pkg for sp in ["android", "system", "download", "battery", "settings", "bluetooth"]):
            return "SYSTEM", False, None

        return "GENERAL", False, None

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

            # Detect category, promotional status, and OTP
            cat, is_pr, otp_c = self.detect_category(pkg, title, text)

            # UPDATE IN PLACE (OS Notification Shade behavior)
            existing.text = text
            existing.subtext = subtext
            existing.timestamp = payload.get("post_time") or now
            existing.is_in_place_update = True
            existing.is_call = is_call
            existing.call_phase = call_phase
            existing.category = cat
            existing.is_promo = is_pr
            existing.otp_code = otp_c
            if otp_c:
                existing.priority = NotificationPriority.URGENT
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
        cat, is_pr, otp_c = self.detect_category(pkg, title, text)

        explicit_prio = payload.get("priority")
        if explicit_prio and explicit_prio.upper() in (
            NotificationPriority.URGENT,
            NotificationPriority.HIGH,
            NotificationPriority.MEDIUM,
            NotificationPriority.LOW,
        ):
            prio = explicit_prio.upper()
        elif otp_c:
            prio = NotificationPriority.URGENT
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
            category=cat,
            is_promo=is_pr,
            otp_code=otp_c,
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

    def search_notifications(
        self,
        query: Optional[str] = None,
        sender_filter: Optional[str] = None,
        app_filter: Optional[str] = None,
        limit: int = 10,
    ) -> List[MobileNotification]:
        """Searches recent notifications by text content, sender/contact name, or app."""
        results: List[MobileNotification] = []
        q_clean = (query or "").lower().strip()
        sender_clean = (sender_filter or "").lower().strip()
        app_clean = (app_filter or "").lower().strip()

        for n in self._notifications:
            # 1. App filter check
            if app_clean:
                if app_clean not in n.app_name.lower() and app_clean not in n.package_name.lower():
                    continue

            # 2. Sender filter check (searches title and text)
            if sender_clean:
                title_lower = (n.title or "").lower()
                text_lower = (n.text or "").lower()
                if sender_clean not in title_lower and sender_clean not in text_lower:
                    continue

            # 3. Content query check
            if q_clean:
                combined_text = f"{n.title} {n.text} {n.subtext or ''}".lower()
                if q_clean not in combined_text:
                    q_words = [w for w in q_clean.split() if len(w) > 3]
                    if not q_words or not any(w in combined_text for w in q_words):
                        continue

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
            "com.google.android.apps.messaging": "Messages",
            "com.samsung.android.messaging": "Messages",
            "com.android.mms": "Messages",
            "com.android.messaging": "Messages",
            "org.thoughtcrime.securesms": "Signal",
            "com.google.android.apps.nbu.paisa.user": "Google Pay",
            "com.phonepe.app": "PhonePe",
            "net.one97.paytm": "Paytm",
            "com.dreamplug.androidapp": "CRED",
            "com.snapwork.hdfc": "HDFC Bank",
            "com.csam.icici.bank.imobile": "ICICI Bank",
            "com.sbi.lotusintouch": "SBI Yono",
            "com.axis.mobile": "Axis Bank",
            "com.msf.kbank.mobile": "Kotak Bank",
            "com.google.android.dialer": "Phone",
            "com.samsung.android.incallui": "Phone",
            "com.android.dialer": "Phone",
        }
        low = package_name.lower()
        if low in mapping:
            return mapping[low]
        # Check partial keywords
        if "bank" in low or "hdfc" in low or "icici" in low or "sbi" in low or "axis" in low or "kotak" in low:
            return "Banking"
        if "whatsapp" in low:
            return "WhatsApp"
        if "telegram" in low:
            return "Telegram"
        if "slack" in low:
            return "Slack"
        return package_name.split(".")[-1].capitalize()


notification_service = NotificationService.get_instance()

