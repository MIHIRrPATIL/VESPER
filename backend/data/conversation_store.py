"""VESPER Persistent Conversation Store.

Provides a lightweight SQLite-backed store for multi-session dialogue history.
Every user-assistant exchange is recorded and can be recalled, searched, and
used as check-in material across sessions and reboots.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vesper.data.conversation_store")

_DB_PATH = Path(__file__).resolve().parent / "conversations.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    session_id  TEXT    NOT NULL DEFAULT '',
    role        TEXT    NOT NULL,           -- 'user' | 'assistant'
    content     TEXT    NOT NULL,
    intent      TEXT    NOT NULL DEFAULT '',
    summary     TEXT    NOT NULL DEFAULT '',
    entities    TEXT    NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_conv_timestamp  ON conversation_turns (timestamp);
CREATE INDEX IF NOT EXISTS idx_conv_session    ON conversation_turns (session_id);
CREATE INDEX IF NOT EXISTS idx_conv_role       ON conversation_turns (role);

CREATE TABLE IF NOT EXISTS conversation_topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    session_id  TEXT    NOT NULL DEFAULT '',
    topic       TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT 'general',
    metadata    TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_topic_timestamp ON conversation_topics (timestamp);
"""


class ConversationStore:
    """Manages persistent conversation history backed by a local SQLite database."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def record_turn(
        self,
        role: str,
        content: str,
        intent: str = "",
        summary: str = "",
        entities: Optional[List[str]] = None,
        session_id: str = "",
    ) -> None:
        """Records a single conversation turn synchronously."""
        ts = datetime.datetime.now().isoformat()
        entities_json = json.dumps(entities or [])
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO conversation_turns (timestamp, session_id, role, content, intent, summary, entities) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, session_id, role, content, intent, summary, entities_json),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[ConversationStore] Failed to record turn: {e}")

    async def arecord_turn(
        self,
        role: str,
        content: str,
        intent: str = "",
        summary: str = "",
        entities: Optional[List[str]] = None,
        session_id: str = "",
    ) -> None:
        """Asynchronously records a conversation turn (non-blocking)."""
        await asyncio.to_thread(self.record_turn, role, content, intent, summary, entities, session_id)

    def get_recent_history(self, limit: int = 14) -> List[Dict[str, Any]]:
        """Returns the most recent conversation turns across sessions."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT timestamp, session_id, role, content, intent, summary, entities "
                "FROM conversation_turns ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            result = []
            for r in reversed(rows):
                result.append({
                    "timestamp": r["timestamp"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "content": r["content"],
                    "intent": r["intent"],
                    "summary": r["summary"],
                    "entities": json.loads(r["entities"] or "[]"),
                })
            return result
        except Exception as e:
            logger.warning(f"[ConversationStore] Failed to get recent history: {e}")
            return []

    def search_conversations(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Keyword search across historical conversation turns."""
        try:
            q = f"%{query}%"
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT timestamp, session_id, role, content, intent, summary, entities "
                "FROM conversation_turns "
                "WHERE content LIKE ? OR summary LIKE ? OR intent LIKE ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (q, q, q, limit),
            ).fetchall()
            conn.close()
            return [
                {
                    "timestamp": r["timestamp"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "content": r["content"],
                    "intent": r["intent"],
                    "summary": r["summary"],
                    "entities": json.loads(r["entities"] or "[]"),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"[ConversationStore] Search failed: {e}")
            return []

    def get_recent_topics(self, days: int = 7) -> List[str]:
        """Returns distinct topics discussed in the last N days (inferred from intents)."""
        try:
            since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT DISTINCT intent FROM conversation_turns "
                "WHERE timestamp >= ? AND intent != '' ORDER BY timestamp DESC LIMIT 20",
                (since,),
            ).fetchall()
            conn.close()
            topics = []
            seen = set()
            for r in rows:
                t = r["intent"].strip()
                if t and t not in seen:
                    seen.add(t)
                    topics.append(t)
            return topics
        except Exception as e:
            logger.warning(f"[ConversationStore] get_recent_topics failed: {e}")
            return []

    def get_suggested_check_ins(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Returns recent user queries/topics suitable as natural conversation starters."""
        try:
            since = (datetime.datetime.now() - datetime.timedelta(days=3)).isoformat()
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT timestamp, content, intent, summary FROM conversation_turns "
                "WHERE role = 'user' AND timestamp >= ? "
                "AND length(content) > 15 "
                "ORDER BY timestamp DESC LIMIT ?",
                (since, limit),
            ).fetchall()
            conn.close()
            return [
                {
                    "timestamp": r["timestamp"],
                    "content": r["content"],
                    "intent": r["intent"],
                    "summary": r["summary"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"[ConversationStore] get_suggested_check_ins failed: {e}")
            return []

    def get_conversation_summary_for_briefing(self) -> str:
        """Builds a brief narrative summary of recent conversations for a morning check-in."""
        topics = self.get_recent_topics(days=3)
        check_ins = self.get_suggested_check_ins(limit=3)
        history = self.get_recent_history(limit=6)
        parts: List[str] = []
        if topics:
            parts.append(f"Recent topics: {', '.join(topics[:5])}.")
        if check_ins:
            last_query = check_ins[0].get("content", "")[:120] if check_ins else ""
            if last_query:
                parts.append(f"Last discussed: \"{last_query}\".")
        if history:
            assistant_lines = [h["content"][:100] for h in history if h["role"] == "assistant"][-3:]
            if assistant_lines:
                parts.append("Previous responses: " + " | ".join(assistant_lines) + ".")
        return " ".join(parts) if parts else ""


# Module-level singleton
conversation_store = ConversationStore()
