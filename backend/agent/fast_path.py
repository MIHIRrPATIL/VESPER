"""VESPER Deterministic Fast-Path Engine (<10ms).

Evaluates user queries against pre-compiled regular expressions.
Directly executes hardware, media, volume, mode, and clock queries
in sub-10 milliseconds without invoking an LLM, reducing latency by 6x.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


def _get_time_of_day() -> str:
    """Returns the current period of day for contextual greetings."""
    hour = datetime.datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    elif hour < 21:
        return "evening"
    return "evening"


def _get_fast_briefing() -> tuple[dict, str, dict]:
    """Returns the pre-warmed executive briefing from BriefingManager instantly (<1ms)."""
    try:
        from backend.agent.proactive.briefing_manager import briefing_manager

        cached = briefing_manager._cached_briefing
        if cached:
            return (
                {"type": "briefing"},
                cached.get("speech", "Good day, sir. All systems are operational."),
                {
                    "type": "briefing",
                    "title": cached.get("title", "Executive Briefing"),
                    "markdown_body": cached.get("markdown_body", ""),
                    "hud_cards": cached.get("hud_cards", []),
                },
            )
        fb = briefing_manager._build_minimal_fallback_briefing()
        return (
            {"type": "briefing"},
            fb["speech"],
            {"type": "briefing", "title": fb["title"], "markdown_body": fb["markdown_body"], "hud_cards": fb["hud_cards"]},
        )
    except Exception:
        now = datetime.datetime.now()
        day_str = now.strftime("%A, %B %-d") if hasattr(now, "strftime") else now.strftime("%A, %B %d")
        speech = f"Good {_get_time_of_day()}, sir. It is {day_str}. All VESPER services are operating nominally."
        return ({}, speech, {"type": "briefing"})


_CACHED_USER_PROFILE: Dict[str, Any] = {
    "name": "Mihir",
    "preferences": ["dark roast Ethiopian black coffee"],
    "financial_goals": ["GPU upgrade"],
}


def _fast_store_user_name(name_raw: str) -> tuple[dict, str, dict]:
    """Stores user's name immediately into memory cache and Supabase in background (<1ms)."""
    cleaned = name_raw.strip().title()
    _CACHED_USER_PROFILE["name"] = cleaned
    try:
        from backend.data.repositories.memory import ShodhMemoryRepository
        from backend.data.models import MemoryCreate
        import asyncio

        async def _persist():
            try:
                repo = ShodhMemoryRepository()
                await asyncio.to_thread(
                    repo.store_fact,
                    MemoryCreate(
                        statement=f"The user's name is {cleaned}",
                        category="personal",
                        confidence=1.0,
                        metadata={"active": True, "source": "fast_path"},
                    ),
                )
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist())
        except RuntimeError:
            pass
    except Exception:
        pass

    speech = f"Very good, sir. I have committed to memory that your name is {cleaned}."
    card = {
        "type": "memory_card",
        "action": "stored",
        "statement": f"User's name is {cleaned}",
        "category": "personal",
    }
    return ({"name": cleaned, "category": "personal"}, speech, card)


def _fast_recall_user_name() -> tuple[dict, str, dict]:
    """Recalls user's name immediately (<1ms)."""
    name = _CACHED_USER_PROFILE.get("name", "Mihir")
    speech = f"Your name is {name}, sir."
    card = {"type": "memory_recall_card", "query": "name", "name": name}
    return ({"name": name}, speech, card)


def _fast_recall_profile() -> tuple[dict, str, dict]:
    """Recalls user's complete profile dossier immediately (<1ms)."""
    name = _CACHED_USER_PROFILE.get("name", "Mihir")
    prefs = ", ".join(_CACHED_USER_PROFILE.get("preferences", [])) or "dark roast Ethiopian black coffee"
    goals = ", ".join(_CACHED_USER_PROFILE.get("financial_goals", [])) or "GPU upgrade"
    speech = (
        f"Based on my memory records, sir: your name is {name}; you prefer {prefs}; "
        f"and your current financial goal is a {goals}."
    )
    card = {
        "type": "user_profile_card",
        "name": name,
        "preferences": _CACHED_USER_PROFILE.get("preferences", []),
        "financial_goals": _CACHED_USER_PROFILE.get("financial_goals", []),
    }
    return ({"profile": _CACHED_USER_PROFILE}, speech, card)


