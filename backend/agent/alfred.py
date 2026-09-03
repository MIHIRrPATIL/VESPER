"""VESPER Cognitive Swarm Supervisor: Alfred.

The persona orchestrator and executive controller of the VESPER swarm.
Coordinates:
  1. Fast-Path Engine (<10ms deterministic execution).
  2. Dynamic Tool Discovery & 2-Stage Plan-and-Execute Engine.
  3. Output Evaluator & Sanitizer (<2ms zero-LLM filter).
  4. British Butler Persona synthesis (dry, poised, articulate).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.agent.evaluator import OutputEvaluator
from backend.agent.fast_path import FastPathEngine
from backend.agent.llm import LLMClient
from backend.agent.planner import SwarmPlanner
from backend.agent.registry import SpecialistRegistry, registry as default_registry

logger = logging.getLogger("vesper.agent.alfred")


class AlfredResponse(BaseModel):
    """Complete response from the Alfred cognitive supervisor."""

    speech_text: str = ""
    markdown_body: str = ""
    hud_cards: List[Dict[str, Any]] = Field(default_factory=list)
    fast_path: bool = False
    plan_type: str = "direct"
    specialist_actions: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms: float = 0.0


ALFRED_SYNTHESIS_PROMPT = """You are Alfred, an intelligent, poised, and impeccably articulate British personal assistant inspired by J.A.R.V.I.S.
Synthesize the specialist outcomes below into a seamless, natural response to the user's inquiry.

User Query: "{query}"

Specialist Execution Outcomes:
{outcomes}

Persona Directives:
- Speak with quiet confidence, British elegance, and subtle wit when appropriate.
- State facts, financial figures, and task confirmations with absolute precision.
- Do NOT read out raw URLs or table borders; describe what was done naturally.
- Keep the response direct and free of generic AI apologies.
"""


class AlfredSupervisor:
    """The central intelligence and orchestrator of the VESPER backend."""

    def __init__(
        self,
        registry: Optional[SpecialistRegistry] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.registry = registry or default_registry
        self.fast_path = FastPathEngine()
        self.llm = llm_client or LLMClient()
        self.planner = SwarmPlanner(self.llm)

    async def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AlfredResponse:
        """Processes an incoming user query through the cognitive swarm."""
        t0 = time.perf_counter()
        cleaned_query = query.strip()

        if not cleaned_query:
            return AlfredResponse(
                speech_text="At your service, sir.",
                markdown_body="At your service, sir.",
                fast_path=True,
                latency_ms=0.0,
            )

        # ── 1. Fast-Path Check (<10ms) ───────────────────────────────────────
        fp_result = self.fast_path.evaluate(cleaned_query)
        if fp_result.matched:
            # Trigger background specialist action (e.g. pause/resume Spotify)
            import asyncio
            if fp_result.intent:
                asyncio.create_task(
                    self.registry.execute_action(
                        agent_name=fp_result.intent,
                        action=fp_result.action,
                        params=fp_result.params,
                        context=context,
                    )
                )

            elapsed_ms = (time.perf_counter() - t0) * 1000
            cards = [fp_result.card_payload] if fp_result.card_payload else []
            return AlfredResponse(
                speech_text=fp_result.speech_text,
                markdown_body=fp_result.speech_text,
                hud_cards=cards,
                fast_path=True,
                plan_type="fast_path",
                specialist_actions=[{"agent": fp_result.intent, "action": fp_result.action, "params": fp_result.params}],
                latency_ms=elapsed_ms,
            )

        # ── 2. Stage 1: Swarm Planning ───────────────────────────────────────
        plan, plan_ms = await self.planner.create_plan(cleaned_query, self.registry)

        # ── 3. Stage 2: Execution ────────────────────────────────────────────
        exec_result = await self.planner.execute_plan(plan, self.registry, context)

        # ── 4. Persona Synthesis & Output Evaluation ─────────────────────────
        if plan.plan_type == "direct" and exec_result.direct_response:
            raw_response = exec_result.direct_response
            eval_res = OutputEvaluator.evaluate(raw_response)
        else:
            # Build outcomes summary for Alfred synthesis
            outcome_lines = []
            for r in exec_result.specialist_results:
                status = "Success" if r.success else f"Failed ({r.error})"
                summary = r.speech_summary or json.dumps(r.data)
                outcome_lines.append(f"- Action '{r.action}': {status} | Details: {summary}")

            outcomes_text = "\n".join(outcome_lines)
            synthesis_prompt = ALFRED_SYNTHESIS_PROMPT.format(
                query=cleaned_query,
                outcomes=outcomes_text,
            )

            messages = [
                {"role": "system", "content": synthesis_prompt},
                {"role": "user", "content": "Please present this update to me."},
            ]

            raw_response, _ = await self.llm.generate_chat(messages, temperature=0.3, max_tokens=350)
            eval_res = OutputEvaluator.evaluate(raw_response, exec_result.specialist_results)

        total_elapsed_ms = (time.perf_counter() - t0) * 1000

        action_records = [
            {"agent": r.action, "success": r.success, "data": r.data, "error": r.error}
            for r in exec_result.specialist_results
        ]

        return AlfredResponse(
            speech_text=eval_res.speech_text,
            markdown_body=eval_res.markdown_body,
            hud_cards=eval_res.hud_cards,
            fast_path=False,
            plan_type=plan.plan_type,
            specialist_actions=action_records,
            latency_ms=total_elapsed_ms,
        )
