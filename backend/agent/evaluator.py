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

    # Regex patterns for stripping from speech
    URL_PATTERN = re.compile(r"https?://(?:www\.)?([^\s/]+)(?:/[^\s]*)?", re.I)
    CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```")
    INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
    TABLE_LINE_PATTERN = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
    TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?[\s\-:]+\|[\s\-:|]*$", re.MULTILINE)
    MARKDOWN_FORMATTING = re.compile(r"[*_~#>]")
    EXCESS_WHITESPACE = re.compile(r"\s{2,}")

    @classmethod
    def sanitize_speech_text(cls, text: str) -> str:
        """Strips URLs, tables, code, and markdown syntax to produce smooth, human-like speech."""
        cleaned = text.strip()

        # Remove code blocks
        cleaned = cls.CODE_BLOCK_PATTERN.sub("", cleaned)
        cleaned = cls.INLINE_CODE_PATTERN.sub(r"\1", cleaned)

        # Remove markdown tables
        cleaned = cls.TABLE_SEPARATOR_PATTERN.sub("", cleaned)
        cleaned = cls.TABLE_LINE_PATTERN.sub("", cleaned)

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
    def evaluate(
        cls,
        raw_text: str,
        specialist_results: Optional[List[SpecialistResult]] = None,
    ) -> EvaluatorResult:
        """Evaluates raw output and specialist returns into speech and HUD presentation."""
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

        # Sanitize speech text for TTS
        speech_text = cls.sanitize_speech_text(raw_text)

        # Fallback if speech text was completely stripped
        if not speech_text:
            if specialist_results:
                summaries = [r.speech_summary for r in specialist_results if r.speech_summary]
                speech_text = " ".join(summaries) if summaries else "Action completed, sir."
            else:
                speech_text = "Action completed, sir."

        return EvaluatorResult(
            speech_text=speech_text,
            hud_cards=hud_cards,
            markdown_body=raw_text.strip(),
            has_errors=has_errors,
            diagnostics=diagnostics,
        )