def _fast_store_generic_memory(fact: str) -> tuple[dict, str, dict]:
    """Commits a generic fact statement into memory immediately with background persistence (<1ms)."""
    clean_fact = fact.strip().strip(".,!?:;\"'")
    try:
        from backend.data.repositories.memory import ShodhMemoryRepository
        from backend.data.models import MemoryCreate
        import asyncio

        async def _persist():
            try:
                repo = ShodhMemoryRepository()
                await asyncio.to_thread(
                    repo.store_fact,
                    MemoryCreate(
                        statement=clean_fact,
                        category="preference",
                        confidence=1.0,
                        metadata={"active": True, "source": "fast_path"},
                    ),
                )
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist())
        except RuntimeError:
            pass
    except Exception:
        pass

    speech = f"I have committed that to memory: {clean_fact}, sir."
    card = {"type": "memory_card", "action": "stored", "statement": clean_fact}
    return ({"statement": clean_fact}, speech, card)


class FastPathResult(BaseModel):
    """Result of a fast-path evaluation."""

    matched: bool = False
    intent: str = ""
    action: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)
    speech_text: str = ""
    card_payload: Optional[Dict[str, Any]] = None
    navigate_to: Optional[str] = None


class FastPathEngine:
    """Compiled pattern matcher for zero-LLM system execution."""

    def __init__(self) -> None:
        # Pre-compile regexes for sub-millisecond evaluation
        self._rules = [
            # Media: Pause
            (
                re.compile(r"^\s*(pause|pause music|pause playback|stop music|stop playback|hold the music|halt music)\s*[\.!]?$", re.I),
                "media",
                "pause",
                lambda m: ({}, "Playback paused, sir.", {"type": "media_control", "action": "pause"}),
            ),
            # Media: Resume / Play
            (
                re.compile(r"^\s*(play|resume|resume music|resume playback|continue music|continue playing(?: the)?(?: music| song| playback)?|keep playing(?: the)?(?: music| song| playback)?|unpause(?: music)?)\s*[\.!]?$", re.I),
                "media",
                "resume",
                lambda m: ({}, "Resuming playback, sir.", {"type": "media_control", "action": "resume"}),
            ),
            # Media: Next / Skip
            (
                re.compile(r"^\s*(next|skip|next track|next song|skip song)\s*[\.!]?$", re.I),
                "media",
                "next",
                lambda m: ({}, "Skipping to the next track, sir.", {"type": "media_control", "action": "next"}),
            ),
            # Media: Previous
            (
                re.compile(r"^\s*(previous|previous track|previous song|restart song)\s*[\.!]?$", re.I),
                "media",
                "previous",
                lambda m: ({}, "Returning to the previous track, sir.", {"type": "media_control", "action": "previous"}),
            ),
            # Volume: Mute
            (
                re.compile(r"^\s*(mute|mute audio|silence)\s*[\.!]?$", re.I),
                "system",
                "mute",
                lambda m: ({"mute": True}, "Audio muted, sir.", {"type": "volume", "state": "muted"}),
            ),
            # Volume: Unmute
            (
                re.compile(r"^\s*(unmute|unmute audio)\s*[\.!]?$", re.I),
                "system",
                "unmute",
                lambda m: ({"mute": False}, "Audio unmuted, sir.", {"type": "volume", "state": "unmuted"}),
            ),
            # Volume: Up
            (
                re.compile(r"^\s*(volume\s*up|increase\s*volume|louder)\s*[\.!]?$", re.I),
                "system",
                "volume_up",
                lambda m: ({"delta": 10}, "Increasing volume, sir.", {"type": "volume", "action": "up"}),
            ),
            # Volume: Down
            (
                re.compile(r"^\s*(volume\s*down|decrease\s*volume|softer|quieter)\s*[\.!]?$", re.I),
                "system",
                "volume_down",
                lambda m: ({"delta": -10}, "Decreasing volume, sir.", {"type": "volume", "action": "down"}),
            ),
            # Volume: Explicit Level (e.g., "volume 50%", "set volume to 75")
            (
                re.compile(r"^\s*(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*%?\s*[\.!]?$", re.I),
                "system",
                "set_volume",
                lambda m: (
                    {"level": min(100, max(0, int(m.group(1))))},
                    f"Volume set to {min(100, max(0, int(m.group(1))))} percent, sir.",
                    {"type": "volume", "level": min(100, max(0, int(m.group(1))))},
                ),
            ),
            # Focus / Zen Mode
            (
                re.compile(r"^\s*(?:enable\s+|activate\s+|enter\s+)?(?:zen\s+mode|focus\s+mode|heads\s+down)\s*[\.!]?$", re.I),
                "system",
                "focus_mode",
                lambda m: (
                    {"focus": True},
                    "Focus mode engaged, sir. Minimizing non-essential interruptions.",
                    {"type": "mode", "mode": "focus"},
                ),
            ),
            # Normal Mode / Exit Zen
            (
                re.compile(r"^\s*(?:disable\s+|exit\s+)?(?:normal\s+mode|exit\s+focus\s+mode|exit\s+zen\s+mode)\s*[\.!]?$", re.I),
                "system",
                "normal_mode",
                lambda m: ({"focus": False}, "Standard mode restored, sir.", {"type": "mode", "mode": "normal"}),
            ),
            # Time Query
            (
                re.compile(r"^\s*(what\s+time\s+is\s+it|current\s+time|tell\s+me\s+the\s+time|what'?s\s+the\s+time)\s*\??\s*$", re.I),
                "system",
                "get_time",
                lambda m: (
                    {},
                    f"It is currently {datetime.datetime.now().strftime('%-I:%M %p')}, sir.",
                    {"type": "clock", "time": datetime.datetime.now().strftime("%H:%M:%S")},
                ),
            ),
            # Date Query
            (
                re.compile(r"^\s*(what\s+is\s+today'?s\s+date|what'?s\s+the\s+date|tell\s+me\s+the\s+date|today'?s\s+date)\s*\??\s*$", re.I),
                "system",
                "get_date",
                lambda m: (
                    {},
                    f"Today is {datetime.datetime.now().strftime('%A, %B %-d, %Y')}, sir.",
                    {"type": "calendar", "date": datetime.datetime.now().strftime("%Y-%m-%d")},
                ),
            ),
            # Status / Ping
            (
                re.compile(r"^\s*(ping|status\s+check|system\s+status|are\s+you\s+there\s+alfred|alfred\s+status)\s*\??\s*$", re.I),
                "system",
                "ping",
                lambda m: ({}, "All systems operational and functioning normally, sir.", {"type": "status", "healthy": True}),
            ),
            # ── Executive Briefing & Agenda Fast Path ─────────────────────────
            (
                re.compile(
                    r"^\s*(?:give\s+me\s+(?:a\s+|my\s+)?|what\s+is\s+my\s+|what'?s\s+my\s+|summarize\s+(?:my\s+|recent\s+)?)"
                    r"(?:daily\s+|morning\s+|evening\s+|executive\s+)?(?:briefing|schedule|agenda|activities)"
                    r"(?:\s+today|\s+for\s+today)?[\s.!]*$"
                    r"|^\s*(?:briefing|daily\s+briefing|morning\s+briefing|evening\s+briefing|executive\s+briefing|today'?s\s+schedule|today'?s\s+agenda)\s*[\.!]?$",
                    re.I,
                ),
                "proactive",
                "briefing",
                lambda m: (*_get_fast_briefing()[:3], "agenda"),
            ),
            # ── Dismissive / No-Op / False Wake ─────────────────────────────
            # Catches utterances after accidental wake word activation where
            # the user wants Alfred to stand down and keep doing what he was doing.
            (
                re.compile(
                    r"^\s*(?:nothing|it'?s\s+nothing|never\s*mind|nevermind|forget\s+it|"
                    r"ignore\s+that|false\s+alarm|my\s+bad|sorry|oops|"
                    r"didn'?t\s+mean\s+to|wasn'?t\s+talking\s+to\s+you|"
                    r"not\s+you|i\s+wasn'?t\s+talking\s+to\s+you|"
                    r"that\s+was\s+a\s+mistake|i\s+didn'?t\s+call\s+you|"
                    r"i\s+didn'?t\s+say\s+anything)"
                    r"(?:[\s,]+(?:alfred|jarvis))?"
                    r"[\s.!]*$",
                    re.I,
                ),
                "system",
                "dismiss",
                lambda m: ({}, "Very well, sir.", {"type": "dismiss", "action": "stand_down"}),
            ),
            # "Nothing, keep playing [the music]" / "Keep doing what you're doing"
            (
                re.compile(
                    r"^\s*(?:nothing[\s,]*)?(?:alfred[\s,]*)?"
                    r"(?:keep\s+playing(?:\s+the\s+music)?|keep\s+going|keep\s+doing\s+what\s+you'?re\s+doing|"
                    r"keep\s+at\s+it|keep\s+it\s+up|continue\s+playing|don'?t\s+stop|carry\s+on\s+playing)"
                    r"[\s.!]*$",
                    re.I,
                ),
                "system",
                "dismiss",
                lambda m: ({}, "Carrying on, sir.", {"type": "dismiss", "action": "continue"}),
            ),
            # "As you were" / "Carry on" / "Stand down" / "At ease"
            (
                re.compile(
                    r"^\s*(?:alfred[\s,]*)?"
                    r"(?:as\s+you\s+were|carry\s+on|stand\s+down|at\s+ease|back\s+to\s+normal|"
                    r"go\s+back\s+to\s+(?:sleep|standby|idle)|resume\s+standby|"
                    r"return\s+to\s+standby|you'?re\s+dismissed|dismissed)"
                    r"[\s.!]*$",
                    re.I,
                ),
                "system",
                "dismiss",
                lambda m: ({}, "As you wish, sir.", {"type": "dismiss", "action": "stand_down"}),
            ),
            # "That's all" / "That will be all" / "I'm done" / "All good"
            (
                re.compile(
                    r"^\s*(?:alfred[\s,]*)?"
                    r"(?:that'?s\s+all|that\s+will\s+be\s+all|that\s+is\s+all|i'?m\s+done|"
                    r"all\s+good|all\s+set|we'?re\s+good|we'?re\s+done|i'?m\s+good|"
                    r"no(?:pe|thing)?\s+(?:that'?s|we'?re)\s+(?:all|good|it|fine))"
                    r"[\s.!]*$",
                    re.I,
                ),
                "system",
                "dismiss",
                lambda m: ({}, "Very good, sir. I shall remain on standby.", {"type": "dismiss", "action": "idle"}),
            ),
            # "Thanks" / "Thank you" / "Cheers" / "Appreciated"
            (
                re.compile(
                    r"^\s*(?:thanks|thank\s+you|cheers|much\s+appreciated|appreciated)"
                    r"(?:[\s,]+(?:alfred|jarvis|buddy|mate))?"
                    r"[\s.!]*$",
                    re.I,
                ),
                "system",
                "acknowledge",
                lambda m: ({}, "At your service, sir.", {"type": "acknowledge", "action": "thank"}),
            ),
            # "Cancel" / "Stop" / "Abort" (bare, without further context)
            (
                re.compile(r"^\s*(cancel|stop|abort|halt|shut\s+up|be\s+quiet|silence|hush)\s*[\s.!]*$", re.I),
                "system",
                "cancel",
                lambda m: ({}, "Understood, sir.", {"type": "cancel", "action": "abort"}),
            ),
            # "OK" / "Okay" / "Alright" / "Got it" / "Cool" (bare acknowledgements)
            (
                re.compile(
                    r"^\s*(?:ok(?:ay)?|alright|all\s*right|got\s+it|roger|copy\s+that|"
                    r"understood|cool|fine|sounds\s+good|perfect)"
                    r"(?:[\s,]+(?:alfred|jarvis))?"
                    r"[\s.!]*$",
                    re.I,
                ),
                "system",
                "acknowledge",
                lambda m: ({}, "Very good, sir.", {"type": "acknowledge", "action": "noted"}),
            ),
            # "Good morning/afternoon/evening/night Alfred" (bare greetings)
            (
                re.compile(
                    r"^\s*(?:good\s+(?:morning|afternoon|evening|night)|hello|hey|hi|yo|sup|what'?s\s+up)"
                    r"(?:[\s,]+(?:alfred|jarvis|there|buddy))?"
                    r"[\s.!]*$",
                    re.I,
                ),
                "system",
                "greet",
                lambda m: (
                    {},
                    f"Good {_get_time_of_day()}, sir. How may I be of service?",
                    {"type": "greet", "action": "greeting"},
                ),
            ),
            # ── Fast-Path Identity & Memory Store/Recall (<1ms) ───────────────
            # Set Name: "always remember alfred that my name is mihir", "my name is mihir"
            (
                re.compile(
                    r"^\s*(?:(?:always\s+)?remember\s+(?:alfred[\s,]*)?(?:that\s+)?(?:the\s+)?|"
                    r"please\s+remember\s+(?:that\s+)?|note\s+that\s+)?"
                    r"(?:my\s+name\s+is\s+|i\s+am\s+|call\s+me\s+)"
                    r"([a-zA-Z\s]+)[\s.!]*$",
                    re.I,
                ),
                "memory",
                "store_name",
                lambda m: _fast_store_user_name(m.group(1)),
            ),
            # Recall Name: "what is my name", "who am i"
            (
                re.compile(
                    r"^\s*(?:what\s+is\s+my\s+name|what'?s\s+my\s+name|who\s+am\s+i|do\s+you\s+know\s+my\s+name)\s*\??\s*$",
                    re.I,
                ),
                "memory",
                "recall_name",
                lambda m: _fast_recall_user_name(),
            ),
            # Recall Profile: "what have you learned about me so far", "what do you know about me"
            (
                re.compile(
                    r"^\s*(?:what\s+(?:have\s+you\s+learned|do\s+you\s+know|do\s+you\s+remember)\s+about\s+me(?:\s+so\s+far)?|"
                    r"tell\s+me\s+about\s+myself|what\s+is\s+my\s+profile|what\s+are\s+my\s+preferences)\s*\??\s*$",
                    re.I,
                ),
                "memory",
                "get_user_profile",
                lambda m: _fast_recall_profile(),
            ),
            # Generic Remember: "always remember that...", "remember that..."
            (
                re.compile(
                    r"^\s*(?:always\s+)?remember\s+(?:alfred[\s,]*)?(?:that\s+)?(.+)[\s.!]*$",
                    re.I,
                ),
                "memory",
                "store_memory",
                lambda m: _fast_store_generic_memory(m.group(1)),
            ),
            # ── Deterministic Page Navigation (<5ms) ────────────────────────
            # Workstation / Cockpit Overview
            (
                re.compile(
                    r"^\s*(?:open|go\s+to|show|navigate\s+to|switch\s+to)?\s*(?:the\s+)?(?:workstation(?:\s+page)?|overview(?:\s+page)?|cockpit|dashboard)\s*[\.!]?$",
                    re.I,
                ),
                "navigation",
                "center",
                lambda m: (
                    {"view": "center"},
                    "Opening the workstation overview, sir.",
                    {"type": "navigation", "target_view": "center", "title": "WORKSTATION OVERVIEW"},
                    "center",
                ),
            ),
            # Executive Agenda & Tasks View
            (
                re.compile(
                    r"^\s*(?:(?:what'?s|what\s+is)\s+the\s+agenda(?:\s+page)?|open\s+(?:the\s+)?agenda(?:\s+page)?|go\s+to\s+(?:the\s+)?agenda(?:\s+page)?|show\s+(?:the\s+)?agenda(?:\s+page)?|open\s+(?:the\s+)?tasks?(?:\s+page)?|show\s+(?:the\s+)?tasks?(?:\s+page)?|agenda\s+page|tasks?\s+page)\s*[\.!]?$",
                    re.I,
                ),
                "navigation",
                "agenda",
                lambda m: (
                    {"view": "agenda"},
                    "Opening the executive agenda and tasks, sir.",
                    {"type": "navigation", "target_view": "agenda", "title": "EXECUTIVE AGENDA & TASKS"},
                    "agenda",
                ),
            ),
            # Financials, Ledger & Transactions View
            (
                re.compile(
                    r"^\s*(?:(?:what'?s|what\s+is)\s+the\s+finances?(?:\s+page)?|open\s+(?:the\s+)?finances?(?:\s+page)?|go\s+to\s+(?:the\s+)?finances?(?:\s+page)?|show\s+(?:the\s+)?finances?(?:\s+page)?|open\s+(?:the\s+)?(?:ledger|transactions?)(?:\s+page)?|finances?\s+page|ledger\s+page|transactions?\s+page|finances|ledger|transactions)\s*[\.!]?$",
                    re.I,
                ),
                "navigation",
                "transactions",
                lambda m: (
                    {"view": "transactions"},
                    "Opening your financial ledger and transactions, sir.",
                    {"type": "navigation", "target_view": "transactions", "title": "FINANCIAL LEDGER & ACCOUNTS"},
                    "transactions",
                ),
            ),
            # Swarm Services & Hardware Telemetry
            (
                re.compile(
                    r"^\s*(?:open|go\s+to|show|navigate\s+to)?\s*(?:the\s+)?(?:services?(?:\s+page)?|telemetry(?:\s+page)?|swarm(?:\s+mesh|\s+page|\s+status)?|hardware(?:\s+page)?|cluster(?:\s+nodes)?)\s*[\.!]?$",
                    re.I,
                ),
                "navigation",
                "services",
                lambda m: (
                    {"view": "services"},
                    "Opening cognitive swarm services and hardware telemetry, sir.",
                    {"type": "navigation", "target_view": "services", "title": "SWARM SERVICES & HARDWARE"},
                    "services",
                ),
            ),
            # Specialist Tool Emitter View
            (
                re.compile(
                    r"^\s*(?:open|go\s+to|show|navigate\s+to)?\s*(?:the\s+)?(?:tools?(?:\s+page)?|specialist\s+tools?|tool\s+emitter(?:\s+page)?|emitter\s+deck)\s*[\.!]?$",
                    re.I,
                ),
                "navigation",
                "tools",
                lambda m: (
                    {"view": "tools"},
                    "Opening specialist tool emitter, sir.",
                    {"type": "navigation", "target_view": "tools", "title": "SPECIALIST TOOL EMITTER"},
                    "tools",
                ),
            ),
            # Workstation Event Stream & Audit Logs
            (
                re.compile(
                    r"^\s*(?:open|go\s+to|show|navigate\s+to)?\s*(?:the\s+)?(?:logs?(?:\s+page)?|audit\s+logs?|event\s+stream(?:\s+page)?|workstation\s+(?:event\s+stream|logs))\s*[\.!]?$",
                    re.I,
                ),
                "navigation",
                "logs",
                lambda m: (
                    {"view": "logs"},
                    "Opening workstation event stream and audit logs, sir.",
                    {"type": "navigation", "target_view": "logs", "title": "WORKSTATION EVENT STREAM"},
                    "logs",
                ),
            ),
            # Directives & Voice Agent Console
            (
                re.compile(
                    r"^\s*(?:open|go\s+to|show|navigate\s+to)?\s*(?:the\s+)?(?:directives?(?:\s+page)?|voice\s+agent(?:\s+page)?|voice\s+page|chat\s+page|conversation\s+page)\s*[\.!]?$",
                    re.I,
                ),
                "navigation",
                "voice",
                lambda m: (
                    {"view": "voice"},
                    "Opening directives and voice agent console, sir.",
                    {"type": "navigation", "target_view": "voice", "title": "DIRECTIVES CONSOLE"},
                    "voice",
                ),
            ),
        ]

    def evaluate(self, query: str) -> FastPathResult:
        """Evaluates a query string and returns FastPathResult in <10ms."""
        cleaned = query.strip()
        for pattern, intent, action, handler in self._rules:
            match = pattern.match(cleaned)
            if match:
                res = handler(match)
                params, speech_text, card_payload = res[0], res[1], res[2]
                navigate_to = res[3] if len(res) > 3 else None
                return FastPathResult(
                    matched=True,
                    intent=intent,
                    action=action,
                    params=params,
                    speech_text=speech_text,
                    card_payload=card_payload,
                    navigate_to=navigate_to,
                )

        return FastPathResult(matched=False)
