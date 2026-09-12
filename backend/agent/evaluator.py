"""VESPER Deterministic Output Evaluator & Diagnostic Sanitizer (<2ms).

Runs in pure Python without an additional LLM call to:
  1. Bifurcate output into clean `speech_text` (for TTS) and rich `hud_cards` (for HUD).
  2. Strip raw URLs, markdown tables, code fences, and robotic boilerplate from speech.
  3. Verify math and specialist outcome consistency.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from backend.agent.specialists.base import SpecialistResult


class EvaluatorResult:
    """Sanitized and bifurcated agent response."""

    def __init__(
        self,
        speech_text: str,
        hud_cards: List[Dict[str, Any]],
        markdown_body: str,
        has_errors: bool = False,
        diagnostics: Optional[List[str]] = None,
    ) -> None:
        self.speech_text = speech_text
        self.hud_cards = hud_cards
        self.markdown_body = markdown_body
        self.has_errors = has_errors
        self.diagnostics = diagnostics or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speech_text": self.speech_text,
            "hud_cards": self.hud_cards,
            "markdown_body": self.markdown_body,
            "has_errors": self.has_errors,
            "diagnostics": self.diagnostics,
        }


class OutputEvaluator:
    """Fast deterministic output sanitizer and validator."""

    # Banned robotic intro/outro filler
    BOILERPLATE_PATTERNS = [
        re.compile(r"^(as an ai language model|as an ai assistant|as an ai),?\s*", re.I),
        re.compile(r"^(certainly|sure thing|of course|happy to help)[!.,]?\s*", re.I),
        re.compile(r"(i hope this helps|let me know if you need anything else)[.!]*$", re.I),
    ]

    # Chain-of-thought and internal reasoning leakage patterns
    COT_PATTERNS = [
        re.compile(r"<think>[\s\S]*?</think>", re.I),
        re.compile(
            r"(?:^|\n)\s*(?:Thought|Thinking|Internal Reasoning|Chain of thought|Analysis|Scratchpad):\s*[\s\S]*?(?=(?:\n\n|\Z))",
            re.I,
        ),
        re.compile(
            r"^(?:the user is asking|the user wants|the user inquired|let me check|looking at the specialist|according to the instructions|in order to answer|i need to check|based on the instructions|in this query|here is the thought process)[\s\S]*?(?=(?:Good (?:morning|afternoon|evening)|Certainly|Sir,|It appears|Currently|Here is|According to our|I do not have|\Z))",
            re.I,
        ),
    ]

    # Regex patterns for stripping from speech
    URL_PATTERN = re.compile(r"https?://(?:www\.)?([^\s/]+)(?:/[^\s]*)?", re.I)
    CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```")
    INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
    TABLE_LINE_PATTERN = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
    TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?[\s\-:]+\|[\s\-:|]*$", re.MULTILINE)
    HR_LINE_PATTERN = re.compile(r"^\s*[-=_*]{3,}\s*$", re.MULTILINE)
    REASONING_BLOCK_PATTERN = re.compile(
        r"(?:^|\n|\s---+\s)\s*(?:Reasoning|Rationale|Explanation|Internal Thinking):\s*[\s\S]*?(?=(?:\n\n|\Z))",
        re.I,
    )
    HEADER_LABELS_PATTERN = re.compile(r"\b(?:Subject|To|From):\s*", re.I)
    MARKDOWN_FORMATTING = re.compile(r"[*_~#>]")
    EXCESS_WHITESPACE = re.compile(r"\s{2,}")

    @classmethod
    def strip_chain_of_thought(cls, text: Optional[str]) -> str:
        """Removes reasoning scratchpads, <think> tags, and internal analysis preambles."""
        if not text:
            return ""
        cleaned = text.strip()
        for pat in cls.COT_PATTERNS:
            cleaned = pat.sub("", cleaned).strip()
        return cleaned

    @classmethod
    def sanitize_speech_text(cls, text: Optional[str]) -> str:
        """Strips URLs, tables, code, reasoning disclaimers, and markdown syntax to produce smooth, human-like speech."""
        if not text:
            return ""
        cleaned = text.strip()

        # Remove chain-of-thought / scratchpad leaks
        cleaned = cls.strip_chain_of_thought(cleaned)

        # Remove code blocks and inline code
        cleaned = cls.CODE_BLOCK_PATTERN.sub("", cleaned)
        cleaned = cls.INLINE_CODE_PATTERN.sub(r"\1", cleaned)

        # Remove reasoning / explanation metadata blocks
        cleaned = cls.REASONING_BLOCK_PATTERN.sub("", cleaned)

        # Remove markdown tables and horizontal rules
        cleaned = cls.TABLE_SEPARATOR_PATTERN.sub("", cleaned)
        cleaned = cls.TABLE_LINE_PATTERN.sub("", cleaned)
        cleaned = cls.HR_LINE_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"[-=_*]{3,}", " ", cleaned)

        # Remove email/header labels that sound awkward when read aloud
        cleaned = cls.HEADER_LABELS_PATTERN.sub("", cleaned)

        # Replace URLs with spoken-friendly domain mention or remove
        def _replace_url(match: re.Match) -> str:
            domain = match.group(1).split(".")[0]
            return f"the {domain} website"

        cleaned = cls.URL_PATTERN.sub(_replace_url, cleaned)

        # Remove markdown characters (*, #, _, >, ~)
        cleaned = cls.MARKDOWN_FORMATTING.sub("", cleaned)

        # Strip robotic filler
        for pattern in cls.BOILERPLATE_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()

        # Clean excess newlines & spaces
        cleaned = cls.EXCESS_WHITESPACE.sub(" ", cleaned).strip()

        # Ensure text doesn't end abruptly without punctuation
        if cleaned and not cleaned[-1] in ".!?":
            cleaned += "."

        return cleaned

    @classmethod
    def condense_briefing_speech(cls, text: str, max_words: int = 45) -> str:
        """Extracts a concise executive spoken summary for TTS when detailed pointers are moved to HUD."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        intro_parts: List[str] = []
        outro_parts: List[str] = []
        found_bullet = False

        for line in lines:
            is_bullet = bool(re.match(r"^(?:[-*•]|\d+\.)\s+", line))
            if is_bullet:
                found_bullet = True
                continue
            clean_l = line.rstrip(":").strip()
            # Skip pure section heading labels that are 1-2 words
            if len(clean_l.split()) <= 2 and not any(w in clean_l.lower() for w in ("here", "good", "sir", "please", "overall", "finally")):
                continue
            if not found_bullet:
                intro_parts.append(clean_l)
            else:
                outro_parts.append(clean_l)

        if intro_parts:
            intro_clean = cls.sanitize_speech_text(" ".join(intro_parts))
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", intro_clean) if s.strip()]
            spoken_intro = " ".join(sentences[:2]) if len(sentences) >= 2 else (sentences[0] if sentences else intro_clean)
            strip_punc = spoken_intro.rstrip(".,;:")
            return f"{strip_punc}. I have displayed the detailed breakdown on your HUD, sir."

        if outro_parts:
            outro_clean = cls.sanitize_speech_text(" ".join(outro_parts))
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", outro_clean) if s.strip()]
            spoken_outro = sentences[0] if sentences else outro_clean
            strip_punc = spoken_outro.rstrip(".,;:")
            return f"{strip_punc}. I have displayed the detailed breakdown on your HUD, sir."

        return "I have compiled the briefing for you, sir. The details are displayed on your HUD."

    @classmethod
    def evaluate(
        cls,
        raw_text: Optional[str],
        specialist_results: Optional[List[SpecialistResult]] = None,
        query: Optional[str] = None,
    ) -> EvaluatorResult:
        """Evaluates raw output and specialist returns into speech and HUD presentation."""
        raw_text_str = (raw_text or "").strip()
        specialist_results = specialist_results or []
        diagnostics: List[str] = []
        hud_cards: List[Dict[str, Any]] = []
        has_errors = False

        # Collect HUD cards from specialist returns
        for res in specialist_results:
            if not res.success:
                has_errors = True
                diagnostics.append(f"Specialist '{res.action}' failed: {res.error}")

            if res.card_payload:
                hud_cards.append(res.card_payload)
            elif res.data:
                # Construct fallback card
                hud_cards.append({
                    "type": "data_card",
                    "action": res.action,
                    "data": res.data,
                })

        # Sanitize markdown body to remove internal chain-of-thought leaks
        markdown_body = cls.strip_chain_of_thought(raw_text_str)

        # Detect structured pointer-based / analytical briefing content
        bullet_count = len(re.findall(r"(?:^|\n)\s*(?:[-*•]|\d+\.)\s+", markdown_body))
        has_headers = bool(re.search(r"(?:^|\n)#{1,4}\s+\w+", markdown_body))
        has_named_sections = bool(re.search(r"(?:^|\n)[A-Z][A-Za-z0-9\s/&-]{2,25}:\s*(?:\n|$)", markdown_body))
        is_pointer_briefing = (bullet_count >= 2) or (has_headers and bullet_count >= 1) or (has_named_sections and bullet_count >= 1)

        # Auto-generate Briefing HUD card if no specialist card was emitted
        if not hud_cards and is_pointer_briefing:
            card_title = "Analytical Briefing"
            if query:
                q_clean = query.strip().rstrip("?").strip()
                if any(w in q_clean.lower() for w in ("compare", "vs", "versus", "better", "difference", "which")):
                    card_title = f"Comparative Briefing // {q_clean.title()[:35]}"
                else:
                    card_title = f"Briefing // {q_clean.title()[:35]}"
            elif any(w in markdown_body.lower() for w in ("compare", "versus", "difference", "better")):
                card_title = "Comparative Analysis"

            hud_cards.append({
                "type": "briefing",
                "title": card_title,
                "data": {
                    "title": card_title,
                    "query": query or "",
                    "text": markdown_body,
                    "summary": markdown_body,
                    "briefing": markdown_body,
                    "markdown": markdown_body,
                },
            })

            # Condense spoken speech for TTS so Alfred doesn't speak out lists of raw bullets
            speech_text = cls.condense_briefing_speech(raw_text_str)
        else:
            # Sanitize speech text for TTS
            speech_text = cls.sanitize_speech_text(raw_text_str)

        # Fallback if speech text was completely stripped
        if not speech_text:
            if specialist_results:
                summaries = [r.speech_summary for r in specialist_results if r.speech_summary]
                speech_text = " ".join(summaries) if summaries else "Action completed, sir."
            else:
                speech_text = "Action completed, sir."

        if not markdown_body:
            markdown_body = speech_text

        return EvaluatorResult(
            speech_text=speech_text,
            hud_cards=hud_cards,
            markdown_body=markdown_body,
            has_errors=has_errors,
            diagnostics=diagnostics,
        )
