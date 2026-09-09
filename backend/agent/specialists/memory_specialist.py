"""VESPER Memory Specialist Agent (4-Tier Shodh Cognitive Memory).

Features:
  1. Intelligent Fact Distillation & Category Taxonomy (personal, preference, work_tech, health_diet, routine).
  2. Conflict Resolution & Superseding (contradictory facts are superseded; duplicates are merged).
  3. Multi-Tier Retrieval Scoring (relevance + recency + access frequency).
  4. Poised British Butler Recall & 360-Degree User Profile Dossier.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import re

from backend.agent.llm import LLMClient
from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.data.client import get_supabase_client
from backend.data.models import MemoryCreate, ShodhMemoryModel
from backend.data.repositories.memory import ShodhMemoryRepository

logger = logging.getLogger("vesper.agent.specialists.memory")


class MemorySpecialist(BaseSpecialist):
    """Specialist agent for persistent 4-tier Shodh memory, conflict resolution, and fact synthesis."""

    def __init__(
        self,
        repo: Optional[ShodhMemoryRepository] = None,
        llm: Optional[LLMClient] = None,
    ) -> None:
        self.repo = repo or ShodhMemoryRepository(get_supabase_client())
        self.llm = llm or LLMClient()
        # Tier 1 Working Memory: session conversation buffer
        self._working_buffer: List[Dict[str, str]] = []
        # Cache for fast-path profile dossier lookups
        self._profile_cache: Optional[SpecialistResult] = None
        self._profile_cache_time: float = 0.0
        self._user_name: Optional[str] = None

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Manages long-term personal memory, user preferences, habits, facts, and knowledge retrieval."

    def get_capabilities(self) -> str:
        return (
            "Store and update personal facts, habits, and preferences with conflict resolution, "
            "recall facts on any topic, delete outdated memories, and generate a complete user profile dossier."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "store_memory",
                "description": "Distills and commits a personal fact, habit, or preference to long-term memory with automatic deduplication and conflict resolution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string", "description": "The fact or preference to remember (e.g. 'I prefer dark roast coffee')."},
                        "category": {
                            "type": "string",
                            "enum": ["preference", "personal", "work_tech", "health_diet", "routine"],
                            "description": "Category for the memory.",
                        },
                    },
                    "required": ["statement"],
                },
            },
            {
                "name": "recall_memory",
                "description": "Recalls what Alfred remembers about a specific topic, preference, or fact.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The topic, preference, or question to recall (e.g. 'What coffee do I like?')."},
                        "category": {"type": "string", "description": "Optional category filter."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "forget_memory",
                "description": "Removes or deactivates an outdated or unwanted fact from memory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The fact or topic to forget."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_user_profile",
                "description": "Generates a structured 360-degree briefing of everything Alfred knows about the user.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    # ── Tier 1 Working Memory ────────────────────────────────────────────────

    def record_working_turn(self, role: str, text: str) -> None:
        """Stores recent turns in short-term working buffer (sliding window of 10)."""
        self._working_buffer.append({"role": role, "text": text})
        if len(self._working_buffer) > 10:
            self._working_buffer.pop(0)

    # ── Conflict Resolution & Fact Distillation ──────────────────────────────

    async def _distill_fact(self, raw_statement: str) -> Dict[str, Any]:
        """Uses fast Groq LPU to distill a user statement into canonical fact, category, and search keywords."""
        system_prompt = (
            "You are a cognitive memory extractor. Analyze the user statement and return strictly valid JSON:\n"
            "{\n"
            '  "canonical_fact": "concise 3rd-person statement (e.g. User prefers dark roast coffee without sugar)",\n'
            '  "category": "preference" | "personal" | "work_tech" | "health_diet" | "routine",\n'
            '  "search_keywords": ["keyword1", "keyword2"]\n'
            "}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Statement to distill:\n{raw_statement}"},
        ]
        try:
            data, _ = await self.llm.generate_json(messages, temperature=0.1)
            return {
                "canonical_fact": data.get("canonical_fact") or raw_statement,
                "category": data.get("category") or "preference",
                "keywords": data.get("search_keywords") or [raw_statement.split()[0]],
            }
        except Exception:
            return {
                "canonical_fact": raw_statement,
                "category": "preference",
                "keywords": raw_statement.split()[:3],
            }

    async def store_memory(
        self, statement: str, category: Optional[str] = None
    ) -> SpecialistResult:
        """Stores a fact with conflict detection, deduplication, and superseding without blocking event loop."""
        self._profile_cache = None  # Invalidate cache on write
        distilled = await self._distill_fact(statement)
        canonical = distilled["canonical_fact"]
        cat = category or distilled["category"]
        keywords = distilled.get("keywords", [])

        # 1. Search existing memories for semantic duplicates or contradictions
        candidate_ids: set[str] = set()
        candidates = []

        # Always inspect most recent active memories first (in thread)
        recent_mems = await asyncio.to_thread(self.repo.list_memories, limit=25)
        for cand in recent_mems:
            if cand.id not in candidate_ids:
                candidate_ids.add(cand.id)
                candidates.append(cand)

        # Search at most top 2 keywords in thread
        for term in keywords[:2]:
            clean_term = term.strip(".,!?:;\"'")
            if len(clean_term) > 2:
                term_matches = await asyncio.to_thread(self.repo.search_by_text, clean_term, limit=5)
                for cand in term_matches:
                    if cand.id not in candidate_ids:
                        candidate_ids.add(cand.id)
                        candidates.append(cand)

        def _norm(s: str) -> str:
            cleaned = re.sub(r"[^\w\s]", "", s.lower()).strip()
            return " ".join([w for w in cleaned.split() if w not in ("the", "a", "an", "user", "i")])

        # 2. Check for exact duplicate or superseding
        superseded_id: Optional[str] = None
        potential_conflicts = []
        for cand in candidates:
            meta = cand.metadata if isinstance(cand.metadata, dict) else {}
            if meta.get("active") is False:
                continue

            cand_norm = _norm(cand.statement)
            stmt_norm = _norm(statement)
            canon_norm = _norm(canonical)

            cand_words = set(cand_norm.split())
            canon_words = set(canon_norm.split())
            stmt_words = set(stmt_norm.split())

            is_lexical_dup = (
                cand_norm in (canon_norm, stmt_norm)
                or (cand.statement.strip().lower() in (canonical.strip().lower(), statement.strip().lower()))
                or (cand_words and canon_words and len(cand_words & canon_words) / len(cand_words | canon_words) >= 0.75)
                or (cand_words and stmt_words and len(cand_words & stmt_words) / len(cand_words | stmt_words) >= 0.75)
            )

            # Exact or near-exact duplicate: merge by incrementing access count
            if is_lexical_dup:
                await asyncio.to_thread(self.repo.record_access, cand.id)
                return SpecialistResult(
                    success=True,
                    action="store_memory",
                    data={"action": "merged", "memory_id": cand.id, "statement": canonical},
                    speech_summary="I have reaffirmed that in my memory, sir.",
                    card_payload={"type": "memory_card", "action": "merged", "statement": canonical},
                )

            # Check overlap for conflict candidates
            if cand_words and canon_words and (len(cand_words & canon_words) >= 2 or cand.category == cat):
                potential_conflicts.append(cand)

        # Check for conflict using at most ONE LLM call on top conflict candidate
        if potential_conflicts:
            top_cand = potential_conflicts[0]
            eval_messages = [
                {
                    "role": "system",
                    "content": (
                        "Analyze if the two facts contradict or update each other. Return strictly JSON:\n"
                        '{"contradicts": true | false, "explanation": "brief rationale"}'
                    ),
                },
                {"role": "user", "content": f"Existing Fact: \"{top_cand.statement}\"\nNew Fact: \"{canonical}\""},
            ]
            try:
                eval_data, _ = await asyncio.wait_for(
                    self.llm.generate_json(eval_messages, temperature=0.0),
                    timeout=2.0,
                )
                if eval_data.get("contradicts"):
                    superseded_id = top_cand.id
            except Exception:
                pass

        # 3. Store new canonical memory in thread
        meta_payload = {
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "superseded_old_id": superseded_id,
        }

        created = await asyncio.to_thread(
            self.repo.store_fact,
            MemoryCreate(
                statement=canonical,
                category=cat,
                confidence=1.0,
                metadata=meta_payload,
            ),
        )

        # 4. If old memory was superseded, mark it inactive in thread
        if superseded_id:
            await asyncio.to_thread(self.repo.supersede, superseded_id, created.id)
            speech = f"I have updated my records to reflect that {canonical}, superseding the previous entry, sir."
        else:
            speech = f"I have committed that to memory: {canonical}, sir."

        return SpecialistResult(
            success=True,
            action="store_memory",
            data={"memory_id": created.id, "statement": canonical, "category": cat, "superseded": superseded_id},
            speech_summary=speech,
            card_payload={
                "type": "memory_card",
                "statement": canonical,
                "category": cat,
                "superseded": superseded_id is not None,
            },
        )

    # ── Multi-Tier Retrieval & Synthesis ─────────────────────────────────────

    def _score_memory(self, memory: ShodhMemoryModel, query_words: List[str]) -> float:
        """Scores candidate memory using keyword match, recency, and access frequency."""
        stmt_lower = memory.statement.lower()
        # Lexical score
        matches = sum(1 for w in query_words if w.lower() in stmt_lower)
        lex_score = matches / max(len(query_words), 1)

        # Recency score (days since creation)
        recency_score = 1.0
        if memory.created_at:
            delta_days = (datetime.now(timezone.utc) - memory.created_at).total_seconds() / 86400
            recency_score = max(0.1, 1.0 - (delta_days / 365.0))

        # Frequency boost (access count up to 10)
        freq_score = min(1.0, (memory.access_count or 0) / 10.0)

        return (lex_score * 0.5) + (recency_score * 0.3) + (freq_score * 0.2)

    async def recall_memory(self, query: str, category: Optional[str] = None) -> SpecialistResult:
        """Searches active memories, scores them, and synthesizes an articulate butler answer without blocking."""
        query_words = [w for w in re.findall(r"\w+", query) if len(w) > 2]
        all_candidates: List[ShodhMemoryModel] = []

        # Gather candidates by searching top 2 key terms in thread
        for kw in query_words[:2]:
            res = await asyncio.to_thread(self.repo.search_by_text, kw, limit=5)
            all_candidates.extend(res)

        # Deduplicate candidates by ID and filter only active
        seen_ids = set()
        active_candidates = []
        for c in all_candidates:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                meta = c.metadata if isinstance(c.metadata, dict) else {}
                if meta.get("active") is not False:
                    active_candidates.append(c)

        if not active_candidates:
            # Fallback search by category if provided
            if category:
                active_candidates = await asyncio.to_thread(self.repo.list_memories, category=category, limit=5)

        if not active_candidates:
            return SpecialistResult(
                success=True,
                action="recall_memory",
                data={"query": query, "found": False, "memories": []},
                speech_summary=f"I do not currently have any recollections regarding '{query}', sir.",
                card_payload={"type": "memory_recall_card", "query": query, "found": False},
            )

        # Score and rank candidates
        ranked = sorted(active_candidates, key=lambda m: self._score_memory(m, query_words), reverse=True)[:4]

        # Record access in thread
        for r in ranked:
            asyncio.create_task(asyncio.to_thread(self.repo.record_access, r.id))

        facts_text = "\n".join([f"- {m.statement} (Category: {m.category})" for m in ranked])

        # Butler persona synthesis
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Alfred, a poised and loyal British butler. Answer the user's query naturally based on your recalled memories. "
                    "Do not recite bullet points or mention database records. Speak with articulate warmth."
                ),
            },
            {"role": "user", "content": f"User Query: {query}\n\nRecalled Memories:\n{facts_text}"},
        ]
        try:
            synthesis, _ = await asyncio.wait_for(
                self.llm.generate_chat(messages, temperature=0.2, max_tokens=150),
                timeout=3.0,
            )
        except Exception:
            synthesis = ""
        synthesis = synthesis.strip() or f"According to my records, {ranked[0].statement}, sir."

        return SpecialistResult(
            success=True,
            action="recall_memory",
            data={
                "query": query,
                "found": True,
                "memories": [m.statement for m in ranked],
            },
            speech_summary=synthesis,
            card_payload={
                "type": "memory_recall_card",
                "query": query,
                "found": True,
                "memories": [m.statement for m in ranked],
            },
        )

    # ── User Profile Dossier ─────────────────────────────────────────────────

    async def get_user_profile(self) -> SpecialistResult:
        """Generates a complete 360-degree organized profile of the user with in-memory caching."""
        now_ts = time.time()
        if self._profile_cache and (now_ts - self._profile_cache_time) < 60.0:
            return self._profile_cache

        all_mem = await asyncio.to_thread(self.repo.list_memories, limit=100)
        active_mem = [m for m in all_mem if not (isinstance(m.metadata, dict) and m.metadata.get("active") is False)]

        if not active_mem:
            res = SpecialistResult(
                success=True,
                action="get_user_profile",
                speech_summary="I have not yet recorded any personal facts or preferences about you, sir.",
                card_payload={"type": "user_profile_card", "profile": {}},
            )
            self._profile_cache = res
            self._profile_cache_time = now_ts
            return res

        grouped: Dict[str, List[str]] = {}
        for m in active_mem:
            cat = m.category or "general"
            grouped.setdefault(cat, []).append(m.statement)

        dossier_lines = []
        for cat, facts in grouped.items():
            dossier_lines.append(f"{cat.replace('_', ' ').capitalize()}: {'; '.join(facts[:3])}")

        speech = "Here is what I have committed to memory regarding your preferences and profile, sir: " + " | ".join(dossier_lines) + "."

        res = SpecialistResult(
            success=True,
            action="get_user_profile",
            data={"profile": grouped, "total_memories": len(active_mem)},
            speech_summary=speech,
            card_payload={"type": "user_profile_card", "profile": grouped, "total": len(active_mem)},
        )
        self._profile_cache = res
        self._profile_cache_time = now_ts
        return res

    # ── Forget Outdated Facts ────────────────────────────────────────────────

    async def forget_memory(self, query: str) -> SpecialistResult:
        """Finds matching facts and removes them from Supabase."""
        query_kw = query.split()[0] if query else ""
        candidates = self.repo.search_by_text(query_kw, limit=5)

        if not candidates:
            return SpecialistResult(
                success=False,
                action="forget_memory",
                error=f"No matching memories found for '{query}'.",
                speech_summary=f"I found no recollections matching '{query}' to remove, sir.",
            )

        # Delete the most relevant match
        target = candidates[0]
        self.repo.delete(target.id)

        speech = f"I have excised that information regarding '{target.statement}' from my recollections, sir."
        return SpecialistResult(
            success=True,
            action="forget_memory",
            data={"deleted_id": target.id, "statement": target.statement},
            speech_summary=speech,
            card_payload={"type": "memory_deleted_card", "statement": target.statement},
        )

    # ── Execution Router ─────────────────────────────────────────────────────

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        act = action.lower().strip()

        # 1. Store Memory
        if act in ["store_memory", "remember", "save_memory", "learn"]:
            stmt = str(params.get("statement") or params.get("fact") or params.get("note") or "").strip()
            cat = params.get("category")
            if not stmt:
                return SpecialistResult(success=False, action=action, error="Statement is required to remember.")
            return await self.store_memory(stmt, category=cat)

        # 2. Recall Memory
        elif act in ["recall_memory", "recall", "remember_query", "what_do_you_know", "get_memory"]:
            q = str(params.get("query") or params.get("topic") or "").strip()
            cat = params.get("category")
            if not q:
                return await self.get_user_profile()
            return await self.recall_memory(q, category=cat)

        # 3. User Profile
        elif act in ["get_user_profile", "user_profile", "profile", "who_am_i"]:
            return await self.get_user_profile()

        # 4. Forget Memory
        elif act in ["forget_memory", "forget", "delete_memory", "remove_memory"]:
            q = str(params.get("query") or params.get("topic") or "").strip()
            if not q:
                return SpecialistResult(success=False, action=action, error="Topic to forget is required.")
            return await self.forget_memory(q)

        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}' on memory specialist.")
