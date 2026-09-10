"""VESPER Proactive Staged Action Queue Manager.

Maintains a prioritized FIFO queue of staged proactive recommendations awaiting
human verification. Ensures actions are never silently overwritten, provides
time-to-live (TTL) management, and reconciles unreviewed items for the
desk-return briefing.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import os
import sys
logger = logging.getLogger("vesper.agent.proactive.queue")


class ActionPriority(str, Enum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class StagedAction(BaseModel):
    """Represents an autonomous recommendation staged for user verification."""

    id: str
    domain: str  # "finance", "tasks", "email", "system", "media", "github"
    action: str  # Tool name, e.g., "log_transaction", "add_task", "send_email"
    params: Dict[str, Any]
    verbatim_text: str  # Exact text/figures to read back without paraphrasing
    raw_evidence: Dict[str, Any] = Field(default_factory=dict)
    speech_prompt: str = ""
    status: str = "staged"  # "staged", "confirmed", "rejected", "expired", "pending_return"
    priority: str = "HIGH"  # "URGENT", "HIGH", "MEDIUM"
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 180.0)  # 3 min default
    requires_explicit_phrase: bool = True  # Enforces domain/entity token in voice confirmation
    rollback_data: Optional[Dict[str, Any]] = None


class ActionQueueManager:
    """Manages the lifecycle of staged proactive actions across the cluster."""

    _instance: Optional["ActionQueueManager"] = None

    def __init__(self, max_capacity: int = 20) -> None:
        self._max_capacity = max_capacity
        self._queue: Dict[str, StagedAction] = {}
        self._last_prompted_action_id: Optional[str] = None
        self._last_prompt_time: float = 0.0
        self._history: List[StagedAction] = []
        self._broadcast_callback: Optional[Any] = None

    @classmethod
    def get_instance(cls) -> "ActionQueueManager":
        if cls._instance is None:
            cls._instance = ActionQueueManager()
        return cls._instance

    def set_broadcast_callback(self, callback: Any) -> None:
        self._broadcast_callback = callback

    def stage_action(self, action: StagedAction) -> StagedAction:
        """Adds a newly formulated recommendation to the staged queue."""
        # Evict oldest expired items if queue exceeds capacity
        if len(self._queue) >= self._max_capacity:
            oldest_id = min(self._queue.keys(), key=lambda k: self._queue[k].created_at)
            self._queue.pop(oldest_id, None)

        self._queue[action.id] = action
        self._last_prompted_action_id = action.id
        self._last_prompt_time = time.time()

        logger.info(
            f"[ActionQueue] Staged action '{action.id}' [{action.domain}:{action.action}] "
            f"verbatim: '{action.verbatim_text[:60]}'"
        )
        return action

    _is_server: bool = False

    def mark_as_server(self) -> None:
        """Explicitly marks this instance as running inside the canonical Gateway process."""
        self._is_server = True

    def is_server(self) -> bool:
        """Determines whether this queue instance is inside the Gateway server process."""
        if self._is_server:
            return True
        if os.environ.get("VESPER_SERVICE_ROLE") == "gateway":
            self._is_server = True
            return True
        # Check if running in Gateway modules
        for m in ("backend.gateway.app", "backend.gateway.router", "backend.gateway.routes.sync"):
            if m in sys.modules:
                self._is_server = True
                return True
        return False

    def get_action(self, action_id: str) -> Optional[StagedAction]:
        return self._queue.get(action_id)

    def get_active_actions(self, domain: Optional[str] = None) -> List[StagedAction]:
        """Returns active staged actions sorted by priority then timestamp."""
        now = time.time()
        active = [
            a for a in self._queue.values()
            if (a.status in ("staged", "pending_return") and a.expires_at > now)
            or a.status == "reviewed_at_desk"
        ]

        # Cross-process fallback: If running outside Gateway process and local queue is empty, query Gateway REST endpoint
        if not self.is_server() and not active and not getattr(self, "_remote_syncing", False):
            try:
                self._remote_syncing = True
                import httpx
                params = {"domain": domain} if domain else {}
                resp = httpx.get("http://127.0.0.1:8000/sync/proactive/actions/active", params=params, timeout=0.2)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        active = [
                            StagedAction(**item)
                            for item in data
                            if (item.get("status") in ("staged", "pending_return") and item.get("expires_at", 0) > now)
                            or item.get("status") == "reviewed_at_desk"
                        ]
            except Exception:
                pass
            finally:
                self._remote_syncing = False

        if domain:
            active = [a for a in active if a.domain.lower() == domain.lower()]

        prio_order = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return sorted(active, key=lambda a: (prio_order.get(a.priority, 9), a.created_at))

    def get_recent_prompted_action(self, max_age_sec: float = 180.0) -> Optional[StagedAction]:
        """Returns the most recently prompted action if within the active focus window."""
        if self._last_prompted_action_id and (time.time() - self._last_prompt_time) <= max_age_sec:
            action = self._queue.get(self._last_prompted_action_id)
            if action and action.status in ("staged", "pending_return", "reviewed_at_desk"):
                return action

        # Cross-process fallback: Query Gateway REST endpoint only if running outside Gateway process
        if not self.is_server() and not getattr(self, "_remote_syncing", False):
            try:
                self._remote_syncing = True
                import httpx
                resp = httpx.get(
                    f"http://127.0.0.1:8000/sync/proactive/actions/recent?max_age={max_age_sec}",
                    timeout=0.2,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("found") and data.get("action"):
                        return StagedAction(**data["action"])
            except Exception:
                pass
            finally:
                self._remote_syncing = False
        return None

    def resolve_action(
        self,
        action_id: str,
        resolution: str,
        confirmed_by: str = "voice_disambiguated",
        rollback_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[StagedAction]:
        """Marks an action as confirmed, rejected, or expired."""
        action = self._queue.pop(action_id, None)
        if not action:
            # Cross-process fallback: Resolve on Gateway REST if not in local queue and running outside Gateway
            if not self.is_server() and not getattr(self, "_remote_syncing", False):
                try:
                    self._remote_syncing = True
                    import httpx
                    resp = httpx.post(
                        f"http://127.0.0.1:8000/sync/proactive/actions/{action_id}/resolve?new_status={resolution}&confirmed_by={confirmed_by}",
                        timeout=0.2,
                    )
                    if resp.status_code == 200 and resp.json().get("success"):
                        return StagedAction(**resp.json()["action"])
                except Exception:
                    pass
                finally:
                    self._remote_syncing = False
            return None

        action.status = resolution
        action.rollback_data = rollback_data
        self._history.append(action)
        if len(self._history) > 50:
            self._history = self._history[-50:]

        if self._last_prompted_action_id == action_id:
            self._last_prompted_action_id = None

        logger.info(
            f"[ActionQueue] Resolved action '{action_id}' -> {resolution} (via {confirmed_by})"
        )
        return action

    def mark_expired_for_return_review(self) -> None:
        """Transitions expired items to pending_return instead of dropping them."""
        now = time.time()
        for action in self._queue.values():
            if action.status == "staged" and action.expires_at <= now:
                action.status = "pending_return"

    def get_unreviewed_actions_for_return(self) -> List[StagedAction]:
        """Returns all unconfirmed items waiting for user's return to desk."""
        return [
            a for a in self._queue.values()
            if a.status in ("staged", "pending_return")
        ]

    def clear_all(self) -> None:
        self._queue.clear()
        self._last_prompted_action_id = None


action_queue = ActionQueueManager.get_instance()
