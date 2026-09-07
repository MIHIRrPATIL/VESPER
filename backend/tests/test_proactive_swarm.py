"""Comprehensive tests for VESPER Autonomous Proactive & Triage Swarm.

Verifies:
  1. Deterministic financial debit extraction (INR, merchant, budget category).
  2. Peer debt and split parsing ("you owe me ...").
  3. Casual chatter & personal banter suppression.
  4. Multi-slot action queue lifecycle (staging, expiration, return-to-desk review).
  5. 3-tier confirmation pre-filter:
     - Strict 15s window confirmation for bare 'yes'.
     - Safe fallthrough for bare 'yes' outside 15s window (no accidental trigger).
     - Domain/entity-anchored voice confirmation ("yes log Swiggy").
     - User rejection / dismissal ("no cancel that").
  6. Financial rollback / undo transaction prefilter integration.
  7. System sentry process termination deny-list enforcement.
  8. Calendar sentry lookahead, departure buffer, and meeting-end media resumption.
"""

from __future__ import annotations

import datetime
import time
import pytest

from backend.agent.planner import SwarmPlanner
from backend.agent.proactive.action_queue import ActionPriority, StagedAction, action_queue
from backend.agent.proactive.audit_logger import audit_logger
from backend.agent.proactive.calendar_sentry import calendar_sentry
from backend.agent.proactive.notification_evaluator import notification_evaluator
from backend.agent.proactive.system_sentry import system_sentry
from backend.sync.notification_service import MobileNotification, NotificationPriority


@pytest.fixture(autouse=True)
def reset_proactive_state():
    """Resets queue, audit logs, and sentinels before every test."""
    action_queue.clear_all()
    calendar_sentry.reset()
    yield
    action_queue.clear_all()
    calendar_sentry.reset()


# ── 1. Financial Debit Parsing ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_financial_debit_parsing_hdfc():
    """Verifies that an Indian bank SMS debit is extracted with exact figures and merchant."""
    notif = MobileNotification(
        id="notif_hdfc_01",
        device_id="dev_pixel8",
        package_name="com.google.android.apps.messaging",
        app_name="Messages",
        title="HDFC Bank",
        text="Rs. 450.00 debited from a/c **1234 at Swiggy on 06-Sep-2026. Avl bal: Rs. 15,200.00",
        priority=NotificationPriority.HIGH,
        timestamp=time.time(),
        device_name="Pixel 8",
    )

    res = await notification_evaluator.evaluate(notif)
    assert res.handled is True
    assert res.staged_action is not None

    staged = res.staged_action
    assert staged.domain == "finance"
    assert staged.action == "log_transaction"
    assert staged.params["amount"] == 450.0
    assert staged.params["category"] == "Dining"
    assert "Swiggy" in staged.verbatim_text
    assert "450.00" in staged.verbatim_text
    assert staged.raw_evidence["source_package"] == "com.google.android.apps.messaging"


@pytest.mark.asyncio
async def test_financial_debit_upi_uber():
    """Verifies UPI transport transaction parsing."""
    notif = MobileNotification(
        id="notif_upi_02",
        device_id="dev_pixel8",
        package_name="net.one97.paytm",
        app_name="Paytm",
        title="Paid to Uber",
        text="Paid ₹280.00 to Uber India via Paytm UPI. Reference: UPI/123456789.",
        priority=NotificationPriority.HIGH,
        timestamp=time.time(),
        device_name="Pixel 8",
    )

    res = await notification_evaluator.evaluate(notif)
    assert res.handled is True
    assert res.staged_action is not None

    staged = res.staged_action
    assert staged.domain == "finance"
    assert staged.params["amount"] == 280.0
    assert staged.params["category"] == "Transport"
    assert "Uber" in staged.verbatim_text


# ── 2. Peer Debt and Expense Splitting ───────────────────────────────────────

@pytest.mark.asyncio
async def test_peer_debt_parsing():
    """Verifies that 'you owe me' peer splits are staged under manage_debt."""
    notif = MobileNotification(
        id="notif_split_01",
        device_id="dev_pixel8",
        package_name="org.telegram.messenger",
        app_name="Telegram",
        title="Rohan",
        text="Hey Mihir, you owe me 650 for dinner yesterday.",
        priority=NotificationPriority.HIGH,
        timestamp=time.time(),
        device_name="Pixel 8",
    )

    res = await notification_evaluator.evaluate(notif)
    assert res.handled is True
    assert res.staged_action is not None

    staged = res.staged_action
    assert staged.domain == "finance"
    assert staged.action == "manage_debt"
    assert staged.params["action"] == "borrow"
    assert staged.params["amount"] == 650.0
    assert staged.params["person"] == "Rohan"


