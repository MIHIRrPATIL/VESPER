"""VESPER Asynchronous Background Task Triage Worker.

Runs in the background via `asyncio.create_task()` immediately after
a task is created, without blocking or slowing down Alfred's fast voice response (<500ms).

Analyzes:
  1. Semantic priority (urgent, high, medium, low) using Groq LPU.
  2. Smart categorization and tags (e.g. #devops, #finance, #health).
  3. Estimated duration and time-sensitivity.
Persists enriched metadata to Supabase silently.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from backend.agent.llm import LLMClient
from backend.data.client import get_supabase_client
from backend.data.models import PriorityLevel

logger = logging.getLogger("vesper.agent.tasks.triage")

TRIAGE_PROMPT = """You are an intelligent Chief of Staff triaging tasks for a high-performance engineer.
Given the task title, infer:
1. priority: "urgent" (critical blocker/emergency), "high" (important, high impact), "medium" (standard day-to-day), or "low" (someday/optional).
2. tags: 1 to 3 relevant tags (e.g. ["devops", "infrastructure"], ["finance", "banking"], ["health"], ["code"]).
3. estimated_minutes: estimated time in minutes to complete (e.g. 15, 60, 120).

Task Title: "{title}"

Respond with strictly valid JSON:
{{
  "priority": "urgent" | "high" | "medium" | "low",
  "tags": ["tag1", "tag2"],
  "estimated_minutes": 30
}}
"""


class AsyncTaskTriageWorker:
    """Decoupled background worker for semantic priority and tag enrichment."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient()

    async def triage_task_in_background(self, task_id: str, title: str) -> None:
        """Fired in background via `asyncio.create_task()`.

        Does not block voice turns.
        """
        logger.info(f"[TaskTriage] Starting background AI triage for task '{title}' ({task_id})...")

        messages = [
            {"role": "system", "content": TRIAGE_PROMPT.format(title=title)},
            {"role": "user", "content": f"Triage this task: {title}"},
        ]

        try:
            triage_data, elapsed_ms = await self.llm.generate_json(messages, temperature=0.1)
            priority_str = triage_data.get("priority", "medium").lower()
            tags = triage_data.get("tags", [])
            est_minutes = triage_data.get("estimated_minutes", 30)

            # Map to valid PriorityLevel (HIGH, NORMAL, LOW)
            valid_p = PriorityLevel.NORMAL
            if "urgent" in priority_str or "high" in priority_str:
                valid_p = PriorityLevel.HIGH
            elif "low" in priority_str:
                valid_p = PriorityLevel.LOW
            else:
                valid_p = PriorityLevel.NORMAL

            # Update Supabase silently
            client = get_supabase_client()
            client.table("tasks").update({
                "priority": valid_p.value,
                "metadata": {
                    "tags": tags,
                    "estimated_minutes": est_minutes,
                    "auto_triaged": True,
                    "triage_latency_ms": elapsed_ms,
                },
            }).eq("id", task_id).execute()

            logger.info(
                f"[TaskTriage] ✓ Completed triage for '{title}': "
                f"Priority={valid_p.value}, Tags={tags} (in {elapsed_ms:.1f}ms background time)"
            )

        except Exception as e:
            logger.warning(f"[TaskTriage] Background triage failed for '{title}': {e}")
