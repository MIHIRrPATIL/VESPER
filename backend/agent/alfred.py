"""VESPER Cognitive Swarm Supervisor: Alfred.

The persona orchestrator and executive controller of the VESPER swarm.
Coordinates:
  1. Fast-Path Engine (<10ms deterministic execution).
  2. Dynamic Tool Discovery & 2-Stage Plan-and-Execute Engine.
  3. Output Evaluator & Sanitizer (<2ms zero-LLM filter).
  4. British Butler Persona synthesis (dry, poised, articulate).
"""

from __future__ import annotations

import datetime
import json
import logging
import re
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

Current Temporal Context:
- Current Date & Time: {current_datetime} ({current_day})

User Query: "{query}"

Specialist Execution Outcomes:
{outcomes}

Persona Directives:
- Speak with quiet confidence, British elegance, and subtle wit when appropriate.
- State facts, financial figures, dates, and titles with absolute precision.
- CRITICAL TEMPORAL GROUNDING & DATES:
  * Current reference time: {current_datetime} ({current_day}).
  * Interpret relative references ('today', 'yesterday', 'tomorrow', 'this evening', 'next week') strictly against this current date and time.
  * Strictly distinguish between tasks or appointments scheduled for TODAY versus older backlog tasks or events from previous days. NEVER describe past backlog tasks as tasks scheduled for today.
- CRITICAL FACTUAL GROUNDING & ANTI-HALLUCINATION:
  1. Base every factual claim STRICTLY and EXCLUSIVELY on the Specialist Execution Outcomes and Verified Web Sources above.
  2. NEVER contradict, alter, or 'correct' the specialist outcomes or search results with unsupported assumptions.
  3. If verified sources or metadata specify an entity, director, actor, date, or number, report it as definitive truth.
  4. If the specialist outcomes do not provide the answer, acknowledge that verified information was not found rather than inventing names, plots, or details.
  5. SEQUENTIAL VISION → RESEARCH HIERARCHY: When the outcomes include both a vision/OCR step AND a research/web-search step (in that order), treat the RESEARCH RESULTS as ground truth and the vision description as an unverified hypothesis only. If the research results contradict the vision description, defer entirely to the research results. Never blend a vision model's guess with verified search facts as if they are equally reliable.
  6. MEDIUM-CONFIDENCE OCR WARNING: If an OCR step reports confidence="medium", acknowledge that the identification may be approximate and the research results are based on a partial read.
- Do NOT read out raw URLs or table borders; describe what was done naturally.
- CRITICAL SPEECH SAFETY: NEVER read out raw code, HTML tags, DOCTYPE declarations, CSS styles, JavaScript snippets, or tracking boilerplate. Always extract and speak only the human message, sender, date, and key subject in an articulate, polished manner.
- Keep the response direct and free of generic AI apologies.
- When referring to recent dialogue or previous actions, speak naturally as an attentive butler aware of active entities and conversation history.
- When summarizing lists, chronological events, or conversation threads, present the progression of events and the latest update clearly.
- CRITICAL NUMERICAL PRECISION: If specialist outcomes contain financial balances, bank accounts, debts, or currency figures (₹/INR), reproduce those numbers EXACTLY as given. NEVER round, alter, or transpose digits.
- EMAIL ACTIONS & DRAFTS:
  * For email drafts or dispatch, speak with utmost brevity (1-2 sentences max).
  * State the recipient and subject, and ask for confirmation ('Would you like me to send it, sir?').
  * NEVER output internal reasoning, justifications, chain-of-thought, or headers like 'Reasoning:', 'Explanation:', 'To:', 'Subject:' in the speech response.