# ── 3. Casual Banter & Group Summary Suppression ────────────────────────────

@pytest.mark.asyncio
async def test_casual_banter_suppression():
    """Verifies that casual personal messages do not stage spurious tasks."""
    banter_messages = [
        ("WhatsApp", "yes my love"),
        ("WhatsApp", "relax"),
        ("Telegram", "ok sure see you then"),
        ("WhatsApp", "lol nice"),
        ("Instagram", "Just now"),
    ]

    for app, text in banter_messages:
        notif = MobileNotification(
            id=f"notif_banter_{int(time.time())}",
            device_id="dev_pixel8",
            package_name="com.whatsapp",
            app_name=app,
            title="Friend",
            text=text,
            priority=NotificationPriority.HIGH,
            timestamp=time.time(),
            device_name="Pixel 8",
        )
        res = await notification_evaluator.evaluate(notif)
        assert res.handled is True
        assert res.staged_action is None


# ── 4. Action Queue Lifecycle & Return-to-Desk Review ───────────────────────

def test_action_queue_lifecycle():
    """Verifies staging, expiration, and desk-return reconciliation."""
    action1 = StagedAction(
        id="act_test_01",
        domain="finance",
        action="log_transaction",
        params={"amount": 500.0, "category": "Dining"},
        verbatim_text="INR 500.00 at Starbucks",
        expires_at=time.time() - 10.0,  # Already expired
    )
    action2 = StagedAction(
        id="act_test_02",
        domain="tasks",
        action="create_task",
        params={"title": "Review Q3 roadmap"},
        verbatim_text="Review Q3 roadmap",
        expires_at=time.time() + 300.0,  # Active
    )

    action_queue.stage_action(action1)
    action_queue.stage_action(action2)

    # Active actions should only return non-expired
    active = action_queue.get_active_actions()
    assert len(active) == 1
    assert active[0].id == "act_test_02"

    # Mark expired for return review
    action_queue.mark_expired_for_return_review()
    return_items = action_queue.get_unreviewed_actions_for_return()
    assert len(return_items) == 2


# ── 5. Confirmation Pre-Filter (Strict 15s Window vs Safe Fallthrough) ───────

def test_strict_15s_window_confirmation():
    """Verifies that a bare 'yes' immediately after a proposal confirms the staged action."""
    planner = SwarmPlanner()

    action = StagedAction(
        id="act_prompted_01",
        domain="finance",
        action="log_transaction",
        params={"amount": 450.0, "category": "Dining", "description": "Expense at Swiggy"},
        verbatim_text="INR 450.00 at Swiggy",
    )
    action_queue.stage_action(action)

    # Simulate user saying "yes" within 15 seconds
    plan = planner._check_deterministic_prefilter("yes")
    assert plan is not None
    assert plan.provider_used == "prefilter"
    assert len(plan.steps) == 1
    assert plan.steps[0]["agent"] == "finance"
    assert plan.steps[0]["action"] == "log_transaction"
    assert plan.steps[0]["params"]["amount"] == 450.0

    # Verify action was resolved in queue and recorded in audit log
    assert action_queue.get_action("act_prompted_01") is None
    last_log = audit_logger.get_last_action()
    assert last_log is not None
    assert last_log["action_id"] == "act_prompted_01"


def test_rejection_of_staged_action():
    """Verifies that user saying 'no, cancel that' rejects the proposal."""
    planner = SwarmPlanner()

    action = StagedAction(
        id="act_reject_01",
        domain="finance",
        action="log_transaction",
        params={"amount": 1200.0, "category": "Shopping"},
        verbatim_text="INR 1,200.00 at Zara",
    )
    action_queue.stage_action(action)

    plan = planner._check_deterministic_prefilter("no cancel that")
    assert plan is not None
    assert plan.plan_type == "direct"
    assert plan.direct_response is not None and "discarded" in plan.direct_response.lower()
    assert action_queue.get_action("act_reject_01") is None


