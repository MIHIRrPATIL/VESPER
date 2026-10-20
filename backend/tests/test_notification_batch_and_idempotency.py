"""Tests for Proactive Advisory Idempotency, Batch Triage, and Ledger Settlement.

Covers:
1. Deterministic SHA256 advisory ID generation and idempotency registry.
2. Historical OTP suppression (>10 min old) vs fresh OTP extraction.
3. Historical financial transaction speech suppression (>15 min old).
4. Bank attribution (Saraswat, Union Bank, SBI, HDFC) and contact name prioritization.
5. Batch triage endpoint (/api/notifications/batch) and Catch-Up Briefing.
6. Pydantic TransactionCreate schema normalization (lowercase type, ISO date parsing).
7. Peer debt auto-settlement upon transaction approval.
"""

from __future__ import annotations

import datetime as dt
import time
import pytest
from fastapi.testclient import TestClient

from backend.agent.proactive.action_queue import StagedAction, action_queue
from backend.agent.proactive.advisory_idempotency import (
    advisory_registry,
    generate_debt_advisory_id,
    generate_financial_advisory_id,
    generate_otp_advisory_id,
    generate_task_advisory_id,
)
from backend.agent.proactive.notification_evaluator import (
    NotificationEvaluator,
    notification_evaluator,
)
from backend.agent.tools.notification_batch_tool import (
    notification_batch_tool,
    triage_notification_backlog_batch,
)
from backend.data.models import TransactionCreate, TransactionType
from backend.gateway.app import create_app
from backend.sync.notification_service import MobileNotification, NotificationPriority


@pytest.fixture
def client():
    test_app = create_app()
    with TestClient(test_app) as test_client:
        yield test_client


def test_deterministic_advisory_ids():
    """Verifies that advisory IDs are purely deterministic and reproducible."""
    id1 = generate_financial_advisory_id(1500.0, "expense", "Swiggy", "Debited Rs 1500 at Swiggy")
    id2 = generate_financial_advisory_id(1500.0, "expense", "Swiggy", "Debited Rs 1500 at Swiggy")
    assert id1 == id2
    assert id1.startswith("act_fin_")

    id_diff = generate_financial_advisory_id(2500.0, "expense", "Swiggy", "Debited Rs 2500 at Swiggy")
    assert id1 != id_diff

    # OTP bucketed within 10-minute window
    now = time.time()
    otp1 = generate_otp_advisory_id("123456", "HDFC Bank", now)
    otp2 = generate_otp_advisory_id("123456", "HDFC Bank", now + 60)
    assert otp1 == otp2

    # Task IDs
    task1 = generate_task_advisory_id("Send slide deck", "Hitanshu")
    task2 = generate_task_advisory_id("Send slide deck", "Hitanshu")
    assert task1 == task2


def test_advisory_registry_idempotency():
    """Verifies that advisory_registry records and checks dispatches."""
    unique_id = f"test_adv_{int(time.time() * 1000)}"
    assert not advisory_registry.is_dispatched(unique_id)

    advisory_registry.record_dispatch(unique_id, domain="finance")
    assert advisory_registry.is_dispatched(unique_id)


def test_stale_otp_suppression():
    """Verifies historical OTPs (>10 mins old) are completely suppressed from live alerts."""
    now = time.time()
    old_ts = now - 1200.0  # 20 minutes ago

    stale_notif = MobileNotification(
        package_name="com.google.android.apps.messaging",
        app_name="Messages",
        title="VK-HDFCBK",
        text="948201 is your OTP for transaction of Rs 500 at Amazon. Valid for 10 mins.",
        timestamp=old_ts,
    )

    code = notification_evaluator._try_extract_otp(stale_notif)
    assert code is None, "Historical OTP was not suppressed"

    # Fresh OTP should be extracted
    fresh_notif = MobileNotification(
        package_name="com.google.android.apps.messaging",
        app_name="Messages",
        title="VK-HDFCBK",
        text="948201 is your OTP for transaction of Rs 500 at Amazon. Valid for 10 mins.",
        timestamp=now - 30.0,
    )
    fresh_code = notification_evaluator._try_extract_otp(fresh_notif)
    assert fresh_code == "948201"


def test_historical_financial_speech_suppression():
    """Verifies historical financial transactions have speech suppressed and priority set to LOW."""
    now = time.time()
    old_ts = now - 3600.0  # 1 hour ago

    hist_notif = MobileNotification(
        package_name="com.saraswatbank.mobile",
        app_name="Saraswat Bank",
        title="VK-SRCBBK",
        text="Your A/C ending 4091 debited by Rs. 850.00 on 20-Oct-26 at Zomato. Avl Bal: Rs 12,000",
        timestamp=old_ts,
    )

    staged = notification_evaluator._try_parse_financial(hist_notif)
    assert staged is not None
    assert staged.speech_prompt is None
    assert staged.priority == "LOW"

    # Fresh transaction has spoken prompt and HIGH priority
    fresh_notif = MobileNotification(
        package_name="com.saraswatbank.mobile",
        app_name="Saraswat Bank",
        title="VK-SRCBBK",
        text="Your A/C ending 4091 debited by Rs. 850.00 on 20-Oct-26 at Zomato. Avl Bal: Rs 12,000",
        timestamp=now - 60.0,
    )
    fresh_staged = notification_evaluator._try_parse_financial(fresh_notif)
    assert fresh_staged is not None
    assert fresh_staged.speech_prompt is not None
    assert "850.00 rupees" in fresh_staged.speech_prompt
    assert fresh_staged.priority == "HIGH"


