"""Shodh-Memory Repository for Supabase.

Stores episodic facts and behavioral experiences. Designed with text search
now, and hooks for pgvector embedding similarity when planned in detail later.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from supabase import Client

from backend.data.client import get_supabase_client
from backend.data.models import MemoryCreate, ShodhMemoryModel

logger = logging.getLogger("vesper.data.memory")


class ShodhMemoryRepository:
    """Repository managing episodic user facts and experience statements."""

    def __init__(self, client: Optional[Client] = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        if self._client is not None:
            return self._client
        return get_supabase_client()

    def store_fact(self, memory: MemoryCreate) -> ShodhMemoryModel:
        """Stores a concise natural-language fact statement (<50 words)."""
        data = {
            "user_id": memory.user_id,
            "statement": memory.statement,
            "category": memory.category,
            "confidence": (memory.confidence),
            "metadata": memory.metadata,
        }
        res = self.client.table("shodh_memories").insert(data).execute()
        if not res.data:
            raise RuntimeError("Failed to store memory in Supabase.")
        return ShodhMemoryModel.model_validate(res.data[0])

    def search_by_text(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 5,
    ) -> list[ShodhMemoryModel]:
        """Fast keyword/text retrieval without LLM embedding latency."""
        res = (
            self.client.table("shodh_memories")
            .select("*")
            .eq("user_id", user_id)
            .ilike("statement", f"%{query}%")
            .order("access_count", desc=True)
            .limit(limit)
            .execute()
        )
        return [ShodhMemoryModel.model_validate(row) for row in res.data]

    def list_memories(
        self,
        user_id: str = "default_user",
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[ShodhMemoryModel]:
        """Lists stored memories, optionally filtered by category."""
        builder = (
            self.client.table("shodh_memories")
            .select("*")
            .eq("user_id", user_id)
        )
        if category:
            builder = builder.eq("category", category)
        res = builder.order("created_at", desc=True).limit(limit).execute()
        return [ShodhMemoryModel.model_validate(row) for row in res.data]

    def record_access(self, memory_id: str) -> None:
        """Increments access count and updates last_accessed_at timestamp."""
        from datetime import timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        # Fetch current count
        res = self.client.table("shodh_memories").select("access_count").eq("id", memory_id).execute()
        if res.data:
            r = dict(res.data[0])  # type: ignore[arg-type]
            new_count = int(r.get("access_count") or 0) + 1
            self.client.table("shodh_memories").update({
                "access_count": new_count,
                "last_accessed_at": now_iso,
            }).eq("id", memory_id).execute()

    def update_statement(self, memory_id: str, new_statement: str) -> bool:
        """Updates an existing memory statement."""
        res = self.client.table("shodh_memories").update({"statement": new_statement}).eq("id", memory_id).execute()
        return len(res.data) > 0

    def supersede(self, old_id: str, new_id: str) -> bool:
        """Marks an older fact as superseded by a newer contradictory fact."""
        res = self.client.table("shodh_memories").select("metadata").eq("id", old_id).execute()
        meta = {}
        if res.data and isinstance(res.data[0], dict):
            raw_meta = res.data[0].get("metadata")
            if isinstance(raw_meta, dict):
                meta = dict(raw_meta)
        meta["superseded_by"] = new_id
        meta["active"] = False

        update_res = self.client.table("shodh_memories").update({"metadata": meta}).eq("id", old_id).execute()
        return len(update_res.data) > 0

    def delete(self, memory_id: str) -> bool:
        """Deletes a memory statement."""
        res = self.client.table("shodh_memories").delete().eq("id", memory_id).execute()
        return len(res.data) > 0
