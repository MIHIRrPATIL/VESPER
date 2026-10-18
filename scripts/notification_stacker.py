#!/usr/bin/env python3
"""VESPER Notification Stacking & Samsung Sensitive Data De-masking Engine.

Manages persistent offline stacking of uncleared and non-time-bound mobile
notifications (banking, financial transactions, OTPs, server alerts, calendar reminders)
and addresses Samsung One UI lock-screen masking of sensitive content.

Features:
1. Filters ephemeral/time-bound noise (download progress, music scrubbing, battery updates).
2. Retains high-priority persistent alerts (transactions, debit/credit alerts, OTPs, reminders).
3. Detects Samsung One UI lock-screen masking ("Content hidden", "1 new message", "****").
4. In-place de-masking when device unlock fires notification update.
5. Chronological synchronization with Gateway REST endpoints upon reconnection.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vesper.notification_stacker")

STACK_STORAGE_PATH = Path(os.getenv("VESPER_NOTIFICATION_STACK", "/home/mihir/.config/vesper/stacked_notifications.json"))
DEFAULT_GATEWAY_URL = os.getenv("VESPER_GATEWAY_URL", "http://192.168.0.200:8000")

# Samsung One UI masking indicators
SAMSUNG_MASK_PATTERNS = [
    re.compile(r"^\s*content\s+hidden\s*$", re.I),
    re.compile(r"^\s*hidden\s+content\s*$", re.I),
    re.compile(r"^\s*sensitive\s+content\s*$", re.I),
    re.compile(r"^\s*\d+\s+new\s+messages?\s*$", re.I),
    re.compile(r"^\s*new\s+message\s*$", re.I),
    re.compile(r"^\s*hidden\s+message\s*$", re.I),
    re.compile(r"^[*\u2022\s]{3,}$"),
]

FINANCIAL_KEYWORDS = [
    "debited", "credited", "spent", "paid", "sent to", "received from",
    "txn of", "transaction alert", "withdrawal", "balance alert", "upi ref",
    "account balance", "card blocked", "auto-debit", "autopay", "salary"
]

FINANCIAL_PACKAGES = [
    "com.google.android.apps.nbu.paisa.user",  # Google Pay
    "com.phonepe.app",                         # PhonePe
    "net.one97.paytm",                         # Paytm
    "com.samsung.android.spay",                # Samsung Wallet / Pay
    "com.samsung.android.spaymini",
    "com.hdfcbank.android",
    "com.csam.icici.bank.imobile",
    "com.sbi.lotusintouch",
    "com.axis.mobile",
    "com.msf.kbank.mobile",
    "com.cred.club",
]

OTP_KEYWORDS = [
    "otp", "verification code", "security code", "auth code", "one time password"
]

EPHEMERAL_KEYWORDS = [
    "downloading", "is running in background", "tap for info",
    "syncing in background", "percent complete"
]


def is_masked_text(text: Optional[str]) -> bool:
    """Detects whether a notification body is masked by Samsung Knox / One UI."""
    if not text:
        return True
    cleaned = text.strip()
    return any(pattern.match(cleaned) for pattern in SAMSUNG_MASK_PATTERNS)


def classify_notification(package_name: str, title: str, text: str) -> Tuple[str, str, bool]:
    """Classifies notification into (category, priority, is_time_bound).

    Returns:
        (category, priority, is_time_bound)
    """
    pkg = (package_name or "").lower()
    t = (title or "").lower()
    body = (text or "").lower()
    combined = f"{t} {body}"

    # 1. Ephemeral / Time-bound noise
    is_progress = bool(re.search(r"\b\d+%\b|\b\d+\s*(?:mb|kb|gb)\s*/", combined))
    if is_progress or any(ek in combined for ek in EPHEMERAL_KEYWORDS):
        return ("EPHEMERAL", "LOW", True)

    # 2. OTP / Two-Factor
    if any(ok in combined for ok in OTP_KEYWORDS):
        return ("URGENT", "URGENT", False)

    # 3. Financial / Banking
    if any(fk in combined for fk in FINANCIAL_KEYWORDS) or any(fp in pkg for fp in FINANCIAL_PACKAGES) or "bank" in pkg:
        return ("FINANCIAL", "HIGH", False)

    # 4. Direct Communication
    if any(app in pkg for app in ["whatsapp", "telegram", "slack", "discord", "messages"]):
        return ("DIRECT", "HIGH", False)

    # 5. General
    return ("GENERAL", "MEDIUM", False)


class NotificationStacker:
    """Persistent storage and de-masking queue for offline notifications."""

    def __init__(self, storage_path: Path = STACK_STORAGE_PATH) -> None:
        self.storage_path = storage_path
        self._ensure_storage_dir()
        self.items: List[Dict[str, Any]] = self._load()

    def _ensure_storage_dir(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Failed to load stacked notifications from {self.storage_path}: {e}")
            return []

    def _save(self) -> None:
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stacked notifications to {self.storage_path}: {e}")

    def stack(self, notification: Dict[str, Any]) -> Tuple[bool, str]:
        """Stacks an ingested notification. Performs in-place de-masking if applicable."""
        pkg = notification.get("package_name", "unknown")
        title = notification.get("title", "")
        text = notification.get("text", "")
        post_time = notification.get("post_time", time.time())

        category, priority, is_time_bound = classify_notification(pkg, title, text)
        masked = is_masked_text(text)

        # Do not stack ephemeral time-bound items (unless uncompleted)
        if is_time_bound:
            return False, "ignored_ephemeral"

        # Unique key based on package and title
        notif_key = f"{pkg}:{title}"

        # Check existing stack
        for existing in self.items:
            existing_key = f"{existing.get('package_name')}:{existing.get('title')}"
            if existing_key == notif_key:
                # Case A: Existing notification was masked, incoming is unmasked (screen unlocked)
                if existing.get("is_masked") and not masked:
                    logger.info(f"De-masking notification for '{title}' (Package: {pkg}): '{text}'")
                    existing["text"] = text
                    existing["subtext"] = notification.get("subtext") or existing.get("subtext")
                    existing["is_masked"] = False
                    existing["category"] = category
                    existing["priority"] = priority
                    existing["post_time"] = post_time
                    existing["demasked_at"] = time.time()
                    self._save()
                    return True, "demasked_updated"

                # Case B: Identical message within 60s
                if existing.get("text") == text and (time.time() - existing.get("post_time", 0) < 60):
                    return False, "duplicate_suppressed"

                # Case C: Financial alert with different transaction details -> keep both!
                if category == "FINANCIAL" and existing.get("text") != text:
                    break

        item = {
            "id": f"stacked_{int(time.time() * 1000)}_{len(self.items)}",
            "package_name": pkg,
            "app_name": notification.get("app_name", pkg),
            "title": title,
            "text": text,
            "subtext": notification.get("subtext", ""),
            "category": category,
            "priority": priority,
            "is_masked": masked,
            "is_time_bound": is_time_bound,
            "post_time": post_time,
            "device_id": notification.get("device_id", "mobile_client"),
            "device_name": notification.get("device_name", "Samsung Device"),
            "stacked_at": time.time(),
        }

        # Keep stack size bounded (up to 500 items), discarding oldest low-priority items first
        if len(self.items) >= 500:
            drop_idx = next(
                (i for i, x in enumerate(self.items) if x.get("category") not in ("FINANCIAL", "URGENT")),
                0
            )
            self.items.pop(drop_idx)

        self.items.append(item)
        self._save()
        logger.info(f"Stacked [{category} / {priority}] notification: '{title}' (Masked: {masked})")
        return True, "stacked_new"

    def list_stacked(self) -> List[Dict[str, Any]]:
        return list(self.items)

    def clear(self) -> int:
        count = len(self.items)
        self.items = []
        self._save()
        return count

    async def flush_to_gateway(self, gateway_url: str = DEFAULT_GATEWAY_URL) -> int:
        """Flushes stacked notifications to the Gateway /api/notifications/relay endpoint."""
        if not self.items:
            logger.info("Notification stack is empty. Nothing to flush.")
            return 0

        target_url = f"{gateway_url.rstrip('/')}/api/notifications/relay"
        logger.info(f"Flushing {len(self.items)} stacked notifications to {target_url}...")

        success_count = 0
        async with httpx.AsyncClient(timeout=6.0) as client:
            for item in list(self.items):
                try:
                    payload = {
                        "package_name": item["package_name"],
                        "app_name": item.get("app_name"),
                        "title": item["title"],
                        "text": item["text"],
                        "subtext": item.get("subtext"),
                        "priority": item.get("priority", "MEDIUM"),
                        "post_time": item.get("post_time"),
                        "device_id": item.get("device_id", "mobile_client"),
                        "device_name": item.get("device_name", "Samsung Device"),
                    }
                    res = await client.post(target_url, json=payload)
                    if res.status_code == 200:
                        success_count += 1
                        self.items.remove(item)
                    else:
                        logger.warning(f"Relay returned HTTP {res.status_code} for item '{item['title']}'")
                except Exception as e:
                    logger.warning(f"Connection failed during flush: {e}")
                    break

        self._save()
        logger.info(f"Flushed {success_count} notifications. Remaining in stack: {len(self.items)}")
        return success_count


def run_samsung_masking_simulation() -> None:
    """Demonstrates Samsung lockscreen masking followed by unlock de-masking."""
    stacker = NotificationStacker()
    print("--- 1. Simulating Samsung Lockscreen Sensitive Notification ---")
    masked_notif = {
        "package_name": "com.hdfcbank.android",
        "app_name": "HDFC Bank",
        "title": "HDFC Bank Alert",
        "text": "Content hidden",
        "subtext": "Banking",
        "device_name": "Galaxy S24",
    }
    stacked, status = stacker.stack(masked_notif)
    print(f"Status: {status} | Masked flag in stack: {stacker.items[-1]['is_masked']}")
    print(f"Stored Text: \"{stacker.items[-1]['text']}\"")

    print("\n--- 2. Simulating Device Screen Unlock (Updated Notification Event) ---")
    time.sleep(0.5)
    unmasked_notif = {
        "package_name": "com.hdfcbank.android",
        "app_name": "HDFC Bank",
        "title": "HDFC Bank Alert",
        "text": "Rs. 2,450.00 debited from A/C **4821 via UPI to ZOMATO on 09-OCT-26",
        "subtext": "Banking",
        "device_name": "Galaxy S24",
    }
    stacked, status = stacker.stack(unmasked_notif)
    print(f"Status: {status} | Masked flag in stack: {stacker.items[-1]['is_masked']}")
    print(f"Resolved Text: \"{stacker.items[-1]['text']}\"")
    print(f"Category: {stacker.items[-1]['category']} | Priority: {stacker.items[-1]['priority']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VESPER Notification Stacking & Samsung Sensitive Data Tool")
    parser.add_argument("--simulate", action="store_true", help="Run Samsung lockscreen masking simulation")
    parser.add_argument("--list", action="store_true", help="List currently stacked notifications")
    parser.add_argument("--flush", action="store_true", help="Flush stacked notifications to gateway")
    parser.add_argument("--clear", action="store_true", help="Clear local stack")
    parser.add_argument("--gateway", type=str, default=DEFAULT_GATEWAY_URL, help="Gateway URL")
    args = parser.parse_args()

    stacker = NotificationStacker()

    if args.simulate:
        run_samsung_masking_simulation()
    elif args.list:
        items = stacker.list_stacked()
        print(f"Stacked Notifications ({len(items)}):")
        for idx, it in enumerate(items, 1):
            dt = datetime.datetime.fromtimestamp(it.get("post_time", 0)).strftime("%H:%M:%S")
            print(f"{idx}. [{dt}] [{it.get('category')}] {it.get('title')}: {it.get('text')} (Masked: {it.get('is_masked')})")
    elif args.clear:
        count = stacker.clear()
        print(f"Cleared {count} stacked notifications.")
    elif args.flush:
        import asyncio
        asyncio.run(stacker.flush_to_gateway(args.gateway))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
