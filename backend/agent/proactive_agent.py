"""VESPER Asynchronous Proactive Agent Orchestrator.

Central daemon managing proactive background intelligence:
  1. Dynamic Battery & Device Health:
     - Continuously polls device telemetry.
     - Adapts low-battery threshold based on imminent calendar obligations.
  2. Calendar & Agenda Sentinel:
     - 30-min and 15-min lookahead triggers.
     - Departure preparation alerts for physical destinations.
     - Media pausing for meetings and proactive resumption upon conclusion.
  3. System Sentry:
     - Periodic CPU/memory watchdog.
     - Protected process deny-list enforcement.
  4. Multi-Slot Notification Triage & Staged Queue:
     - High-speed deterministic regex triage for financial debits, peer splits, and VIP tasks.
     - Coalesced sender thread windowing (30s).
     - Structured JSON LLM triage fallback for ambiguous VIP alerts.
     - Multi-slot FIFO staged action queue requiring explicit confirmation or desk-return review.

Maintains 1800s British butler diction (Alfred) and strictly zero emojis.
"""
from __future__ import annotations
import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional, Set

from backend.agent.proactive.action_queue import ActionPriority, StagedAction, action_queue
from backend.agent.proactive.audit_logger import audit_logger
from backend.agent.proactive.calendar_sentry import calendar_sentry
from backend.agent.proactive.notification_evaluator import notification_evaluator
from backend.agent.proactive.system_sentry import system_sentry
from backend.sync.models import DeviceRegistration, SynchronizedState
from backend.sync.notification_service import (
    MobileNotification,
    NotificationPriority,
    notification_service,
)

logger = logging.getLogger("vesper.agent.proactive")

# ── Configuration Constants ──────────────────────────────────────────────────

DEFAULT_BATTERY_THRESHOLD = 30       # Default low-battery alert threshold (%)
ELEVATED_BATTERY_THRESHOLD = 50      # Raised when an event is within lookahead window
EVENT_LOOKAHEAD_MINUTES = 30         # Minutes to look ahead for calendar events
BATTERY_POLL_INTERVAL_SEC = 60       # Battery telemetry check cadence
CALENDAR_POLL_INTERVAL_SEC = 60      # Calendar agenda review cadence
SYSTEM_POLL_INTERVAL_SEC = 120       # System resource inspection cadence
REMINDER_COOLDOWN_SEC = 600          # 10 min cooldown per device before re-alerting

# VIP packages whose HIGH/URGENT notifications trigger LLM triage if regex doesn't match
VIP_PACKAGES: Set[str] = {
    "com.whatsapp",
    "org.telegram.messenger",
    "com.slack",
    "com.discord",
    "com.google.android.gm",
    "com.microsoft.office.outlook",
}


