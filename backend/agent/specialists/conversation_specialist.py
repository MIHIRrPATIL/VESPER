"""VESPER Conversational Specialist.

Implements humanized chit-chat, empathetic banter, historical dialogue recall,
and proactive check-ins grounded in the persistent ConversationStore.

Registered under domain 'conversation'.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult

logger = logging.getLogger("vesper.agent.specialists.conversation")


class ConversationSpecialist(BaseSpecialist):
    """Specialist for humanized dialogue, chit-chat, and historical conversation recall."""

    @property
    def name(self) -> str:
        return "conversation"

    @property
    def description(self) -> str:
        return "Engages in humanized chit-chat, empathetic banter, and recalls past conversations."

    def get_capabilities(self) -> str:
        return (
            "Handles casual conversation, greetings, how-are-you, philosophical banter, "
            "and historical dialogue recall ('what did we talk about', 'what have we worked on recently'). "
            "Maintains persistent memory across sessions."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "chit_chat",
                "description": (
                    "Engages in warm, humanized British butler conversation including greetings, "
                    "banter, check-ins, and philosophical exchange. Use for casual queries like "
                    "'how are you', 'good morning alfred', 'what do you think about...', 'tell me a fact'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The user's conversational input.",
                        },
                        "topic_hint": {
                            "type": "string",
                            "description": "Optional topic hint extracted from the query.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "recall_conversations",
                "description": (
                    "Searches and summarizes historical conversation turns from persistent memory. "
                    "Use when user asks 'what did we work on', 'what have we discussed', "
                    "'remind me of previous conversations', or references past topics."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query or topic to recall (e.g. 'Vesper project', 'music', 'tasks').",
                        },
                        "time_range": {
                            "type": "string",
                            "description": "Optional time range: 'today', 'week', 'month'.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "proactive_check_in",
                "description": (
                    "Synthesizes a warm proactive check-in greeting based on recent activity, "
                    "past topics, and active session context. Useful for 'good morning' or "
                    "unprompted check-in scenarios."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        if action == "chit_chat":
            return await self._chit_chat(params, context)
        elif action == "recall_conversations":
            return await self._recall_conversations(params)
        elif action == "proactive_check_in":
            return await self._proactive_check_in(context)
        return SpecialistResult(
            success=False,
            action=action,
            error=f"Unknown conversation action: '{action}'.",
        )

    async def _chit_chat(
        self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        from backend.agent.llm import LLMClient
        from backend.data.conversation_store import conversation_store

        query = params.get("query", "")
        topic_hint = params.get("topic_hint", "")

        recent = conversation_store.get_recent_history(limit=8)
        topics = conversation_store.get_recent_topics(days=7)

        now = datetime.datetime.now()
        hour = now.hour
        if hour < 12:
            time_greeting = "Good morning"
        elif hour < 17:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"

        history_snippet = ""
        if recent:
            user_turns = [r["content"][:100] for r in recent if r["role"] == "user"][-3:]
            if user_turns:
                history_snippet = "Recent topics from our conversations: " + "; ".join(user_turns) + ". "

        topics_str = ", ".join(topics[:5]) if topics else ""
        topic_line = f"Areas we have explored together recently: {topics_str}. " if topics_str else ""

        system_prompt = (
            f"You are Alfred, an impeccably articulate British personal assistant with a warm, poised character. "
            f"Today is {now.strftime('%A, %B %d, %Y')} and the time is {now.strftime('%I:%M %p')}. "
            f"{time_greeting}, sir.\n\n"
            f"{history_snippet}"
            f"{topic_line}"
            f"Persona directives:\n"
            f"- Speak as a thoughtful, empathetic, and subtly witty British butler.\n"
            f"- Reference past conversation context naturally where appropriate.\n"
            f"- Keep responses warm but concise (2-4 sentences maximum).\n"
            f"- Never use emojis, exclamation marks, or generic AI phrases.\n"
            f"- If the user greets you, greet them back naturally and offer a relevant observation or check-in.\n"
        )
        if topic_hint:
            system_prompt += f"- Gently weave in the topic '{topic_hint}' if relevant.\n"

        llm = LLMClient()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        response, _ = await llm.generate_chat(messages, temperature=0.7, max_tokens=200)

        if not response:
            response = f"{time_greeting}, sir. How may I be of assistance today?"

        card = {
            "type": "conversation_card",
            "query": query,
            "response": response,
            "recent_topics": topics[:5],
        }

        return SpecialistResult(
            success=True,
            action="chit_chat",
            speech_summary=response,
            data={"response": response, "recent_topics": topics, "context": history_snippet},
            card_payload=card,
        )

    async def _recall_conversations(self, params: Dict[str, Any]) -> SpecialistResult:
        from backend.data.conversation_store import conversation_store

        query = params.get("query", "")
        time_range = params.get("time_range", "week")

        days_map = {"today": 1, "week": 7, "month": 30}
        days = days_map.get(time_range, 7)

        results = conversation_store.search_conversations(query, limit=6)
        topics = conversation_store.get_recent_topics(days=days)

        if not results and not topics:
            speech = (
                "I am afraid I could not find any notable discussions matching your query in our recent history, sir. "
                "Our conversations have not been extensively logged yet."
            )
            return SpecialistResult(
                success=True,
                action="recall_conversations",
                speech_summary=speech,
                data={"results": [], "topics": []},
            )

        lines = []
        for r in results[:4]:
            ts = r.get("timestamp", "")[:16]
            content = r.get("content", "")[:120]
            role = r.get("role", "user")
            if role == "user":
                lines.append(f"[{ts}] You asked: \"{content}\"")
            else:
                lines.append(f"[{ts}] I responded: \"{content}\"")

        topics_str = ", ".join(topics[:6]) if topics else "nothing specific on record"

        speech_parts = [f"Here is what I recall from our recent conversations, sir."]
        if lines:
            speech_parts.append("Selected exchanges: " + "; ".join(lines[:3]) + ".")
        speech_parts.append(f"Topics we have touched on: {topics_str}.")

        speech = " ".join(speech_parts)

        card = {
            "type": "conversation_recall_card",
            "query": query,
            "results": results,
            "topics": topics,
        }

        return SpecialistResult(
            success=True,
            action="recall_conversations",
            speech_summary=speech,
            data={"results": results, "topics": topics},
            card_payload=card,
        )

    async def _proactive_check_in(self, context: Optional[Dict[str, Any]] = None) -> SpecialistResult:
        from backend.data.conversation_store import conversation_store

        summary = conversation_store.get_conversation_summary_for_briefing()
        check_ins = conversation_store.get_suggested_check_ins(limit=2)

        now = datetime.datetime.now()
        hour = now.hour
        if hour < 12:
            greeting_time = "morning"
        elif hour < 17:
            greeting_time = "afternoon"
        else:
            greeting_time = "evening"

        lines = [f"Good {greeting_time}, sir."]
        if summary:
            lines.append(summary)
        if check_ins:
            last = check_ins[0].get("content", "")[:100]
            if last:
                lines.append(f"I recall you were enquiring about '{last}' recently. Shall we pick up from there?")
        else:
            lines.append("I am at your disposal whenever you are ready to begin.")

        speech = " ".join(lines)

        return SpecialistResult(
            success=True,
            action="proactive_check_in",
            speech_summary=speech,
            data={"summary": summary, "check_ins": check_ins},
            card_payload={
                "type": "conversation_card",
                "response": speech,
                "recent_topics": conversation_store.get_recent_topics(days=3),
            },
        )
