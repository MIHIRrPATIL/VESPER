"""VESPER Notification Backlog Batch Triage Tool.

Processes backlogs of notifications received while mobile companion was offline
or disconnected. Groups alerts by category, deterministically evaluates financial
and security items, applies temporal relevance and LLM triage to communication
backlogs, and stages actions into the ActionQueue with idempotent SHA256 IDs.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.agent.proactive.action_queue import StagedAction, action_queue
from backend.agent.proactive.advisory_idempotency import (
    advisory_registry,
    generate_debt_advisory_id,
    generate_financial_advisory_id,
    generate_general_advisory_id,
    generate_otp_advisory_id,
    generate_task_advisory_id,
)
from backend.agent.proactive.notification_evaluator import (
    FINANCIAL_ALLOWED_PACKAGES,
    SMS_PACKAGES,
    notification_evaluator,
)
from backend.sync.notification_service import MobileNotification, NotificationPriority

logger = logging.getLogger("vesper.agent.tools.notification_batch")


class BatchTriageItemResult(BaseModel):
    id: str
    category: str
    retained: bool
    reason: str
    staged_action_id: Optional[str] = None
    action_type: Optional[str] = None


class BatchTriageResult(BaseModel):
    total_received: int
    retained_count: int
    stale_or_ignored_count: int
    financial_count: int
    tasks_count: int
    items: List[BatchTriageItemResult] = Field(default_factory=list)
    catch_up_briefing: str


class NotificationBatchTool:
    """Triage engine and LLM tool for batch processing mobile notification backlogs."""

    def __init__(self) -> None:
        pass

    async def triage_batch(
        self,
        notifications: List[Dict[str, Any] | MobileNotification],
        device_id: str = "mobile_client",
        device_name: str = "Mobile Companion",
    ) -> BatchTriageResult:
        """Processes a backlog of notifications in batches grouped by category."""
        now = time.time()
        total = len(notifications)
        if total == 0:
            return BatchTriageResult(
                total_received=0,
                retained_count=0,
                stale_or_ignored_count=0,
                financial_count=0,
                tasks_count=0,
                catch_up_briefing="Sir, no backlog notifications were pending triage.",
            )

        logger.info(f"[NotificationBatchTool] Starting batch triage for {total} notifications from {device_name}")

        normalized_items: List[MobileNotification] = []
        for raw in notifications:
            if isinstance(raw, MobileNotification):
                notif = raw
            elif isinstance(raw, dict):
                notif = MobileNotification(
                    id=raw.get("id") or f"backlog_{int(time.time() * 1000)}",
                    device_id=raw.get("device_id") or device_id,
                    device_name=raw.get("device_name") or device_name,
                    package_name=raw.get("package_name") or "unknown",
                    app_name=raw.get("app_name") or "App",
                    title=raw.get("title") or "",
                    text=raw.get("text") or "",
                    subtext=raw.get("subtext") or "",
                    priority=raw.get("priority") or NotificationPriority.MEDIUM,
                    timestamp=raw.get("post_time") or raw.get("timestamp") or now,
                    raw_payload=raw,
                )
            else:
                continue

            # Normalize timestamp (handle ms epoch)
            ts = notif.timestamp
            if ts > 1e11:
                ts = ts / 1000.0
                notif.timestamp = ts
            normalized_items.append(notif)

        # Sort chronologically (oldest to newest)
        normalized_items.sort(key=lambda n: n.timestamp)

        item_results: List[BatchTriageItemResult] = []
        comm_candidates: List[Tuple[MobileNotification, float]] = []  # (notif, age_sec)
        financial_staged: List[Dict[str, Any]] = []
        tasks_staged: List[Dict[str, Any]] = []
        expired_otps = 0

        for notif in normalized_items:
            age_sec = max(0.0, now - notif.timestamp)

            # 1. Summary, Noise, Outgoing
            if notification_evaluator._is_summary_or_outgoing(notif):
                item_results.append(
                    BatchTriageItemResult(
                        id=notif.id,
                        category="NOISE",
                        retained=False,
                        reason="summary_or_outgoing",
                    )
                )
                continue

            # 2. Marketing / Promo / Ads
            if notification_evaluator._is_promotional_or_spam(notif):
                item_results.append(
                    BatchTriageItemResult(
                        id=notif.id,
                        category="PROMO",
                        retained=False,
                        reason="promotional_or_spam",
                    )
                )
                continue

            # 3. Casual Banter
            if notification_evaluator._is_casual_banter(notif.text):
                item_results.append(
                    BatchTriageItemResult(
                        id=notif.id,
                        category="CASUAL",
                        retained=False,
                        reason="casual_banter",
                    )
                )
                continue

            # 4. Financial SMS / UPI transactions
            fin_action = notification_evaluator._try_parse_financial(notif)
            if fin_action:
                staged = action_queue.stage_action(fin_action)
                is_dup = getattr(staged, "status", "") == "duplicate"
                item_results.append(
                    BatchTriageItemResult(
                        id=notif.id,
                        category="FINANCIAL",
                        retained=not is_dup,
                        reason="duplicate_action" if is_dup else "staged_transaction",
                        staged_action_id=staged.id,
                        action_type=staged.action,
                    )
                )
                if not is_dup:
                    financial_staged.append(staged.params)
                continue

            # 5. Peer Debt
            debt_action = notification_evaluator._try_parse_peer_debt(notif)
            if debt_action:
                staged = action_queue.stage_action(debt_action)
                is_dup = getattr(staged, "status", "") == "duplicate"
                item_results.append(
                    BatchTriageItemResult(
                        id=notif.id,
                        category="FINANCIAL_DEBT",
                        retained=not is_dup,
                        reason="duplicate_action" if is_dup else "staged_debt",
                        staged_action_id=staged.id,
                        action_type=staged.action,
                    )
                )
                if not is_dup:
                    financial_staged.append(staged.params)
                continue

            # 6. OTP Codes
            otp_match = notification_evaluator._try_extract_otp(notif)
            if otp_match:
                # If older than 10 minutes, OTP is dead
                if age_sec > 600.0:
                    expired_otps += 1
                    item_results.append(
                        BatchTriageItemResult(
                            id=notif.id,
                            category="SECURITY_OTP",
                            retained=False,
                            reason=f"expired_otp (age: {int(age_sec)}s > 600s)",
                        )
                    )
                else:
                    source = notification_evaluator._clean_source_name(notif)
                    action_id = generate_otp_advisory_id(otp_match, source, notif.timestamp)
                    staged_otp = StagedAction(
                        id=action_id,
                        domain="security",
                        action="display_otp",
                        params={"code": otp_match, "source": source, "title": notif.title},
                        verbatim_text=f"OTP: {otp_match} ({source})",
                        speech_prompt=f"Security code from {source}: {' '.join(list(otp_match))}.",
                        priority=NotificationPriority.URGENT,
                    )
                    staged = action_queue.stage_action(staged_otp)
                    is_dup = getattr(staged, "status", "") == "duplicate"
                    item_results.append(
                        BatchTriageItemResult(
                            id=notif.id,
                            category="SECURITY_OTP",
                            retained=not is_dup,
                            reason="active_otp",
                            staged_action_id=staged.id,
                            action_type=staged.action,
                        )
                    )
                continue

            # 7. Group messages where user isn't mentioned
            if notification_evaluator._is_group_notification(notif) and not notification_evaluator._mentions_user(notif.text):
                item_results.append(
                    BatchTriageItemResult(
                        id=notif.id,
                        category="GROUP_UNMENTIONED",
                        retained=False,
                        reason="group_message_not_addressed_to_user",
                    )
                )
                continue

            # 8. Communication candidates for LLM triage
            # If message is older than 24 hours, discard as stale unless URGENT
            if age_sec > 86400.0 and notif.priority != NotificationPriority.URGENT:
                item_results.append(
                    BatchTriageItemResult(
                        id=notif.id,
                        category="STALE_COMMUNICATION",
                        retained=False,
                        reason="stale_message (>24h old)",
                    )
                )
                continue

            comm_candidates.append((notif, age_sec))

        # LLM Triage for Communication Candidates
        llm_briefing_summary = ""
        if comm_candidates:
            triaged_tasks, llm_briefing_summary = await self._triage_communication_candidates(comm_candidates)
            for notif, task_info in triaged_tasks:
                if task_info.get("actionable"):
                    title = task_info.get("task", "")
                    action_id = generate_task_advisory_id(title, notif.title)
                    staged_task = StagedAction(
                        id=action_id,
                        domain="tasks",
                        action="create_task",
                        params={"title": title, "priority": "HIGH"},
                        verbatim_text=title,
                        speech_prompt=None,  # Do not speak out loud during batch triage
                        priority="HIGH",
                        raw_evidence={
                            "sender": notif.title,
                            "app": notif.app_name,
                            "message": notif.text,
                            "reason": task_info.get("reason", ""),
                        },
                    )
                    staged = action_queue.stage_action(staged_task)
                    is_dup = getattr(staged, "status", "") == "duplicate"
                    item_results.append(
                        BatchTriageItemResult(
                            id=notif.id,
                            category="COMMUNICATION",
                            retained=not is_dup,
                            reason="actionable_task",
                            staged_action_id=staged.id,
                            action_type=staged.action,
                        )
                    )
                    if not is_dup:
                        tasks_staged.append({"title": title, "sender": notif.title})
                else:
                    item_results.append(
                        BatchTriageItemResult(
                            id=notif.id,
                            category="COMMUNICATION",
                            retained=False,
                            reason=task_info.get("reason", "not_actionable"),
                        )
                    )

        retained_count = sum(1 for r in item_results if r.retained)
        stale_count = total - retained_count

        # Build Butler Catch-Up Briefing text
        briefing_parts = []
        if financial_staged:
            total_amt = sum(float(f.get("amount", 0.0)) for f in financial_staged)
            briefing_parts.append(
                f"{len(financial_staged)} financial transaction(s) totaling INR {total_amt:,.2f} were queued for ledger approval."
            )
        if tasks_staged:
            briefing_parts.append(
                f"{len(tasks_staged)} action item(s) were identified: {', '.join(t['title'] for t in tasks_staged[:3])}."
            )
        if expired_otps > 0:
            briefing_parts.append(f"{expired_otps} historical verification code(s) expired and were cleared.")
        if llm_briefing_summary:
            briefing_parts.append(llm_briefing_summary)

        if not briefing_parts:
            catch_up_briefing = (
                f"Sir, {total} offline alerts were inspected. All items were routine notifications or past offers; "
                f"no urgent actions are pending."
            )
        else:
            catch_up_briefing = (
                f"Sir, while your mobile device was offline, {total} notifications arrived. "
                + " ".join(briefing_parts)
            )

        logger.info(
            f"[NotificationBatchTool] Completed triage: {retained_count}/{total} retained, "
            f"{len(financial_staged)} transactions, {len(tasks_staged)} tasks."
        )

        return BatchTriageResult(
            total_received=total,
            retained_count=retained_count,
            stale_or_ignored_count=stale_count,
            financial_count=len(financial_staged),
            tasks_count=len(tasks_staged),
            items=item_results,
            catch_up_briefing=catch_up_briefing,
        )

    async def _triage_communication_candidates(
        self,
        candidates: List[Tuple[MobileNotification, float]],
    ) -> Tuple[List[Tuple[MobileNotification, Dict[str, Any]]], str]:
        """Uses LLM to evaluate temporal relevance and extract actionable items from communication batch."""
        if not candidates:
            return [], ""

        try:
            from backend.agent.llm import LLMClient

            llm = LLMClient()
            items_payload = []
            for idx, (notif, age_sec) in enumerate(candidates):
                age_min = int(age_sec / 60)
                age_str = f"{age_min} minutes ago" if age_min < 60 else f"{age_min // 60} hours ago"
                items_payload.append(
                    {
                        "item_index": idx,
                        "app": notif.app_name,
                        "sender": notif.title,
                        "message": notif.text,
                        "received_relative": age_str,
                    }
                )

            prompt = (
                f"You are Alfred, a discreet proactive AI butler triaging a backlog of messages received while the user was offline.\n"
                f"Messages backlog ({len(items_payload)} items):\n"
                f"{items_payload}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. For each item, evaluate if the message is STILL RELEVANT right now, and whether it contains a concrete, important action or request required of the user.\n"
                f"2. Suppress casual check-ins, simple greetings, low-priority chat, advertisements, or time-sensitive questions that have clearly lapsed.\n"
                f"3. Provide a brief 1-2 sentence consolidated catch-up executive summary.\n\n"
                f"Return JSON strictly adhering to schema:\n"
                f"{{\n"
                f'  "triage": [\n'
                f'    {{"item_index": 0, "actionable": true, "task": "Send deck to John", "reason": "Client presentation request"}},\n'
                f'    {{"item_index": 1, "actionable": false, "task": "", "reason": "Casual greeting"}}\n'
                f"  ],\n"
                f'  "executive_summary": "1-2 sentence executive summary of key news or catch-up items"\n'
                f"}}"
            )

            messages = [
                {"role": "system", "content": "You are a precise notification triage assistant. Always output valid json."},
                {"role": "user", "content": prompt},
            ]

            data, _ = await llm.generate_json(messages, temperature=0.1)
            triage_list = data.get("triage", []) if isinstance(data, dict) else []
            exec_summary = data.get("executive_summary", "") if isinstance(data, dict) else ""

            lookup: Dict[int, Dict[str, Any]] = {}
            for entry in triage_list:
                if isinstance(entry, dict) and "item_index" in entry:
                    lookup[int(entry["item_index"])] = entry

            results = []
            for idx, (notif, _) in enumerate(candidates):
                res = lookup.get(idx, {"actionable": False, "task": "", "reason": "not_triaged"})
                results.append((notif, res))

            return results, exec_summary

        except Exception as e:
            logger.warning(f"[NotificationBatchTool] LLM candidate triage failed: {e}")
            fallback_results = []
            for notif, _ in candidates:
                fallback_results.append((notif, {"actionable": False, "task": "", "reason": "llm_error"}))
            return fallback_results, ""


notification_batch_tool = NotificationBatchTool()


async def triage_notification_backlog_batch(
    notifications: List[Dict[str, Any] | MobileNotification],
    device_id: str = "mobile_client",
    device_name: str = "Mobile Companion",
) -> Dict[str, Any]:
    """Top-level functional interface for triage of notification batches."""
    res = await notification_batch_tool.triage_batch(
        notifications=notifications,
        device_id=device_id,
        device_name=device_name,
    )
    return res.model_dump()
