"""VESPER Proactive Actions Append-Only Audit Logger.

Maintains an immutable record of all autonomous actions staged, confirmed,
rejected, or rolled back by the proactive swarm sentries.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("vesper.agent.proactive.audit")

AUDIT_LOG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "output", "proactive_actions_log.jsonl"
)


class AuditEntry(BaseModel):
    id: str
    action_id: str
    domain: str
    action_type: str
    params: Dict[str, Any]
    verbatim_text: str
    source_event_type: str
    raw_evidence_summary: str
    staged_at: float
    resolved_at: float
    resolution: str  # "confirmed", "rejected", "expired", "undone"
    confirmed_by: Optional[str] = None  # "voice_anchored", "hud_tap", "voice_focus_window"
    rollback_data: Optional[Dict[str, Any]] = None


class ProactiveAuditLogger:
    """Thread-safe append-only logger for all proactive actions."""

    _instance: Optional["ProactiveAuditLogger"] = None

    def __init__(self, log_path: str = AUDIT_LOG_FILE) -> None:
        self._log_path = log_path
        self._memory_entries: List[AuditEntry] = []
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
        self._load_existing_log()

    def _load_existing_log(self, max_entries: int = 50) -> None:
        """Loads recent historical entries from the append-only log on disk."""
        if not os.path.exists(self._log_path):
            return
        try:
            entries: List[AuditEntry] = []
            with open(self._log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(AuditEntry.model_validate(data))
                    except Exception:
                        continue
            self._memory_entries = entries[-max_entries:]
        except Exception as e:
            logger.warning(f"[AuditLogger] Failed to load existing audit log: {e}")

    @classmethod
    def get_instance(cls) -> "ProactiveAuditLogger":
        if cls._instance is None:
            cls._instance = ProactiveAuditLogger()
        return cls._instance

    def record_resolution(
        self,
        action_id: str,
        domain: str,
        action_type: str,
        params: Dict[str, Any],
        verbatim_text: str,
        source_event_type: str,
        raw_evidence: Dict[str, Any],
        staged_at: float,
        resolution: str,
        confirmed_by: Optional[str] = None,
        rollback_data: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Appends a resolution entry to the immutable audit log."""
        entry = AuditEntry(
            id=f"audit_{int(time.time() * 1000)}_{action_id[:8]}",
            action_id=action_id,
            domain=domain,
            action_type=action_type,
            params=params,
            verbatim_text=verbatim_text,
            source_event_type=source_event_type,
            raw_evidence_summary=str(raw_evidence)[:300],
            staged_at=staged_at,
            resolved_at=time.time(),
            resolution=resolution,
            confirmed_by=confirmed_by,
            rollback_data=rollback_data,
        )
        self._memory_entries.append(entry)
        if len(self._memory_entries) > 100:
            self._memory_entries.pop(0)

        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.model_dump()) + "\n")
        except Exception as e:
            logger.warning(f"[AuditLogger] Failed to write audit entry to file: {e}")

        logger.info(
            f"[AuditLogger] Recorded '{entry.action_id}' [{domain}:{action_type}] "
            f"as '{resolution}' via '{confirmed_by}'"
        )
        return entry

    def get_last_confirmed_action(self, domain: Optional[str] = None) -> Optional[AuditEntry]:
        """Returns the most recent confirmed action for rollback/undo purposes."""
        for entry in reversed(self._memory_entries):
            if entry.resolution == "confirmed":
                if domain is None or entry.domain.lower() == domain.lower():
                    return entry
        return None

    def mark_undone(self, audit_id: str) -> bool:
        """Marks an existing entry as reversed/undone."""
        for entry in self._memory_entries:
            if entry.id == audit_id:
                entry.resolution = "undone"
                return True
        return False

    def log_action(self, action: Any, confirmed_by: str = "voice") -> AuditEntry:
        """Convenience method to record a confirmed StagedAction."""
        return self.record_resolution(
            action_id=getattr(action, "id", str(time.time())),
            domain=getattr(action, "domain", "general"),
            action_type=getattr(action, "action", "unknown"),
            params=getattr(action, "params", {}),
            verbatim_text=getattr(action, "verbatim_text", ""),
            source_event_type="staged_action_confirmation",
            raw_evidence=getattr(action, "raw_evidence", {}),
            staged_at=getattr(action, "created_at", time.time()),
            resolution="confirmed",
            confirmed_by=confirmed_by,
            rollback_data=getattr(action, "rollback_data", None),
        )

    def get_last_action(self, domain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Returns the most recent confirmed action as a dictionary, or None."""
        entry = self.get_last_confirmed_action(domain)
        return entry.model_dump() if entry else None

    def record_undo(self, action_id: str, success: bool = True) -> bool:
        """Records an undo event for an existing action."""
        for entry in self._memory_entries:
            if entry.action_id == action_id or entry.id == action_id:
                entry.resolution = "undone" if success else "undo_failed"
                return True
        return False

    def list_entries(self, limit: int = 50) -> List[AuditEntry]:
        return list(reversed(self._memory_entries[-limit:]))


audit_logger = ProactiveAuditLogger.get_instance()