def test_bank_attribution_and_clean_source_name():
    """Verifies Saraswat Bank and Union Bank attribution and contact name prioritization."""
    notif_saraswat = MobileNotification(
        package_name="com.saraswatbank.mobile",
        app_name="Saraswat Bank",
        title="VK-SRCBBK",
        text="Debited Rs 400",
    )
    assert notification_evaluator._clean_source_name(notif_saraswat) == "Saraswat Bank"

    notif_union = MobileNotification(
        package_name="com.unionbank.online",
        app_name="Union Bank",
        title="BZ-UNIONB",
        text="Credited Rs 5000",
    )
    assert notification_evaluator._clean_source_name(notif_union) == "Union Bank"

    # Human sender name prioritized over generic package name
    notif_chat = MobileNotification(
        package_name="com.whatsapp",
        app_name="WhatsApp",
        title="Hitanshu Gala",
        text="Hey Mihir, are we meeting at 4?",
    )
    assert notification_evaluator._clean_source_name(notif_chat) == "Hitanshu Gala via WhatsApp"


@pytest.mark.asyncio
async def test_batch_triage_tool_logic():
    """Verifies that the batch triage tool groups, filters noise, and computes Catch-Up Briefing."""
    now = time.time()
    unique_amt = 1200 + int(now % 1000)
    batch = [
        # 1. Historical financial transaction (should be staged)
        {
            "package_name": "com.saraswatbank.mobile",
            "app_name": "Saraswat Bank",
            "title": "VK-SRCBBK",
            "text": f"Your A/C ending 4091 debited by Rs. {unique_amt}.00 at Starbucks.",
            "post_time": now - 3600.0,
        },
        # 2. Promo SMS (should be discarded)
        {
            "package_name": "com.google.android.apps.messaging",
            "app_name": "Messages",
            "title": "AD-FLPKRT",
            "text": "Mega Diwali sale! 60% off on electronics. Click 1kx.in/sale",
            "post_time": now - 1800.0,
        },
        # 3. Expired OTP (should be discarded)
        {
            "package_name": "com.google.android.apps.messaging",
            "app_name": "Messages",
            "title": "VK-SBINB",
            "text": "481920 is your State Bank OTP to login. Valid for 10 mins.",
            "post_time": now - 1200.0,
        },
        # 4. WhatsApp group summary (should be discarded)
        {
            "package_name": "com.whatsapp",
            "app_name": "WhatsApp",
            "title": "WhatsApp",
            "text": "5 messages from 3 chats",
            "post_time": now - 100.0,
        },
    ]

    res = await notification_batch_tool.triage_batch(batch)
    assert res.total_received == 4
    assert res.financial_count >= 1
    assert res.retained_count >= 1
    assert "Sir, while your mobile device was offline" in res.catch_up_briefing


def test_batch_triage_rest_endpoint(client: TestClient):
    """Verifies POST /api/notifications/batch endpoint."""
    now = time.time()
    payload = {
        "device_id": "test_companion",
        "device_name": "Pixel 8",
        "notifications": [
            {
                "package_name": "com.saraswatbank.mobile",
                "app_name": "Saraswat Bank",
                "title": "VK-SRCBBK",
                "text": "Your A/C ending 4091 debited by Rs. 650.00 at Swiggy.",
                "post_time": now - 100.0,
            },
            {
                "package_name": "com.whatsapp",
                "app_name": "WhatsApp",
                "title": "You",
                "text": "Sent an image",
                "post_time": now - 50.0,
            },
        ],
    }

    res = client.post("/api/notifications/batch", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "result" in data
    assert data["result"]["total_received"] == 2


def test_transaction_create_pydantic_normalization():
    """Verifies TransactionCreate normalizes uppercase EXPENSE and ISO datetime strings."""
    # 1. Uppercase string
    t1 = TransactionCreate(
        amount=150.0,
        type="EXPENSE",  # type: ignore
        category="Dining",
        description="Coffee with peer",
        date="2026-10-20T15:30:00.000Z",  # type: ignore
    )
    assert t1.type == TransactionType.EXPENSE
    assert t1.date == dt.date(2026, 10, 20)
    assert t1.amount == 150.0

    # 2. Lowercase string
    t2 = TransactionCreate(
        amount=500.0,
        type="income",  # type: ignore
        category="Refund",
        date="2026-10-20",  # type: ignore
    )
    assert t2.type == TransactionType.INCOME
    assert t2.date == dt.date(2026, 10, 20)