class ProactiveAgent:
    """Master orchestrator for anticipatory alerts, sentinels, and staged triage."""

    _instance: Optional["ProactiveAgent"] = None

    def __init__(self) -> None:
        self._battery_task: Optional[asyncio.Task] = None
        self._calendar_task: Optional[asyncio.Task] = None
        self._system_task: Optional[asyncio.Task] = None
        self._running = False

        # Device battery warning timestamps {device_id: last_warned_timestamp}
        self._battery_reminders: Dict[str, float] = {}

        # Gateway broadcast and direct session send callbacks
        self._broadcast_callback: Optional[Any] = None
        self._send_to_session_callback: Optional[Any] = None

        # Tracking for executive briefing deliveries
        self._delivered_briefings: Set[str] = set()
        self._briefing_delivery_times: Dict[str, float] = {}

        # Weather Sentry (initialized on start)
        self._weather_sentry = None

    @classmethod
    def get_instance(cls) -> "ProactiveAgent":
        if cls._instance is None:
            cls._instance = ProactiveAgent()
        return cls._instance

    def set_broadcast_callback(self, callback: Any) -> None:
        """Registers gateway broadcast function for emitting alerts and HUD cards."""
        self._broadcast_callback = callback
        action_queue.set_broadcast_callback(callback)

    def set_send_to_session_callback(self, callback: Any) -> None:
        """Registers gateway callback to send an envelope to a specific client session."""
        self._send_to_session_callback = callback

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts all proactive background sentinel loops and warms briefing cache."""
        if self._running:
            return
        self._running = True
        self._battery_task = asyncio.create_task(self._battery_monitor_loop())
        self._calendar_task = asyncio.create_task(self._calendar_monitor_loop())
        self._system_task = asyncio.create_task(self._system_monitor_loop())

        # Pre-warm executive briefing cache immediately for instantaneous TTS response
        try:
            from backend.agent.proactive.briefing_manager import briefing_manager
            briefing_manager.warm_cache_background()
        except Exception as e:
            logger.warning(f"[ProactiveAgent] Failed to warm briefing cache: {e}")

        try:
            from backend.agent.proactive.weather_sentry import init_weather_sentry
            self._weather_sentry = init_weather_sentry(
                callback=self._weather_broadcast,
                location="Palghar",
            )
            self._weather_sentry.start()
        except Exception as e:
            logger.warning(f"[ProactiveAgent] WeatherSentry failed to start: {e}")
        logger.info("[ProactiveAgent] Proactive sentinel swarm started.")

    async def stop(self) -> None:
        """Gracefully terminates all proactive sentinel loops."""
        self._running = False
        if self._weather_sentry:
            try:
                self._weather_sentry.stop()
            except Exception:
                pass
        tasks = [t for t in (self._battery_task, self._calendar_task, self._system_task) if t and not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("[ProactiveAgent] Proactive sentinel swarm stopped.")

    async def _weather_broadcast(self, event_type: str, payload: dict) -> None:
        """Routes weather sentry alerts to the Gateway broadcast."""
        speech = payload.get("speech", "")
        if speech and self._broadcast_callback:
            try:
                await self._broadcast_callback(
                    event_type="PROACTIVE_ALERT",
                    payload={
                        "alert_type": event_type,
                        "speech": speech,
                        "weather": payload.get("weather") or payload.get("result"),
                        "source": "weather_sentry",
                    },
                )
            except Exception as e:
                logger.warning(f"[ProactiveAgent] Weather broadcast failed: {e}")

    # ── 1. Battery Telemetry Monitoring ───────────────────────────────────────

    async def _battery_monitor_loop(self) -> None:
        await asyncio.sleep(5)  # Startup grace period for node registrations
        while self._running:
            try:
                await self._evaluate_all_device_batteries()
            except Exception as e:
                logger.error(f"[ProactiveAgent] Battery monitor error: {e}", exc_info=True)
            await asyncio.sleep(BATTERY_POLL_INTERVAL_SEC)

    async def _evaluate_all_device_batteries(self) -> None:
        from backend.sync.sync_manager import sync_manager

        now = time.time()
        # Monitor all registered devices with known battery telemetry from the last 4 hours
        all_devices = list(sync_manager.state.active_devices.values())
        devices = [
            d for d in all_devices
            if d.battery_level is not None and (now - getattr(d, "last_heartbeat", 0.0) < 14400.0)
        ]
        if not devices:
            return

        upcoming_events = await self._fetch_upcoming_events_safe()
        has_imminent_event = len(upcoming_events) > 0
        dynamic_threshold = ELEVATED_BATTERY_THRESHOLD if has_imminent_event else DEFAULT_BATTERY_THRESHOLD

        for dev in devices:

            if dev.is_charging:
                self._battery_reminders.pop(dev.device_id, None)
                continue

            last_warned = self._battery_reminders.get(dev.device_id, 0.0)
            if (now - last_warned) < REMINDER_COOLDOWN_SEC:
                continue

            if dev.battery_level is not None and dev.battery_level <= dynamic_threshold:
                await self._emit_battery_alert(dev, dynamic_threshold, upcoming_events)
                self._battery_reminders[dev.device_id] = now

    async def _emit_battery_alert(
        self,
        device: DeviceRegistration,
        threshold: int,
        upcoming_events: List[Dict[str, Any]],
    ) -> None:
        if upcoming_events:
            event_summary = upcoming_events[0].get("summary", "an upcoming commitment")
            event_start = upcoming_events[0].get("start", "shortly")
            speech = (
                f"Sir, {device.device_name}'s battery is at {device.battery_level}% and is not on charge. "
                f"You have '{event_summary}' approaching at {event_start}. "
                f"I advise placing your device on charge beforehand."
            )
        else:
            speech = (
                f"Sir, {device.device_name}'s battery has fallen to {device.battery_level}% and is not charging. "
                f"You may wish to replenish it soon."
            )

        logger.info(
            f"[ProactiveAgent] Battery advisory for '{device.device_name}' "
            f"({device.battery_level}% <= threshold {threshold}%)"
        )

        is_crit = device.battery_level is not None and device.battery_level <= 15
        bat_priority = NotificationPriority.URGENT if is_crit else NotificationPriority.HIGH

        notification_service.ingest_notification(
            payload={
                "package_name": "vesper.system.battery",
                "app_name": "Battery Sentry",
                "title": f"Low Battery: {device.device_name}",
                "text": speech,
                "priority": bat_priority,
            },
            source_device_id=device.device_id,
            source_device_name=device.device_name,
        )

        await self._broadcast_hud_voice(
            envelope_id=f"proactive_bat_{device.device_id}_{int(time.time())}",
            title=f"Low Battery: {device.device_name}",
            speech=speech,
            device_name=device.device_name,
            priority=bat_priority,
        )

    # ── 2. Calendar & Agenda Sentinel Loop ───────────────────────────────────

    async def _calendar_monitor_loop(self) -> None:
        await asyncio.sleep(10)
        while self._running:
            try:
                events = await self._fetch_upcoming_events_safe(max_results=5, lookahead_minutes=60)
                if events:
                    alerts = await calendar_sentry.evaluate_agenda(events)
                    for alert in alerts:
                        await self._broadcast_hud_voice(
                            envelope_id=f"proactive_cal_{alert['event_id']}_{int(time.time())}",
                            title=alert.get("title", "Calendar Alert"),
                            speech=alert.get("speech", ""),
                            device_name="VESPER Sentinel",
                            priority=NotificationPriority.HIGH,
                            extra_payload=alert,
                        )
            except Exception as e:
                logger.error(f"[ProactiveAgent] Calendar monitor error: {e}", exc_info=True)
            await asyncio.sleep(CALENDAR_POLL_INTERVAL_SEC)

    async def _fetch_upcoming_events_safe(
        self, max_results: int = 3, lookahead_minutes: int = EVENT_LOOKAHEAD_MINUTES
    ) -> List[Dict[str, Any]]:
        try:
            from backend.agent.tools.calendar_tool import GoogleCalendarTool

            cal = GoogleCalendarTool()
            if not cal.is_configured():
                return []

            now = datetime.datetime.now(datetime.timezone.utc)
            lookahead = now + datetime.timedelta(minutes=lookahead_minutes)
            return await cal.list_upcoming_events(
                max_results=max_results,
                time_min=now,
                time_max=lookahead,
            )
        except Exception as e:
            logger.warning(f"[ProactiveAgent] Calendar retrieval unavailable: {e}")
            return []

    # ── 3. System Sentry Loop ─────────────────────────────────────────────────

    async def _system_monitor_loop(self) -> None:
        await asyncio.sleep(15)
        while self._running:
            try:
                health = system_sentry.evaluate_system_health()
                if health.get("status") == "ELEVATED_LOAD":
                    proposals = health.get("proposals", [])
                    for p in proposals:
                        await self._broadcast_hud_voice(
                            envelope_id=f"proactive_sys_{int(time.time())}",
                            title="System Sentry: Elevated Load",
                            speech=p.speech_prompt,
                            device_name="Workstation Sentry",
                            priority=NotificationPriority.HIGH,
                            extra_payload={"staged_action": p.model_dump()},
                        )
            except Exception as e:
                logger.error(f"[ProactiveAgent] System monitor error: {e}", exc_info=True)
            await asyncio.sleep(SYSTEM_POLL_INTERVAL_SEC)

    # ── 4. Unified Notification Triage ───────────────────────────────────────

    async def evaluate_notification(self, notif: MobileNotification) -> None:
        """Called when any notification is received by the gateway.
        
        Evaluates deterministically via NotificationEvaluator (finances, debt, tasks),
        falling back to fast JSON LLM triage for ambiguous VIP communications.
        """
        # Tier 1: Fast deterministic evaluation (0ms, 0 tokens)
        eval_res = await notification_evaluator.evaluate(notif)
        if eval_res.handled:
            if eval_res.staged_action:
                staged = eval_res.staged_action
                logger.info(
                    f"[ProactiveAgent] Staged action [{staged.domain}:{staged.action}] "
                    f"for notification from {notif.app_name}"
                )
                await self._broadcast_staged_action_card(notif, staged)
            return

        # Tier 2: VIP LLM triage for ambiguous messages
        if notif.package_name.lower() in VIP_PACKAGES and notif.priority in (
            NotificationPriority.URGENT,
            NotificationPriority.HIGH,
        ):
            logger.info(
                f"[ProactiveAgent] Performing VIP LLM triage for {notif.app_name}: "
                f"'{notif.title}' - '{notif.text[:60]}'"
            )
            try:
                suggestion = await self._triage_with_llm(notif)
                if suggestion:
                    action_id = f"act_task_vip_{int(time.time())}_{notif.id}"
                    staged_task = action_queue.stage_action(
                        StagedAction(
                            id=action_id,
                            domain="tasks",
                            action="create_task",
                            params={"title": suggestion},
                            verbatim_text=suggestion,
                            speech_prompt=(
                                f"Sir, I noticed an important message from {notif.title} on {notif.app_name}. "
                                f"Shall I add a task: '{suggestion}'?"
                            ),
                            priority=ActionPriority.HIGH.value,
                            raw_evidence={
                                "package_name": notif.package_name,
                                "app_name": notif.app_name,
                                "title": notif.title,
                                "text": notif.text,
                            },
                        )
                    )
                    await self._broadcast_staged_action_card(notif, staged_task)
            except Exception as e:
                logger.warning(f"[ProactiveAgent] VIP LLM triage failed: {e}")

    async def _triage_with_llm(self, notif: MobileNotification) -> Optional[str]:
        """Uses a structured JSON LLM call to extract actionable tasks while suppressing banter."""
        try:
            from backend.agent.llm import LLMClient

            llm = LLMClient()
            prompt = (
                f"You are Alfred, a discreet 1800s British butler and AI assistant.\n"
                f"A notification arrived:\n"
                f"  App: {notif.app_name}\n"
                f"  Sender: {notif.title}\n"
                f"  Message: {notif.text}\n\n"
                f"Determine whether this message clearly requires a specific task or follow-up action. "
                f"Suppress casual personal banter, greetings, simple confirmations (e.g. 'ok', 'yes my love', 'relax'), "
                f"advertisements, promotional offers, expiring credits/points, or automated marketing chatter.\n\n"
                f"You MUST return a JSON object with this exact schema:\n"
                f"{{\n"
                f'  "actionable": true | false,\n'
                f'  "task": "Concise task description under 10 words" | "",\n'
                f'  "reason": "Brief justification"\n'
                f"}}"
            )

            messages = [
                {"role": "system", "content": "You are a precise task extraction assistant. You always respond in valid json."},
                {"role": "user", "content": prompt},
            ]

            result, _ = await llm.generate_json(messages, temperature=0.1)
            if isinstance(result, dict) and result.get("actionable"):
                task = str(result.get("task", "")).strip()
                if task and "no_action" not in task.lower():
                    return task
            return None

        except Exception as e:
            logger.warning(f"[ProactiveAgent] LLM triage invocation failed: {e}")
            if notif.priority == NotificationPriority.URGENT:
                return f"Review {notif.app_name} alert: {notif.title}"
            return None

    # ── 5. Broadcast Helpers ──────────────────────────────────────────────────

    async def _broadcast_staged_action_card(self, notif: MobileNotification, staged: StagedAction) -> None:
        """Emits an actionable card and voice prompt to HUD and mobile clients."""
        speech = staged.speech_prompt or (
            f"Sir, shall I execute: {staged.verbatim_text}?"
        )

        if self._broadcast_callback:
            try:
                from backend.shared.events import Channel, EventType, ServerEnvelope

                envelope = ServerEnvelope(
                    uuid=f"proactive_stage_{staged.id}_{int(time.time())}",
                    channel=Channel.NOTIFY,
                    type=EventType.NOTIFICATION_DIGEST,
                    payload={
                        "source_client": "proactive_agent",
                        "device_name": notif.device_name,
                        "notification": {
                            "app_name": f"Alfred - {staged.domain.title()}",
                            "title": f"Proposed Action: {staged.action}",
                            "text": speech,
                            "priority": NotificationPriority.HIGH,
                            "staged_action_id": staged.id,
                            "verbatim_text": staged.verbatim_text,
                        },
                        "is_update": False,
                        "is_ongoing": False,
                        "proactive": True,
                        "speech": speech,
                        "action_required": True,
                        "staged_action": staged.model_dump(),
                    },
                )
                await self._broadcast_callback(envelope)
            except Exception as e:
                logger.warning(f"[ProactiveAgent] Failed to broadcast staged action card: {e}")

    async def _broadcast_hud_voice(
        self,
        envelope_id: str,
        title: str,
        speech: str,
        device_name: str,
        priority: str = NotificationPriority.HIGH,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._broadcast_callback or not speech:
            return

        try:
            from backend.shared.events import Channel, EventType, ServerEnvelope

            payload: Dict[str, Any] = {
                "source_client": "proactive_agent",
                "device_name": device_name,
                "notification": {
                    "app_name": "Alfred Sentry",
                    "title": title,
                    "text": speech,
                    "priority": priority,
                },
                "is_update": False,
                "is_ongoing": False,
                "proactive": True,
                "speech": speech,
            }
            if extra_payload:
                payload.update(extra_payload)

            envelope = ServerEnvelope(
                uuid=envelope_id,
                channel=Channel.NOTIFY,
                type=EventType.NOTIFICATION_DIGEST,
                payload=payload,
            )
            await self._broadcast_callback(envelope)
        except Exception as e:
            logger.warning(f"[ProactiveAgent] Failed to broadcast alert: {e}")

    # ── 6. State Sync & Return-to-Desk Reconciliation ────────────────────────

    async def on_state_change(self, state: SynchronizedState, diff: Dict[str, Any]) -> None:
        """SyncManager state listener."""
        if "device_registered" in diff:
            dev_id = diff["device_registered"]
            dev = state.active_devices.get(dev_id)
            if dev and dev.battery_level is not None:
                await self._evaluate_single_device(dev)

        # Desk return detection: if desktop node transitions to active
        if "active_devices" in diff or "device_registered" in diff:
            await self._check_desk_return_review()

    async def _evaluate_single_device(self, dev: DeviceRegistration) -> None:
        if dev.battery_level is None or dev.is_charging:
            self._battery_reminders.pop(dev.device_id, None)
            return

        now = time.time()
        last_warned = self._battery_reminders.get(dev.device_id, 0.0)
        if (now - last_warned) < REMINDER_COOLDOWN_SEC:
            return

        upcoming_events = await self._fetch_upcoming_events_safe()
        has_imminent_event = len(upcoming_events) > 0
        dynamic_threshold = ELEVATED_BATTERY_THRESHOLD if has_imminent_event else DEFAULT_BATTERY_THRESHOLD

        if dev.battery_level <= dynamic_threshold:
            await self._emit_battery_alert(dev, dynamic_threshold, upcoming_events)
            self._battery_reminders[dev.device_id] = now

    async def _check_desk_return_review(self) -> None:
        """Surfaces pending unreviewed staged actions when the user returns to their desk."""
        now = time.time()
        last_time = getattr(self, "_last_desk_return_review_time", 0.0)
        cooldown = getattr(self, "_desk_return_cooldown_sec", 1800.0)
        if (now - last_time) < cooldown:
            return

        pending = action_queue.get_unreviewed_actions_for_return()
        if not pending:
            return

        # Mark all pending items so they do not trigger repeatedly on subsequent heartbeats
        for a in pending:
            a.status = "reviewed_at_desk"

        self._last_desk_return_review_time = now
        count = len(pending)
        speech = (
            f"Welcome back to your desk, sir. You have {count} pending matter{'s' if count != 1 else ''} "
            f"staged for your review while you were away."
        )
        logger.info(f"[ProactiveAgent] Desk return review triggered: {count} unreviewed actions pending")

        await self._broadcast_hud_voice(
            envelope_id=f"proactive_return_review_{int(time.time())}",
            title="Desk Return Briefing",
            speech=speech,
            device_name="VESPER Host",
            priority=NotificationPriority.HIGH,
            extra_payload={
                "type": "return_review_digest",
                "pending_count": count,
                "pending_actions": [a.model_dump() for a in pending],
            },
        )

    # ── 7. Query Interface ───────────────────────────────────────────────────

    def get_all_device_battery_status(self) -> List[Dict[str, Any]]:
        from backend.sync.sync_manager import sync_manager

        devices = sync_manager.get_active_devices()
        results = []
        for dev in devices:
            entry: Dict[str, Any] = {
                "device_id": dev.device_id,
                "device_name": dev.device_name,
                "device_type": dev.device_type,
                "is_online": dev.is_online,
            }
            if dev.battery_level is not None:
                entry["battery_level"] = dev.battery_level
                entry["is_charging"] = dev.is_charging
                last_warned = self._battery_reminders.get(dev.device_id)
                entry["last_alert_at"] = last_warned
                entry["alert_active"] = (
                    last_warned is not None and (time.time() - last_warned) < REMINDER_COOLDOWN_SEC
                )
            else:
                entry["battery_level"] = None
                entry["is_charging"] = None
                entry["alert_active"] = False
            results.append(entry)
        return results

    # ── 8. Executive Startup Briefing ────────────────────────────────────────

    async def deliver_startup_briefing(self, session_id: Optional[str] = None, force: bool = False) -> None:
        """Delivers the pre-cached executive briefing to a connected client or cluster.

        Enforces at least a 1-hour (3600s) cooldown between automatic startup briefings across process restarts.
        """
        import json
        from pathlib import Path

        now = time.time()
        cooldown_sec = 3600.0  # At least 1 hour between startup briefings
        state_file = getattr(self, "_state_file_path", Path("output/last_briefing_delivery.json"))

        if not force:
            last_delivered = getattr(self, "_last_briefing_time", 0.0)
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text())
                    file_last = float(data.get("last_delivered", 0.0))
                    last_delivered = max(last_delivered, file_last)
                except Exception:
                    pass
            self._last_briefing_time = last_delivered

            elapsed = now - last_delivered
            if elapsed < cooldown_sec:
                mins_left = int((cooldown_sec - elapsed) / 60)
                logger.info(
                    f"[ProactiveAgent] Skipping automatic startup briefing: delivered {int(elapsed / 60)}m ago "
                    f"({mins_left}m remaining until 1h cooldown expires)."
                )
                return

        from backend.agent.proactive.briefing_manager import briefing_manager

        briefing = await briefing_manager.get_briefing(timeout=2.5)
        speech = briefing.get("speech", "")
        title = briefing.get("title", "Executive Briefing")
        markdown_body = briefing.get("markdown_body", "")
        hud_cards = briefing.get("hud_cards", [])

        self._last_briefing_time = now
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps({"last_delivered": now, "title": title}))
        except Exception as e:
            logger.warning(f"[ProactiveAgent] Failed to persist briefing state: {e}")

        envelope_id = f"proactive_briefing_{int(now)}"
        extra_payload = {
            "type": "startup_briefing",
            "markdown_body": markdown_body,
            "hud_cards": hud_cards,
            "target_session_id": session_id,
        }

        # If a specific session is targeted and callback is available, send directly
        if session_id and self._send_to_session_callback:
            try:
                from backend.shared.events import Channel, EventType, ServerEnvelope
                payload: Dict[str, Any] = {
                    "source_client": "proactive_agent",
                    "device_name": "Alfred Executive",
                    "notification": {
                        "app_name": "Alfred Sentry",
                        "title": title,
                        "text": speech,
                        "priority": NotificationPriority.HIGH,
                    },
                    "is_update": False,
                    "is_ongoing": False,
                    "proactive": True,
                    "speech": speech,
                }
                payload.update(extra_payload)
                envelope = ServerEnvelope(
                    uuid=envelope_id,
                    channel=Channel.NOTIFY,
                    type=EventType.NOTIFICATION_DIGEST,
                    payload=payload,
                )
                await self._send_to_session_callback(session_id, envelope)
                logger.info(f"[ProactiveAgent] Delivered startup briefing directly to session '{session_id}'.")
                return
            except Exception as e:
                logger.warning(f"[ProactiveAgent] Failed to send briefing directly to '{session_id}', falling back to broadcast: {e}")

        # Fallback to general broadcast
        await self._broadcast_hud_voice(
            envelope_id=envelope_id,
            title=title,
            speech=speech,
            device_name="Alfred Executive",
            priority=NotificationPriority.HIGH,
            extra_payload=extra_payload,
        )
        logger.info("[ProactiveAgent] Broadcast startup briefing to cluster.")


# Global singleton
proactive_agent = ProactiveAgent.get_instance()