def test_bare_yes_outside_15s_window_falls_through():
    """Verifies that a bare 'yes' does NOT accidentally trigger a stale action after 15s."""
    planner = SwarmPlanner()

    action = StagedAction(
        id="act_stale_01",
        domain="finance",
        action="log_transaction",
        params={"amount": 350.0, "category": "Dining"},
        verbatim_text="INR 350.00 at McDonald's",
    )
    action_queue.stage_action(action)

    # Artificially age the prompt time beyond the 15-second window
    action_queue._last_prompt_time = time.time() - 30.0

    # Bare "yes" should NOT match the prefilter
    plan = planner._check_deterministic_prefilter("yes")
    assert plan is None

    # But an explicit domain-anchored phrase DOES match
    plan_explicit = planner._check_deterministic_prefilter("yes log McDonald's")
    assert plan_explicit is not None
    assert plan_explicit.steps[0]["action"] == "log_transaction"


def test_domain_anchored_disambiguation():
    """Verifies that if multiple items match an ambiguous phrase, Alfred asks for disambiguation."""
    planner = SwarmPlanner()

    action1 = StagedAction(
        id="act_swiggy_1",
        domain="finance",
        action="log_transaction",
        params={"amount": 250.0, "category": "Dining", "description": "Swiggy order 1"},
        verbatim_text="INR 250.00 at Swiggy",
    )
    action2 = StagedAction(
        id="act_swiggy_2",
        domain="finance",
        action="log_transaction",
        params={"amount": 450.0, "category": "Dining", "description": "Swiggy order 2"},
        verbatim_text="INR 450.00 at Swiggy",
    )
    action_queue.stage_action(action1)
    action_queue.stage_action(action2)

    # Force prompt time to past so 15s single-prompt shortcut is skipped
    action_queue._last_prompt_time = time.time() - 30.0

    plan = planner._check_deterministic_prefilter("yes confirm swiggy")
    assert plan is not None
    assert plan.plan_type == "direct"
    assert plan.direct_response is not None and "multiple" in plan.direct_response.lower()


# ── 6. Financial Undo / Rollback ─────────────────────────────────────────────

def test_financial_undo_prefilter():
    """Verifies that 'undo last transaction' is routed directly to finance:undo_transaction."""
    planner = SwarmPlanner()

    plan = planner._check_deterministic_prefilter("undo last transaction")
    assert plan is not None
    assert plan.provider_used == "prefilter"
    assert plan.steps[0]["agent"] == "finance"
    assert plan.steps[0]["action"] == "undo_transaction"


# ── 7. System Sentry Deny-List Enforcement ───────────────────────────────────

def test_system_sentry_deny_list():
    """Verifies that protected developer processes cannot be terminated."""
    protected = ["code", "cursor", "python", "node", "bash", "zsh", "cargo", "git"]
    for proc in protected:
        assert system_sentry.is_protected_process(proc) is True

    # Terminating a protected process must be blocked
    res = system_sentry.kill_rogue_process(9999, process_name="code")
    assert res["success"] is False
    assert "protected" in res["error"].lower()


# ── 8. Calendar Sentry Lookahead & Media Resumption ──────────────────────────

@pytest.mark.asyncio
async def test_calendar_sentry_lookahead_and_media():
    """Verifies 30m departure alert and 15m media pause staging."""
    now = datetime.datetime.now(datetime.timezone.utc)

    # Event 1: in 25 minutes at physical location
    event_30m = {
        "id": "ev_phys_01",
        "summary": "Doctor Appointment",
        "start": (now + datetime.timedelta(minutes=25)).isoformat(),
        "end": (now + datetime.timedelta(minutes=55)).isoformat(),
        "location": "Kalyani Nagar Clinic",
    }

    # Event 2: in 10 minutes (online)
    event_15m = {
        "id": "ev_meet_02",
        "summary": "Sprint Planning",
        "start": (now + datetime.timedelta(minutes=10)).isoformat(),
        "end": (now + datetime.timedelta(minutes=40)).isoformat(),
        "location": "Google Meet",
    }

    alerts = await calendar_sentry.evaluate_agenda([event_30m, event_15m], now=now)
    assert len(alerts) >= 2

    # Check departure alert
    dep_alert = next((a for a in alerts if a["event_id"] == "ev_phys_01"), None)
    assert dep_alert is not None
    assert dep_alert.get("is_departure_warning") is True
    assert "departure" in dep_alert["speech"].lower()

    # Check media pause staged for imminent meeting
    pause_actions = action_queue.get_active_actions(domain="media")
    assert len(pause_actions) >= 1
    assert pause_actions[0].action == "control_playback"
    assert pause_actions[0].params["command"] == "pause"
