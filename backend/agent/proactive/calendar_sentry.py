"""VESPER Proactive Calendar Sentry.

Monitors Google Calendar for upcoming events, meetings, and focus blocks:
  - 30-minute lookahead: Alerts user, checks departure buffer if physical location.
  - 15-minute lookahead: Imminent alert, prepares media pause if music is playing.
  - Meeting conclusion: Detects when a meeting has concluded and offers to resume paused media.
  - Deep Work / Zen Mode: Recognizes focus blocks and advises quiet focus.

Maintains 1800s British butler diction (Alfred) and zero emojis.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional, Set

from backend.agent.proactive.action_queue import ActionPriority, StagedAction, action_queue
from backend.agent.proactive.audit_logger import audit_logger

logger = logging.getLogger("vesper.agent.proactive.calendar")


class CalendarSentry:
    """Proactive sentinel for calendar events, departures, and focus blocks."""

    def __init__(self) -> None:
        # Tracks (event_id, stage) to prevent repetitive alerting
        # stages: "30m", "15m", "zen_start", "concluded"
        self._notified_stages: Set[str] = set()
        # Tracks whether media was paused on behalf of an active meeting
        self._paused_for_meeting: Dict[str, bool] = {}

    def _get_stage_key(self, event_id: str, stage: str) -> str:
        return f"{event_id}:{stage}"

    def parse_event_time(self, time_val: Any) -> Optional[datetime.datetime]:
        """Parses various datetime representations returned by Google Calendar."""
        if not time_val:
            return None
        if isinstance(time_val, datetime.datetime):
            return time_val
        time_str = str(time_val).strip()

        # Try ISO format first
        try:
            # Handle trailing Z
            if time_str.endswith("Z"):
                time_str = time_str[:-1] + "+00:00"
            return datetime.datetime.fromisoformat(time_str)
        except Exception:
            pass

        # Try standard 12-hour time (e.g., '04:30 PM') assuming today
        try:
            now = datetime.datetime.now()
            t = datetime.datetime.strptime(time_str, "%I:%M %p").time()
            return datetime.datetime.combine(now.date(), t).astimezone()
        except Exception:
            pass

        return None

    async def evaluate_agenda(
        self,
        events: List[Dict[str, Any]],
        now: Optional[datetime.datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluates upcoming events against proactive horizons (30m, 15m, end-of-meeting).
        
        Returns a list of alert dictionaries suitable for HUD/voice dispatch.
        """
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        elif now.tzinfo is None:
            now = now.astimezone()

        if len(self._notified_stages) > 100:
            self._notified_stages.clear()

        alerts: List[Dict[str, Any]] = []

        for ev in events:
            ev_id = str(ev.get("id") or ev.get("summary") or "event")
            summary = ev.get("summary", "Scheduled appointment")
            location = ev.get("location", "").strip()

            start_dt = self.parse_event_time(ev.get("start"))
            end_dt = self.parse_event_time(ev.get("end"))

            if not start_dt:
                continue

            # Ensure start_dt and end_dt have timezone for comparison
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=now.tzinfo)
            if end_dt and end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=now.tzinfo)

            minutes_until_start = (start_dt - now).total_seconds() / 60.0

            # ── 1. 30-Minute Horizon ──────────────────────────────────────────
            key_30m = self._get_stage_key(ev_id, "30m")
            if 15.0 < minutes_until_start <= 32.0 and key_30m not in self._notified_stages:
                self._notified_stages.add(key_30m)
                
                is_physical = bool(
                    location
                    and not any(v in location.lower() for v in ["meet", "zoom", "teams", "http", "call", "online"])
                )

                if is_physical:
                    speech = (
                        f"Sir, your appointment '{summary}' commences in approximately 30 minutes at {location}. "
                        f"I recommend making departure preparations presently."
                    )
                else:
                    speech = (
                        f"Sir, you have '{summary}' scheduled in approximately 30 minutes. "
                        f"I have verified your upcoming obligations."
                    )

                alerts.append({
                    "event_id": ev_id,
                    "stage": "30m",
                    "title": f"Upcoming: {summary}",
                    "speech": speech,
                    "location": location,
                    "is_departure_warning": is_physical,
                })

            # ── 2. 15-Minute Horizon & Pre-Meeting Media Pause ────────────────
            key_15m = self._get_stage_key(ev_id, "15m")
            if 0.0 <= minutes_until_start <= 16.0 and key_15m not in self._notified_stages:
                self._notified_stages.add(key_15m)

                speech = f"Sir, '{summary}' begins in {max(1, int(minutes_until_start))} minutes."
                alerts.append({
                    "event_id": ev_id,
                    "stage": "15m",
                    "title": f"Imminent: {summary}",
                    "speech": speech,
                    "location": location,
                })

                # If music is playing or imminent, stage an action to pause media gracefully
                act_id = f"act_cal_pause_{int(time.time())}_{ev_id}"
                staged = action_queue.stage_action(
                    StagedAction(
                        id=act_id,
                        domain="media",
                        action="control_playback",
                        params={"command": "pause"},
                        verbatim_text=f"Pause workstation playback for '{summary}'",
                        speech_prompt=(
                            f"Sir, '{summary}' starts momentarily. Shall I pause media playback on your workstation?"
                        ),
                        priority=ActionPriority.HIGH.value,
                        raw_evidence={"event_id": ev_id, "summary": summary, "start": str(ev.get("start"))},
                    )
                )
                self._paused_for_meeting[ev_id] = True
                alerts[-1]["speech"] += " Shall I pause media playback on your workstation, sir?"
                alerts[-1]["staged_action"] = staged.model_dump()

            # ── 3. Focus / Zen Mode Block ─────────────────────────────────────
            is_focus_block = any(
                term in summary.lower()
                for term in ["focus", "deep work", "do not disturb", "zen mode", "coding block"]
            )
            key_zen = self._get_stage_key(ev_id, "zen_start")
            if is_focus_block and -5.0 <= minutes_until_start <= 2.0 and key_zen not in self._notified_stages:
                self._notified_stages.add(key_zen)
                speech = (
                    f"Sir, your focus session '{summary}' has commenced. "
                    f"I shall filter non-critical notifications to preserve your concentration."
                )
                alerts.append({
                    "event_id": ev_id,
                    "stage": "zen_start",
                    "title": f"Focus Block: {summary}",
                    "speech": speech,
                    "zen_mode": True,
                })

            # ── 4. Meeting Conclusion & Media Resumption ──────────────────────
            if end_dt:
                minutes_since_end = (now - end_dt).total_seconds() / 60.0
                key_end = self._get_stage_key(ev_id, "concluded")
                if 0.0 <= minutes_since_end <= 10.0 and key_end not in self._notified_stages:
                    self._notified_stages.add(key_end)

                    if self._paused_for_meeting.get(ev_id):
                        self._paused_for_meeting.pop(ev_id, None)
                        resumption_speech = (
                            f"Sir, '{summary}' has concluded. Would you care for me to resume your music playback?"
                        )
                        resumption_id = f"act_cal_resume_{int(time.time())}_{ev_id}"
                        action_queue.stage_action(
                            StagedAction(
                                id=resumption_id,
                                domain="media",
                                action="control_playback",
                                params={"command": "play"},
                                verbatim_text=f"Resume workstation playback after '{summary}'",
                                speech_prompt=resumption_speech,
                                priority=ActionPriority.MEDIUM.value,
                                raw_evidence={"event_id": ev_id, "summary": summary, "end": str(ev.get("end"))},
                            )
                        )
                        alerts.append({
                            "event_id": ev_id,
                            "stage": "concluded",
                            "title": f"Concluded: {summary}",
                            "speech": resumption_speech,
                            "resumption_offered": True,
                        })

        return alerts

    def reset(self) -> None:
        """Clears tracked alerts (useful for testing or day transitions)."""
        self._notified_stages.clear()
        self._paused_for_meeting.clear()


# Global singleton instance
calendar_sentry = CalendarSentry()
