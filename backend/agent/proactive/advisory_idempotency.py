"""VESPER Deterministic Advisory Idempotency Module.

Ensures all proactive advisories, OTP security prompts, VIP task proposals,
and financial recommendations have deterministic fingerprints, preventing
duplicate broadcasts across reconnection flushes and restarts.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("vesper.agent.proactive.idempotency")

_DB_PATH = Path("/home/mihir/Codes/VESPER/backend/data/advisories.db")


def generate_financial_advisory_id(
    amount: float | str,
    tx_type: str | float = "expense",
    merchant: str = "",
    account: str = "",
    timestamp: Optional[float] = None,
) -> str:
    """Generates a deterministic 1-hour bucketed ID for a financial transaction."""
    if isinstance(amount, str) and (isinstance(tx_type, (int, float)) or str(tx_type).replace(".", "", 1).isdigit()):
        acc_str = str(amount)
        amt_val = float(tx_type)
        type_str = str(merchant) or "expense"
        merch_str = str(account)
    else:
        amt_val = float(amount)
        type_str = str(tx_type) or "expense"
        merch_str = str(merchant)
        acc_str = str(account)

    ts = timestamp or time.time()
    hour_bucket = int(ts // 3600)
    raw = f"finance:{acc_str.lower().strip()}:{amt_val:.2f}:{type_str.lower().strip()}:{merch_str.lower().strip()}:{hour_bucket}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"act_fin_{digest}"


def generate_otp_advisory_id(
    source_or_code: str,
    code_or_source: str,
    timestamp: Optional[float] = None,
) -> str:
    """Generates a deterministic 10-minute bucketed ID for an OTP code."""
    s1 = str(source_or_code).strip()
    s2 = str(code_or_source).strip()
    if s1.isdigit() and not s2.isdigit():
        code, source = s1, s2
    else:
        source, code = s1, s2

    ts = timestamp or time.time()
    window_bucket = int(ts // 600)
    raw = f"security_otp:{source.lower().strip()}:{code.strip()}:{window_bucket}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"act_otp_{digest}"


def generate_task_advisory_id(
    sender_or_title: str,
    title_or_sender: str,
    timestamp: Optional[float] = None,
) -> str:
    """Generates a deterministic 1-day bucketed ID for a VIP task proposal."""
    ts = timestamp or time.time()
    day_bucket = int(ts // 86400)
    t1 = "".join(ch for ch in str(sender_or_title).lower() if ch.isalnum() or ch.isspace()).strip()
    t2 = "".join(ch for ch in str(title_or_sender).lower() if ch.isalnum() or ch.isspace()).strip()
    tokens = sorted([t1, t2])
    raw = f"task:{tokens[0]}:{tokens[1]}:{day_bucket}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"act_task_{digest}"


def generate_debt_advisory_id(
    person_or_amount: str | float,
    amount_or_person: float | str,
    timestamp: Optional[float] = None,
) -> str:
    """Generates a deterministic 1-hour bucketed ID for a peer debt proposal."""
    if isinstance(person_or_amount, (int, float)) or str(person_or_amount).replace(".", "", 1).isdigit():
        amt_val = float(person_or_amount)
        person_str = str(amount_or_person)
    else:
        person_str = str(person_or_amount)
        amt_val = float(amount_or_person)

    ts = timestamp or time.time()
    hour_bucket = int(ts // 3600)
    raw = f"debt:{person_str.lower().strip()}:{amt_val:.2f}:{hour_bucket}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"act_debt_{digest}"


def generate_general_advisory_id(
    package_name: str,
    title: str,
    text: str,
    timestamp: Optional[float] = None,
) -> str:
    """Generates a deterministic 1-hour bucketed ID for general alerts."""
    ts = timestamp or time.time()
    hour_bucket = int(ts // 3600)
    snippet = text[:40].lower().strip()
    raw = f"advisory:{package_name.lower().strip()}:{title.lower().strip()}:{snippet}:{hour_bucket}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"act_adv_{digest}"


class AdvisoryIdempotencyRegistry:
    """Persistent registry of dispatched advisory IDs to eliminate redundant recommendations."""

    _instance: Optional["AdvisoryIdempotencyRegistry"] = None

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path
        self._memory_cache: dict[str, float] = {}  # id -> expires_at
        self._init_db()

    @classmethod
    def get_instance(cls) -> "AdvisoryIdempotencyRegistry":
        if cls._instance is None:
            cls._instance = AdvisoryIdempotencyRegistry()
        return cls._instance

    def _init_db(self) -> None:
        """Initializes SQLite table for dispatched advisory deduplication."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dispatched_advisories (
                        advisory_id TEXT PRIMARY KEY,
                        domain TEXT,
                        created_at REAL,
                        expires_at REAL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_adv_expires ON dispatched_advisories(expires_at)")
                conn.commit()
        except Exception as e:
            logger.warning(f"[IdempotencyRegistry] Failed to init DB: {e}")

    def is_dispatched(self, advisory_id: str) -> bool:
        """Checks if this advisory was already dispatched and is still within retention."""
        now = time.time()
        # 1. Fast in-memory check
        exp = self._memory_cache.get(advisory_id)
        if exp is not None:
            if exp > now:
                return True
            else:
                self._memory_cache.pop(advisory_id, None)

        # 2. SQLite check
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT expires_at FROM dispatched_advisories WHERE advisory_id = ?",
                    (advisory_id,),
                )
                row = cursor.fetchone()
                if row:
                    expires_at = float(row[0])
                    if expires_at > now:
                        self._memory_cache[advisory_id] = expires_at
                        return True
                    else:
                        cursor.execute("DELETE FROM dispatched_advisories WHERE advisory_id = ?", (advisory_id,))
                        conn.commit()
        except Exception as e:
            logger.debug(f"[IdempotencyRegistry] Lookup error: {e}")

        return False

    def record_dispatch(
        self,
        advisory_id: str,
        domain: str = "general",
        ttl_seconds: float = 86400.0,
    ) -> None:
        """Records an advisory as dispatched for the given TTL."""
        now = time.time()
        expires_at = now + ttl_seconds
        self._memory_cache[advisory_id] = expires_at

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO dispatched_advisories (advisory_id, domain, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (advisory_id, domain, now, expires_at),
                )
                # Periodically purge expired records (1 in 20 chance)
                if int(now) % 20 == 0:
                    conn.execute("DELETE FROM dispatched_advisories WHERE expires_at < ?", (now,))
                conn.commit()
        except Exception as e:
            logger.warning(f"[IdempotencyRegistry] Failed to record dispatch: {e}")


advisory_registry = AdvisoryIdempotencyRegistry.get_instance()
