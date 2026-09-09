"""VESPER Proactive Executive Briefing Manager.

Provides immediate, pre-warmed executive briefings summarizing:
  1. Time, date, and contextual butler salutation (Alfred).
  2. Upcoming schedule & calendar obligations for today.
  3. High-priority tasks and staged action review items.
  4. Recent activity log (financial debits, system events, reminders).
  5. System health and ecosystem status.

Maintains an in-memory cache warmed on service boot for sub-millisecond
retrieval and instantaneous TTS synthesis. Strictly zero emojis.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.agent.proactive.action_queue import action_queue
from backend.agent.proactive.audit_logger import audit_logger
from backend.agent.proactive.system_sentry import system_sentry

logger = logging.getLogger("vesper.agent.proactive.briefing")

CACHE_TTL_SECONDS = 300.0  # 5 minutes cache lifetime


def _get_day_suffix(day: int) -> str:
    """Returns ordinal suffix for day of month (e.g., 1st, 2nd, 3rd, 4th)."""
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _get_time_of_day_salutation(hour: int) -> str:
    """Returns time-appropriate butler greeting."""
    if 5 <= hour < 12:
        return "Good morning, sir."
    elif 12 <= hour < 17:
        return "Good afternoon, sir."
    elif 17 <= hour < 22:
        return "Good evening, sir."
    else:
        return "Good evening, sir. A late hour to be at work."


class BriefingManager:
    """Orchestrates pre-fetching, formatting, and delivery of startup briefings."""

    _instance: Optional["BriefingManager"] = None

    def __init__(self) -> None:
        self._cached_briefing: Optional[Dict[str, Any]] = None
        self._cached_at: float = 0.0
        self._briefing_ready_event = asyncio.Event()
        self._warming_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "BriefingManager":
        if cls._instance is None:
            cls._instance = BriefingManager()
        return cls._instance

    # ── Cache Warming ─────────────────────────────────────────────────────────

    def warm_cache_background(self) -> None:
        """Kicks off asynchronous pre-fetch on service startup."""
        if self._warming_task and not self._warming_task.done():
            return
        self._briefing_ready_event.clear()
        self._warming_task = asyncio.create_task(self._warm_cache_worker())

    async def _warm_cache_worker(self) -> None:
        """Background worker that queries calendar, tasks, and audit logs."""
        try:
            t0 = time.time()
            briefing = await self._build_briefing_payload()
            async with self._lock:
                self._cached_briefing = briefing
                self._cached_at = time.time()
                self._briefing_ready_event.set()
            latency_ms = (time.time() - t0) * 1000.0
            logger.info(f"[BriefingManager] Startup briefing cache warmed in {latency_ms:.1f}ms")
        except Exception as e:
            logger.error(f"[BriefingManager] Failed to warm briefing cache: {e}", exc_info=True)
            # Create a minimal fallback briefing so clients are never blocked
            fallback = self._build_minimal_fallback_briefing()
            async with self._lock:
                self._cached_briefing = fallback
                self._cached_at = time.time()
                self._briefing_ready_event.set()

    async def get_briefing(self, timeout: float = 2.5, force_refresh: bool = False) -> Dict[str, Any]:
        """Returns the pre-cached briefing immediately (<1ms) or waits briefly if warming."""
        now = time.time()
        if not force_refresh and self._cached_briefing and (now - self._cached_at) < CACHE_TTL_SECONDS:
            return self._cached_briefing

        if force_refresh:
            self._briefing_ready_event.clear()
            self._warming_task = asyncio.create_task(self._warm_cache_worker())

        if not self._briefing_ready_event.is_set():
            if not self._warming_task or self._warming_task.done():
                self.warm_cache_background()
            try:
                await asyncio.wait_for(self._briefing_ready_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"[BriefingManager] Timeout waiting for warm cache ({timeout}s); generating immediate fallback.")
                return self._build_minimal_fallback_briefing()

        if self._cached_briefing:
            return self._cached_briefing

        return self._build_minimal_fallback_briefing()

    # ── Data Assembly & Formatting ───────────────────────────────────────────

    async def _build_briefing_payload(self) -> Dict[str, Any]:
        """Fetches all intelligence sources concurrently and formats response."""
        now = datetime.datetime.now()
        local_tz = now.astimezone().tzinfo
        now_tz = now.astimezone()
        hour = now.hour

        # 1. Concurrently query Calendar and Tasks
        calendar_task = asyncio.create_task(self._fetch_today_events(now_tz))
        tasks_task = asyncio.create_task(self._fetch_pending_tasks())

        events, tasks = await asyncio.gather(calendar_task, tasks_task, return_exceptions=True)
        if isinstance(events, Exception):
            logger.warning(f"[BriefingManager] Calendar fetch error: {events}")
            events = []
        if isinstance(tasks, Exception):
            logger.warning(f"[BriefingManager] Task fetch error: {tasks}")
            tasks = []

        # 2. Query Recent Activities from Audit Logger
        recent_audit = audit_logger.list_entries(limit=10)

        # 3. Query Staged Pending Actions
        staged_pending = action_queue.get_unreviewed_actions_for_return()

        # 4. Query System Health
        try:
            sys_health = system_sentry.evaluate_system_health()
        except Exception:
            sys_health = {"status": "NOMINAL", "cpu_percent": 0.0, "ram_percent": 0.0}

        # 5. Synthesize Articulate Butler Speech & Markdown
        speech, markdown_body, hud_card = self._compose_briefing(
            now=now,
            events=events,
            tasks=tasks,
            audit_entries=recent_audit,
            staged_pending=staged_pending,
            sys_health=sys_health,
        )

        title = f"Executive {'Morning' if hour < 12 else ('Afternoon' if hour < 17 else 'Evening')} Briefing"

        return {
            "title": title,
            "speech": speech,
            "markdown_body": markdown_body,
            "hud_cards": [hud_card],
            "events_count": len(events),
            "tasks_count": len(tasks),
            "staged_count": len(staged_pending),
            "cached_at": time.time(),
        }

    async def _fetch_today_events(self, now: datetime.datetime) -> List[Dict[str, Any]]:
        """Queries Google Calendar for events scheduled between now and end of today."""
        try:
            from backend.agent.tools.calendar_tool import GoogleCalendarTool

            cal = GoogleCalendarTool()
            if not cal.is_configured():
                return []

            end_of_day = datetime.datetime.combine(now.date(), datetime.time(23, 59, 59)).astimezone(now.tzinfo)
            # Add lookahead buffer (until tomorrow morning if late evening)
            if now.hour >= 20:
                end_of_day = (now + datetime.timedelta(hours=14)).astimezone(now.tzinfo)

            return await cal.list_upcoming_events(
                max_results=8,
                time_min=now,
                time_max=end_of_day,
            )
        except Exception as e:
            logger.warning(f"[BriefingManager] Calendar query error: {e}")
            return []

    async def _fetch_pending_tasks(self) -> List[Any]:
        """Queries Supabase for pending/undone user tasks."""
        try:
            from backend.data.repositories.tasks import TaskRepository

            repo = TaskRepository()
            return await asyncio.to_thread(repo.list, include_completed=False, limit=50)
        except Exception as e:
            logger.warning(f"[BriefingManager] Task repository unavailable: {e}")
            return []

    def _compose_briefing(
        self,
        now: datetime.datetime,
        events: List[Dict[str, Any]],
        tasks: List[Any],
        audit_entries: List[Any],
        staged_pending: List[Any],
        sys_health: Dict[str, Any],
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Formulates butler speech text, detailed markdown briefing, and HUD card with strict temporal awareness."""
        hour = now.hour
        salutation = _get_time_of_day_salutation(hour)
        day_name = now.strftime("%A")
        month_name = now.strftime("%B")
        day_num = now.day
        suffix = _get_day_suffix(day_num)
        time_str = now.strftime("%-I:%M %p") if hasattr(now, "strftime") else now.strftime("%I:%M %p").lstrip("0")

        local_tz = now.astimezone().tzinfo
        t_min = datetime.datetime.combine(now.date(), datetime.time.min).replace(tzinfo=local_tz)
        t_max = datetime.datetime.combine(now.date(), datetime.time.max).replace(tzinfo=local_tz)

        def _to_tz(dt_val: Any) -> Optional[datetime.datetime]:
            if not dt_val:
                return None
            if isinstance(dt_val, str):
                try:
                    dt_val = datetime.datetime.fromisoformat(dt_val)
                except Exception:
                    return None
            if isinstance(dt_val, datetime.date) and not isinstance(dt_val, datetime.datetime):
                dt_val = datetime.datetime.combine(dt_val, datetime.time.min)
            if isinstance(dt_val, datetime.datetime):
                if dt_val.tzinfo is None:
                    return dt_val.replace(tzinfo=local_tz)
                return dt_val.astimezone(local_tz)
            return None

        # Categorize tasks by temporal context
        today_tasks: List[Any] = []
        overdue_tasks: List[Tuple[Any, str]] = []  # (task, age_label)
        backlog_tasks: List[Any] = []

        for t in tasks:
            meta = getattr(t, "metadata", {}) or {}
            is_reminder = meta.get("item_type") == "reminder"
            deadline = _to_tz(getattr(t, "deadline", None))
            created = _to_tz(getattr(t, "created_at", None))

            if deadline is not None:
                if t_min <= deadline <= t_max:
                    today_tasks.append(t)
                elif deadline < t_min:
                    days_overdue = max(1, (t_min.date() - deadline.date()).days)
                    age_str = f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue"
                    overdue_tasks.append((t, age_str))
                else:
                    backlog_tasks.append(t)
            else:
                # No explicit deadline
                if created is not None and created < t_min:
                    # Created prior to today and still undone -> Overdue/past-due
                    days_ago = max(1, (t_min.date() - created.date()).days)
                    age_str = f"{days_ago} day{'s' if days_ago != 1 else ''} overdue"
                    if is_reminder:
                        age_str = f"Overdue reminder from {created.strftime('%b %-d') if hasattr(created, 'strftime') else created.strftime('%b %d')}"
                    overdue_tasks.append((t, age_str))
                elif created is not None and t_min <= created <= t_max:
                    # Created today
                    today_tasks.append(t)
                else:
                    # Default for new tasks without creation date in current session
                    today_tasks.append(t)

        # ── Speech Formulation ───────────────────────────────────────────────
        speech_parts: List[str] = []
        speech_parts.append(f"{salutation} It is {day_name}, {month_name} {day_num}{suffix}, {time_str}.")

        # Calendar Schedule synthesis
        if events:
            if len(events) == 1:
                ev = events[0]
                summary = ev.get("summary") or "Scheduled appointment"
                start = ev.get("start") or "today"
                speech_parts.append(f"You have one appointment on your calendar today: '{summary}' at {start}.")
            else:
                top_items = []
                for ev in events[:2]:
                    summary = ev.get("summary") or "Scheduled appointment"
                    start = ev.get("start") or ""
                    top_items.append(f"'{summary}' at {start}" if start else f"'{summary}'")
                remaining = len(events) - len(top_items)
                rem_phrase = f", along with {remaining} further obligation{'s' if remaining != 1 else ''}" if remaining > 0 else ""
                speech_parts.append(f"You have {len(events)} appointments scheduled today: {' and '.join(top_items)}{rem_phrase}.")
        else:
            speech_parts.append("Your calendar is completely clear for the remainder of today, sir.")

        # Staged Actions (VIP pending review)
        if staged_pending:
            s_count = len(staged_pending)
            speech_parts.append(
                f"You have {s_count} pending recommendation{'s' if s_count != 1 else ''} staged for your review."
            )

        # Tasks for Today vs Overdue from earlier
        if today_tasks:
            top_t = today_tasks[0]
            title = getattr(top_t, "title", "Scheduled task")
            speech_parts.append(f"For today's agenda, you have {len(today_tasks)} task{'s' if len(today_tasks) != 1 else ''} scheduled, beginning with '{title}'.")
        else:
            speech_parts.append("You have no tasks scheduled specifically for today, sir.")

        if overdue_tasks:
            top_ot, top_age = overdue_tasks[0]
            ot_title = getattr(top_ot, "title", "Pending matter")
            if len(overdue_tasks) == 1:
                speech_parts.append(f"However, regarding pending matters, you have 1 overdue item from earlier ({top_age}): '{ot_title}'.")
            else:
                speech_parts.append(f"However, regarding pending matters, you have {len(overdue_tasks)} overdue items from earlier, notably '{ot_title}' ({top_age}).")

        # Recent activity highlights (filter duplicate verbatim strings)
        distinct_recent: List[str] = []
        seen_texts: set[str] = set()
        for entry in audit_entries:
            text = getattr(entry, "verbatim_text", "").strip()
            if text and text not in seen_texts:
                seen_texts.add(text)
                distinct_recent.append(text)
            if len(distinct_recent) >= 2:
                break

        if distinct_recent:
            act_str = " and ".join(f"'{a}'" for a in distinct_recent)
            speech_parts.append(f"Recent system activity notes: {act_str}.")

        # System health note
        status = sys_health.get("status", "NOMINAL")
        if status == "NOMINAL":
            speech_parts.append("All VESPER services are initialized and operating nominally.")
        else:
            speech_parts.append("All VESPER services are online, though system load is elevated.")

        speech_parts.append("How may I be of service?")
        full_speech = " ".join(speech_parts)

        # ── Markdown Body Formulation ────────────────────────────────────────
        md_lines: List[str] = []
        md_lines.append(f"### Executive Intelligence Briefing")
        md_lines.append(f"**Date:** {day_name}, {month_name} {day_num}{suffix}, {now.year} | **Time:** {time_str}\n")

        # Calendar & Today's Schedule Section
        md_lines.append("#### Calendar & Agenda (Today)")
        if events:
            for ev in events:
                summary = ev.get("summary") or "Appointment"
                start = ev.get("start") or "Scheduled"
                loc = f" ({ev.get('location')})" if ev.get("location") else ""
                md_lines.append(f"- **{start}**: {summary}{loc}")
        else:
            md_lines.append("- *No scheduled calendar events for today.*")
        md_lines.append("")

        # Today's Tasks
        md_lines.append("#### Today's Tasks")
        if today_tasks:
            for t in today_tasks[:5]:
                prio = getattr(t, "priority", "normal").upper()
                prio_badge = f"[{prio}] " if prio != "NORMAL" else ""
                title = getattr(t, "title", "Task")
                md_lines.append(f"- {prio_badge}{title}")
        else:
            md_lines.append("- *No tasks scheduled for today.*")
        md_lines.append("")

        # Overdue Matters Section (Items not marked done from prior dates)
        if overdue_tasks:
            md_lines.append("#### Overdue Matters (Action Required)")
            for ot, age in overdue_tasks[:6]:
                prio = getattr(ot, "priority", "normal").upper()
                prio_badge = f"[{prio}] " if prio != "NORMAL" else ""
                title = getattr(ot, "title", "Task")
                md_lines.append(f"- [OVERDUE] {prio_badge}**{title}** *({age})*")
            if len(overdue_tasks) > 6:
                md_lines.append(f"- *...and {len(overdue_tasks) - 6} further overdue items.*")
            md_lines.append("")

        if backlog_tasks:
            md_lines.append("#### Upcoming Tasks (Future)")
            for bt in backlog_tasks[:4]:
                prio = getattr(bt, "priority", "normal").upper()
                prio_badge = f"[{prio}] " if prio != "NORMAL" else ""
                title = getattr(bt, "title", "Task")
                dl = _to_tz(getattr(bt, "deadline", None))
                due_str = f" *(due {dl.strftime('%b %d')})*" if dl else ""
                md_lines.append(f"- {prio_badge}{title}{due_str}")
            md_lines.append("")

        # Staged Review Section
        if staged_pending:
            md_lines.append("#### Staged Proactive Actions (Awaiting Confirmation)")
            for a in staged_pending:
                domain = getattr(a, "domain", "general").capitalize()
                verb = getattr(a, "verbatim_text", "")
                md_lines.append(f"- **{domain}**: {verb}")
            md_lines.append("")

        # Recent Activity Log Section
        md_lines.append("#### Recent Activities")
        if distinct_recent:
            for r in distinct_recent:
                md_lines.append(f"- {r}")
        else:
            md_lines.append("- *No recent logged activities.*")
        md_lines.append("")

        # System Status Section
        cpu = sys_health.get("cpu_percent", "--")
        ram = sys_health.get("ram_percent", "--")
        md_lines.append(f"**Status:** {status} | **CPU:** {cpu}% | **RAM:** {ram}%")

        full_markdown = "\n".join(md_lines)

        # ── HUD Card Formulation ─────────────────────────────────────────────
        hud_card: Dict[str, Any] = {
            "type": "briefing",
            "title": f"Briefing: {day_name}, {month_name} {day_num}{suffix}",
            "time": time_str,
            "events_count": len(events),
            "events": [
                {"summary": ev.get("summary", "Event"), "time": ev.get("start", "")}
                for ev in events[:4]
            ],
            "today_tasks_count": len(today_tasks),
            "overdue_tasks_count": len(overdue_tasks),
            "overdue_tasks": [
                {"title": getattr(ot, "title", "Task"), "age": age}
                for ot, age in overdue_tasks[:4]
            ],
            "tasks_count": len(tasks),
            "recent_activities": distinct_recent,
            "staged_count": len(staged_pending),
            "system_status": status,
        }

        return full_speech, full_markdown, hud_card

    def _build_minimal_fallback_briefing(self) -> Dict[str, Any]:
        """Provides an immediate fallback briefing (<1ms) based solely on local clock."""
        now = datetime.datetime.now()
        hour = now.hour
        salutation = _get_time_of_day_salutation(hour)
        day_name = now.strftime("%A")
        month_name = now.strftime("%B")
        day_num = now.day
        suffix = _get_day_suffix(day_num)
        time_str = now.strftime("%-I:%M %p") if hasattr(now, "strftime") else now.strftime("%I:%M %p").lstrip("0")

        speech = (
            f"{salutation} It is {day_name}, {month_name} {day_num}{suffix}, {time_str}. "
            f"All VESPER services are initialized and operating nominally. "
            f"How may I be of assistance?"
        )
        markdown = (
            f"### Executive Briefing\n"
            f"**Date:** {day_name}, {month_name} {day_num}{suffix}, {now.year} | **Time:** {time_str}\n\n"
            f"All core VESPER microservices are online and ready."
        )
        return {
            "title": "Executive Briefing",
            "speech": speech,
            "markdown_body": markdown,
            "hud_cards": [
                {
                    "type": "briefing",
                    "title": f"Briefing: {day_name}, {month_name} {day_num}{suffix}",
                    "time": time_str,
                    "events_count": 0,
                    "tasks_count": 0,
                    "system_status": "NOMINAL",
                }
            ],
            "events_count": 0,
            "tasks_count": 0,
            "staged_count": 0,
            "cached_at": time.time(),
        }


briefing_manager = BriefingManager.get_instance()