- SANDBOX / MOCK DATA DISCLOSURE: If any specialist outcome indicates source="sandbox" or source="sandbox_inbox", explicitly state that you are referencing offline sandbox data as live account credentials are not yet connected.
"""


def normalize_spoken_emails(text: str) -> str:
    """Converts natural speech transcriptions of email addresses into standard format.

    Examples:
      'mihirpatil885 at the rate gmail.com' -> 'mihirpatil885@gmail.com'
      'mihir patil 885 at the rate gmail.com' -> 'mihirpatil885@gmail.com'
      'at the rate gmail.com' -> '@gmail.com'
      'at the rate of gmail.com' -> '@gmail.com'
      'john dot doe at gmail dot com' -> 'john.doe@gmail.com'
    """
    if not text:
        return ""

    t = text
    # 1. Replace "dot com", "dot io", etc. (consuming any whitespace before dot)
    t = re.sub(r"\s*\bdot\s+(com|net|org|io|ai|in|edu|gov|co|app|tech)\b", r".\1", t, flags=re.IGNORECASE)

    # 2. Replace "dot" between alphanumerics e.g. "john dot doe" -> "john.doe"
    t = re.sub(r"([a-zA-Z0-9_-]+)\s+dot\s+([a-zA-Z0-9_-]+)", r"\1.\2", t, flags=re.IGNORECASE)

    # 3. Handle spoken handles with spaces after common verbs/prepositions:
    # e.g., "email to mihir patil 885 at the rate gmail.com" -> "email to mihirpatil885@gmail.com"
    def _collapse_handle(m):
        prefix = m.group(1) or ""
        handle = re.sub(r"\s+", "", m.group(2))
        domain = m.group(3)
        return f"{prefix}{handle}@{domain}"

    t = re.sub(
        r"(\b(?:to|for|send|draft|email)\s+)([a-zA-Z0-9]+(?:\s+[a-zA-Z0-9]+){1,4})\s+(?:at the rate of|at the rate|at sign|at)\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        _collapse_handle,
        t,
        flags=re.IGNORECASE,
    )

    # 4. Replace "at the rate of", "at the rate", "at sign" before domain (with single-token handle)
    t = re.sub(
        r"([a-zA-Z0-9._%+-]+)\s+(?:at the rate of|at the rate|at sign)\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        r"\1@\2",
        t,
        flags=re.IGNORECASE,
    )

    # 5. Replace standalone "at" between user and email domain
    t = re.sub(
        r"([a-zA-Z0-9._%+-]+)\s+at\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        r"\1@\2",
        t,
        flags=re.IGNORECASE,
    )

    # 6. Standalone or phrase-initial "at the rate (of) domain.com" or "at domain.com" -> "@domain.com"
    t = re.sub(
        r"(?:^|\b)(?:at the rate of|at the rate|at sign)\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        r"@\1",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(?:^|\b)(?:at)\s+([a-zA-Z0-9-]+\.(?:com|net|org|io|ai|in|edu|gov|co|app|tech))\b",
        r"@\1",
        t,
        flags=re.IGNORECASE,
    )

    return t


def detect_cut_off_utterance(query: str) -> bool:
    """Detects whether an utterance was cut off mid-speech by VAD or user hesitation."""
    clean = query.strip()
    if not clean:
        return False

    # Trailing ellipsis or dash markers indicate abrupt pause
    if re.search(r"(\.\.\.|…|--|-)\s*$", clean):
        return True

    # Strip trailing punctuation for word analysis
    words = re.sub(r"[^\w\s]", "", clean).strip().split()
    if not words:
        return False

    last_word = words[-1].lower()
    q_lower = clean.lower().strip("?!.")

    # Check if query consists solely of introductory openers without an actual action
    stripped_openers = re.sub(
        r"\b(can you|could you|would you|will you|please|i want to|i would like to|i need to|tell me|check if|see if|write an email to)\b",
        "",
        q_lower,
    ).strip()
    if not stripped_openers:
        return True

    # Dangling trailing prepositions / conjunctions
    dangling_tokens = {
        "from", "to", "at", "with", "about", "for", "into", "saying",
        "because", "and", "or", "while", "whereby", "onto", "toward", "towards",
    }

    if last_word in dangling_tokens:
        # Check if this is a legitimate inverted question ending in a preposition
        is_legitimate_inverted_q = bool(
            re.match(r"^(who|where|what|which)\b", q_lower)
            and len(words) >= 3
            and words[1] in ("is", "are", "was", "were", "did", "do", "does", "should", "could", "would", "can")
        )
        if not is_legitimate_inverted_q:
            return True

    return False


class AlfredSupervisor:
    """The central intelligence and orchestrator of the VESPER backend."""

    def __init__(
        self,
        registry: Optional[SpecialistRegistry] = None,
        llm_client: Optional[LLMClient] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self.registry = registry or default_registry
        self.fast_path = FastPathEngine()
        self.llm = llm_client or LLMClient()
        self.planner = SwarmPlanner(self.llm)
        self.conversation_history: List[Dict[str, str]] = []
        self._turn_counter: int = 0
        self._context_metadata: Dict[str, Dict[str, Any]] = {}
        self._session_id: str = session_id or ""
        self.session_context: Dict[str, Any] = {
            "entities": {},
            "active_email": None,
            "active_track": None,
            "active_repo": None,
            "active_task": None,
            "active_person": None,
            "active_event": None,
            "active_visual": None,
            "pending_incomplete_utterance": None,
            "pending_email_draft": None,
            "last_research": None,
        }
        try:
            from backend.data.conversation_store import conversation_store as _conv_store
            self._conversation_store = _conv_store
        except Exception:
            self._conversation_store = None

    def clear_history(self) -> None:
        """Clears the session conversation history and active context."""
        self.conversation_history.clear()
        self._turn_counter = 0
        self._context_metadata.clear()
        self.session_context = {
            "entities": {},
            "active_email": None,
            "active_track": None,
            "active_repo": None,
            "active_task": None,
            "active_person": None,
            "active_event": None,
            "active_visual": None,
            "pending_incomplete_utterance": None,
            "pending_email_draft": None,
            "last_research": None,
        }

    def _prune_stale_context(self, max_age_seconds: float = 900.0, max_turns: int = 8) -> None:
        """Expires session context entities that exceed TTL (15 min) or turn threshold (8 turns)."""
        now = time.time()
        stale_slots = []
        for slot, meta in list(self._context_metadata.items()):
            age = now - meta.get("updated_at", now)
            turn_diff = self._turn_counter - meta.get("turn", self._turn_counter)
            if age > max_age_seconds or turn_diff > max_turns:
                stale_slots.append(slot)

        for slot in stale_slots:
            logger.info(f"[Alfred.Context] Expiring stale slot '{slot}' (age={now - self._context_metadata[slot]['updated_at']:.1f}s, turns={self._turn_counter - self._context_metadata[slot]['turn']})")
            if slot in self.session_context:
                self.session_context[slot] = None
            ent_key = slot.replace("active_", "")
            if ent_key in self.session_context.get("entities", {}):
                del self.session_context["entities"][ent_key]
            self._context_metadata.pop(slot, None)

    def _set_active_entity(self, slot: str, entity_type: str, data: Any) -> None:
        """Sets an active entity and records its freshness metadata."""
        self.session_context[slot] = data
        if "entities" not in self.session_context:
            self.session_context["entities"] = {}
        if data is not None:
            self.session_context["entities"][entity_type] = data
            self._context_metadata[slot] = {
                "updated_at": time.time(),
                "turn": self._turn_counter,
            }
        else:
            self.session_context["entities"].pop(entity_type, None)
            self._context_metadata.pop(slot, None)

    def get_history(self) -> List[Dict[str, str]]:
        """Returns the current conversation turns."""
        return list(self.conversation_history)

    def _get_compact_planner_history(self, max_turns: int = 6) -> List[Dict[str, str]]:
        """Returns concise conversation history turns to prevent prompt bloat.

        User turns are kept intact. Assistant turns are compacted to their essential factual
        or action summary (<150 characters / ~35 words) so pronoun and entity resolution
        works without spending hundreds of tokens on conversational pleasantries.
        """
        if not self.conversation_history:
            return []

        compact_turns = []
        for turn in self.conversation_history[-max_turns:]:
            role = turn.get("role", "user")
            content = turn.get("content", "").strip()
            if not content:
                continue

            if role == "assistant":
                if len(content) > 160:
                    clean = re.sub(
                        r"^(Certainly,?\s*sir\.?|Right away,?\s*sir\.?|At your service,?\s*sir\.?|Very good,?\s*sir\.?|Please note that I am currently referencing offline sandbox data,?\s*sir\.?)\s*",
                        "",
                        content,
                        flags=re.IGNORECASE,
                    ).strip()
                    first_sentence = clean.split(". ")[0]
                    if len(first_sentence) < 40 and ". " in clean:
                        first_sentence = ". ".join(clean.split(". ")[:2])
                    content = first_sentence[:140] + ("..." if len(first_sentence) > 140 else ".")
                compact_turns.append({"role": "assistant", "content": content})
            else:
                compact_turns.append({"role": "user", "content": content})

        return compact_turns

    async def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AlfredResponse:
        """Processes an incoming user query through the cognitive swarm."""
        t0 = time.perf_counter()
        cleaned_query = query.strip()

        self._turn_counter += 1
        self._prune_stale_context()

        if not cleaned_query:
            return AlfredResponse(
                speech_text="At your service, sir.",
                markdown_body="At your service, sir.",
                fast_path=True,
                latency_ms=0.0,
            )

        # 0. Spoken Normalization & Utterance Continuation
        normalized_query = normalize_spoken_emails(cleaned_query)

        pending_cutoff = self.session_context.get("pending_incomplete_utterance")
        if pending_cutoff:
            if re.search(r"\b(cancel|never mind|forget it|stop|ignore that)\b", normalized_query, re.I):
                self.session_context["pending_incomplete_utterance"] = None
                return AlfredResponse(
                    speech_text="Understood, sir. Previous instruction cancelled.",
                    markdown_body="Understood, sir. The incomplete instruction has been discarded.",
                    fast_path=True,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            logger.info(f"[Alfred] Merging cut-off utterance '{pending_cutoff}' with continuation '{normalized_query}'")
            cleaned_query = f"{pending_cutoff} {normalized_query}".strip()
            self.session_context["pending_incomplete_utterance"] = None
        else:
            cleaned_query = normalized_query

        # Incomplete / Cut-off Utterance Guard (<1ms)
        if detect_cut_off_utterance(cleaned_query):
            logger.info(f"[Alfred] Detected cut-off utterance: '{cleaned_query}'. Prompting user to continue.")
            self.session_context["pending_incomplete_utterance"] = cleaned_query
            last_token = cleaned_query.split()[-1] if cleaned_query.split() else ""
            return AlfredResponse(
                speech_text="It appears you were cut off, sir. Please continue whenever you are ready.",
                markdown_body=f"Your instruction appears incomplete (paused after *'{last_token}'*). Please continue speaking or typing to complete your request.",
                fast_path=True,
                latency_ms=(time.perf_counter() - t0) * 1000,
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

            # Record turn in conversation history
            self.conversation_history.append({"role": "user", "content": cleaned_query})
            self.conversation_history.append({"role": "assistant", "content": fp_result.speech_text})
            if len(self.conversation_history) > 16:
                self.conversation_history = self.conversation_history[-16:]

            return AlfredResponse(
                speech_text=fp_result.speech_text,
                markdown_body=fp_result.speech_text,
                hud_cards=cards,
                fast_path=True,
                plan_type="fast_path",
                specialist_actions=[{"agent": fp_result.intent, "action": fp_result.action, "params": fp_result.params}],
                latency_ms=elapsed_ms,
            )

        # ── 2. Stage 1: Swarm Planning (with compact multi-turn history & session context)
        compact_history = self._get_compact_planner_history(max_turns=6)
        plan, plan_ms = await self.planner.create_plan(
            cleaned_query,
            self.registry,
            history=compact_history,
            session_context=self.session_context,
        )

        # ── 3. Stage 2: Execution ────────────────────────────────────────────
        exec_result = await self.planner.execute_plan(plan, self.registry, context)

        # ── 4. Persona Synthesis & Output Evaluation ─────────────────────────
        # Check if specialist execution was purely financial (guarantee 100% numerical exactness)
        is_pure_finance = (
            bool(exec_result.specialist_results)
            and all(
                (getattr(r, "agent_name", "") == "finance" or r.action in ("get_balance", "log_transaction", "split_expense", "manage_debt"))
                for r in exec_result.specialist_results
            )
        )

        # Check if specialist execution was purely system vitals / network cluster status
        is_pure_system_status = (
            bool(exec_result.specialist_results)
            and all(
                (getattr(r, "agent_name", "") == "system" or r.action in ("get_system_vitals", "scan_network_devices", "list_processes"))
                for r in exec_result.specialist_results
            )
            and all(r.success for r in exec_result.specialist_results)
        )

        # Check for sandbox data presence across all outcomes
        has_sandbox_data = any(
            isinstance(r.data, dict) and (
                r.data.get("source") in ("sandbox", "sandbox_inbox")
                or (isinstance(r.data.get("emails"), list) and any(isinstance(e, dict) and e.get("source") == "sandbox" for e in r.data["emails"]))
                or (isinstance(r.data.get("events"), list) and any(isinstance(e, dict) and e.get("source") == "sandbox" for e in r.data["events"]))
                or (isinstance(r.data.get("calendar_events"), list) and any(isinstance(e, dict) and e.get("source") == "sandbox" for e in r.data["calendar_events"]))
            )
            for r in exec_result.specialist_results
        )

        # Check if the user query is asking an inquiry/question where synthesis is needed
        is_inquiry = any(
            w in cleaned_query.lower()
            for w in ("when", "what", "which", "who", "why", "how", "summarize", "tell me", "explain", "detail", "?")
        )

        # Single-specialist action synthesis bypass (<2ms, 0 tokens)
        can_bypass_synthesis = (
            len(exec_result.specialist_results) == 1
            and exec_result.specialist_results[0].success
            and bool(exec_result.specialist_results[0].speech_summary)
            and not is_inquiry
            and exec_result.specialist_results[0].action not in (
                "web_search", "inspect_webcam", "inspect_screen", "quick_scrape", "scrape_and_summarize",
                "read_email", "read_thread", "search_emails", "get_daily_agenda"
            )
            and not (isinstance(exec_result.specialist_results[0].data, dict) and exec_result.specialist_results[0].data.get("sources"))
        )

        if plan.plan_type == "direct" and exec_result.direct_response:
            raw_response = exec_result.direct_response
            eval_res = OutputEvaluator.evaluate(raw_response)
        elif is_pure_finance:
            # Guaranteed 100% numerical accuracy bypass: specialist speech_summary formatted without LLM rounding
            raw_response = " ".join([r.speech_summary for r in exec_result.specialist_results if r.speech_summary])
            eval_res = OutputEvaluator.evaluate(raw_response, exec_result.specialist_results)
        elif is_pure_system_status:
            # Guaranteed instantaneous (<5ms) system and cluster report: precise butler summaries without LLM delay
            raw_response = " ".join([r.speech_summary for r in exec_result.specialist_results if r.speech_summary])
            eval_res = OutputEvaluator.evaluate(raw_response, exec_result.specialist_results)
        elif can_bypass_synthesis:
            # Single-action synthesis bypass: saves ~1,800 tokens and 600ms latency
            raw_response = exec_result.specialist_results[0].speech_summary
            eval_res = OutputEvaluator.evaluate(raw_response, exec_result.specialist_results)
        else:
            # Build outcomes summary for Alfred synthesis
            outcome_lines = []
            for r in exec_result.specialist_results:
                status = "Success" if r.success else f"Failed ({r.error})"
                summary = r.speech_summary or ""

                extra_facts = []
                if isinstance(r.data, dict):
                    if "sources" in r.data and isinstance(r.data["sources"], list):
                        snippets = [
                            f"    * [{s.get('title', 'Source')}]: {s.get('snippet', '')}"
                            for s in r.data["sources"]
                            if s.get("snippet")
                        ]
                        if snippets:
                            extra_facts.append("  Verified Web Sources:\n" + "\n".join(snippets[:3]))
                    if r.data.get("answer"):
                        extra_facts.append(f"  Direct Answer/Fact: {r.data['answer']}")
                    if r.data.get("album") or r.data.get("movie"):
                        extra_facts.append(
                            f"  Track Metadata: Title='{r.data.get('track')}', "
                            f"Album/Film='{r.data.get('album') or r.data.get('movie')}', "
                            f"Artist='{r.data.get('artist')}'"
                        )
                    if "body" in r.data:
                        extra_facts.append(
                            f"  Email Content: Subject='{r.data.get('subject')}', From='{r.data.get('sender')}', Date='{r.data.get('date')}':\n"
                            f"  {str(r.data.get('body'))[:350]}"
                        )
                    elif "emails" in r.data and isinstance(r.data["emails"], list):
                        e_summaries = [
                            f"    * [{e.get('date', 'Recent')} - {e.get('sender_name') or e.get('sender')}]: Subject='{e.get('subject')}' | Preview='{e.get('snippet', '')[:120]}'"
                            for e in r.data["emails"][:3]
                        ]
                        if e_summaries:
                            extra_facts.append("  Matching Emails Found:\n" + "\n".join(e_summaries))
                    if "messages" in r.data and isinstance(r.data["messages"], list):
                        t_msgs = [
                            f"    * [{m.get('date', 'Recent')} - {m.get('sender_name', m.get('sender'))}]: {m.get('body', '')[:160]}"
                            for m in r.data["messages"]
                        ]
                        if t_msgs:
                            extra_facts.append("  Email Thread History:\n" + "\n".join(t_msgs))

                details_block = summary
                if extra_facts:
                    details_block = f"{summary}\n" + "\n".join(extra_facts)
                elif not details_block and r.data:
                    details_block = json.dumps(r.data)

                outcome_lines.append(f"- Action '{r.action}': {status} | Summary: {details_block}")

            outcomes_text = "\n".join(outcome_lines)
            now_dt = datetime.datetime.now().astimezone()
            current_datetime = now_dt.strftime("%A, %B %d, %Y, %I:%M %p %Z")
            current_day = now_dt.strftime("%A")
            synthesis_prompt = ALFRED_SYNTHESIS_PROMPT.format(
                query=cleaned_query,
                outcomes=outcomes_text,
                current_datetime=current_datetime,
                current_day=current_day,
            )

            messages: List[Dict[str, str]] = [
                {"role": "system", "content": synthesis_prompt},
            ]

            # Inject recent conversation turns for contextual continuity (compacted)
            compact_turns = self._get_compact_planner_history(max_turns=4)
            for turn in compact_turns:
                content = turn.get("content", "").strip()
                if content:
                    messages.append({"role": turn.get("role", "user"), "content": content})

            messages.append({"role": "user", "content": f"User query: '{cleaned_query}'. Please present this update to me in your persona."})

            raw_response, _ = await self.llm.generate_chat(messages, temperature=0.3, max_tokens=350)
            if not raw_response:
                summaries = [r.speech_summary for r in exec_result.specialist_results if r.speech_summary]
                raw_response = " ".join(summaries) if summaries else "I have completed the task, sir."
            eval_res = OutputEvaluator.evaluate(raw_response, exec_result.specialist_results)

        if has_sandbox_data:
            sandbox_notice = "[Sandbox Notice] I am currently referencing offline sandbox data as live account credentials are not yet connected, sir. "
            if raw_response and not raw_response.startswith("[Sandbox Notice]"):
                raw_response = sandbox_notice + raw_response
            if eval_res and hasattr(eval_res, "speech_text") and eval_res.speech_text:
                if not eval_res.speech_text.startswith("Please note that I am currently referencing offline sandbox data"):
                    eval_res.speech_text = "Please note that I am currently referencing offline sandbox data, sir. " + eval_res.speech_text
            if eval_res and hasattr(eval_res, "markdown_body") and eval_res.markdown_body:
                if not eval_res.markdown_body.startswith("[Sandbox Notice]"):
                    eval_res.markdown_body = sandbox_notice + eval_res.markdown_body

        total_elapsed_ms = (time.perf_counter() - t0) * 1000

        action_records = [
            {
                "agent": f"{r.agent_name}:{r.action}" if hasattr(r, "agent_name") and r.agent_name else r.action,
                "action": r.action,
                "success": r.success,
                "data": r.data,
                "error": r.error,
                "summary": r.speech_summary,
            }
            for r in exec_result.specialist_results
        ]

        # Update active session context from specialist execution results (with freshness TTL tracking)
        for r in exec_result.specialist_results:
            if not r.success or not isinstance(r.data, dict):
                continue
            
            # 1. Emails & Senders & Drafts
            if r.action == "draft_email":
                draft_info = {
                    "to": r.data.get("to"),
                    "subject": r.data.get("subject", "A brief note"),
                    "body": r.data.get("body", ""),
                }
                self._set_active_entity("pending_email_draft", "email_draft", draft_info)
                self.session_context["pending_email_draft"] = draft_info
            elif r.action == "send_email":
                self.session_context["pending_email_draft"] = None
                if "email_draft" in self.session_context.get("entities", {}):
                    del self.session_context["entities"]["email_draft"]
                self._context_metadata.pop("pending_email_draft", None)
            elif r.action in ("read_email", "read_thread") or ("sender" in r.data and "subject" in r.data):
                email_info = {
                    "id": r.data.get("id"),
                    "thread_id": r.data.get("thread_id", r.data.get("id")),
                    "sender": r.data.get("sender"),
                    "sender_name": r.data.get("sender_name") or str(r.data.get("sender", "")).split("<")[0].strip(),
                    "subject": r.data.get("subject"),
                }
                self._set_active_entity("active_email", "email", email_info)
                if email_info["sender_name"]:
                    self._set_active_entity("active_person", "person", email_info["sender_name"])
            elif r.action == "search_emails" and r.data.get("emails"):
                first_e = r.data["emails"][0]
                email_info = {
                    "id": first_e.get("id"),
                    "thread_id": first_e.get("thread_id", first_e.get("id")),
                    "sender": first_e.get("sender"),
                    "sender_name": first_e.get("sender_name") or str(first_e.get("sender", "")).split("<")[0].strip(),
                    "subject": first_e.get("subject"),
                }
                self._set_active_entity("active_email", "email", email_info)
                if email_info["sender_name"]:
                    self._set_active_entity("active_person", "person", email_info["sender_name"])

            # 2. Media / Audio
            if r.data.get("track") or (r.data.get("title") and any(k in r.data for k in ("artist", "album", "channel"))):
                track_info = {
                    "track": r.data.get("track") or r.data.get("title"),
                    "artist": r.data.get("artist") or r.data.get("channel"),
                    "album": r.data.get("album") or r.data.get("movie"),
                    "device": r.data.get("device"),
                }
                self._set_active_entity("active_track", "media", track_info)

            # 3. GitHub / Code Repos
            if r.data.get("repo"):
                repo_info = {
                    "repo": r.data.get("repo"),
                    "file": r.data.get("file") or r.data.get("file_path"),
                }
                self._set_active_entity("active_repo", "repo", repo_info)

            # 4. Tasks & Reminders
            if r.action in ("add_task", "set_reminder") or r.data.get("task"):
                task_data = r.data.get("task") if isinstance(r.data.get("task"), dict) else r.data
                task_info = {
                    "task_id": task_data.get("id") or task_data.get("task_id"),
                    "title": task_data.get("title") or task_data.get("reminder"),
                    "due_date": task_data.get("due_date") or task_data.get("time"),
                }
                self._set_active_entity("active_task", "task", task_info)

            # 5. Calendar Events
            if r.action == "schedule_event" or r.data.get("event"):
                event_data = r.data.get("event") if isinstance(r.data.get("event"), dict) else r.data
                event_info = {
                    "event_id": event_data.get("id"),
                    "summary": event_data.get("summary"),
                    "start_time": event_data.get("start_time"),
                }
                self._set_active_entity("active_event", "event", event_info)

            # 6. General Person Detection
            if r.data.get("person") or r.data.get("contact"):
                p_name = r.data.get("person") or r.data.get("contact")
                self._set_active_entity("active_person", "person", p_name)

            # 7. Vision / OCR Results — capture what Alfred just saw or read
            if r.action in ("inspect_webcam", "ocr_webcam", "inspect_screen", "ocr_screen") and r.success:
                visual_text = r.data.get("extracted_text") or r.data.get("description") or ""
                if visual_text:
                    visual_info = {
                        "action": r.action,
                        "source": r.data.get("source", "unknown"),
                        "text": visual_text[:800],
                    }
                    self._set_active_entity("active_visual", "visual", visual_info)

            # 8. Research & Web Search — save recent research for follow-up sharing or drafting
            if (r.action == "web_search" or (r.data.get("results") and r.data.get("query"))) and r.success:
                research_info = {
                    "query": r.data.get("query"),
                    "summary": r.data.get("summary") or r.speech_summary,
                    "results": r.data.get("results", []),
                }
                self._set_active_entity("last_research", "research", research_info)
                self.session_context["last_research"] = research_info

        # Update session conversation history
        self.conversation_history.append({"role": "user", "content": cleaned_query})
        if eval_res.speech_text:
            self.conversation_history.append({"role": "assistant", "content": eval_res.speech_text})
        if len(self.conversation_history) > 16:
            self.conversation_history = self.conversation_history[-16:]

        # Persist turns to conversation store asynchronously (non-blocking)
        if self._conversation_store is not None:
            try:
                intent_hint = plan.steps[0].get("action", "") if getattr(plan, "steps", None) else ""
                asyncio.create_task(
                    self._conversation_store.arecord_turn(
                        role="user",
                        content=cleaned_query,
                        intent=intent_hint,
                        session_id=self._session_id,
                    )
                )
                if eval_res.speech_text:
                    asyncio.create_task(
                        self._conversation_store.arecord_turn(
                            role="assistant",
                            content=eval_res.speech_text[:500],
                            intent=intent_hint,
                            summary=eval_res.speech_text[:200],
                            session_id=self._session_id,
                        )
                    )
            except Exception:
                pass

        return AlfredResponse(
            speech_text=eval_res.speech_text,
            markdown_body=eval_res.markdown_body,
            hud_cards=eval_res.hud_cards,
            fast_path=False,
            plan_type=plan.plan_type,
            specialist_actions=action_records,
            latency_ms=total_elapsed_ms,
        )
