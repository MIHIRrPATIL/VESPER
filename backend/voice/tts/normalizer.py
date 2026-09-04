"""VESPER Speech Normalization & Pronunciation Engine.

Pre-processes agent responses before speech synthesis to ensure:
  1. Human pacing: natural breathing pauses at punctuation and clauses.
  2. Clear pronunciation: expansion of titles (Mr. -> Mister), abbreviations, and latinisms.
  3. Phonetic spelling of acronyms: ISBN -> I S B N, API -> A P I, OCR -> O C R, etc.
  4. Digit grouping: reads long serials, ISBNs, and barcodes as distinct digit groups.
  5. Unicode cleanup: removes non-breaking spaces, em-dashes, smart quotes, and markdown.
"""

from __future__ import annotations

import re


class SpeechNormalizer:
    """Normalizes natural text into speech-optimized phonetic transcriptions."""

    # Honorifics & titles
    HONORIFICS: dict[str, str] = {
        r"\bMr\b\.?": "Mister",
        r"\bMrs\b\.?": "Missus",
        r"\bMs\b\.?": "Mizz",
        r"\bDr\b\.?": "Doctor",
        r"\bProf\b\.?": "Professor",
        r"\bSr\b\.?": "Senior",
        r"\bJr\b\.?": "Junior",
        r"\bSt\b\.?": "Saint",
        r"\bCapt\b\.?": "Captain",
        r"\bGen\b\.?": "General",
        r"\bLt\b\.?": "Lieutenant",
        r"\bCol\b\.?": "Colonel",
    }

    # Common abbreviations & Latin phrases
    ABBREVIATIONS: dict[str, str] = {
        r"\be\.g\.,?": "for example,",
        r"\bi\.e\.,?": "that is,",
        r"\betc\b\.?": "etcetera",
        r"\bvs\b\.?": "versus",
        r"\bapprox\b\.?": "approximately",
        r"\best\b\.?": "estimated",
        r"\bmin\b\.?": "minutes",
        r"\bmins\b\.?": "minutes",
        r"\bsec\b\.?": "seconds",
        r"\bsecs\b\.?": "seconds",
        r"\bhr\b\.?": "hour",
        r"\bhrs\b\.?": "hours",
        r"\bno\b\.?": "number",
        r"\bnos\b\.?": "numbers",
        r"\bvol\b\.?": "volume",
        r"\bvols\b\.?": "volumes",
        r"\bdept\b\.?": "department",
        r"\bgovt\b\.?": "government",
    }

    # Acronyms to space out letter-by-letter for articulate enunciation
    SPELL_OUT_ACRONYMS: list[str] = [
        "ISBN", "OCR", "TTS", "LLM", "API", "UI", "HUD", "STT",
        "PDF", "GPU", "CPU", "RAM", "SBC", "OS", "URL", "HTML",
        "CSS", "JSON", "SQL", "V4L2", "REST", "CLI", "SDK", "FAQ",
        "ID", "AI",
    ]

    # Proper names to capitalize cleanly
    NAME_CASING: dict[str, str] = {
        r"\bVESPER\b": "Vesper",
        r"\bSHODH\b": "Shodh",
    }

    @classmethod
    def normalize_for_speech(cls, text: str) -> str:
        """Transforms formatted text into a natural, spoken-English transcript."""
        if not text:
            return ""

        t = text

        # 1. Unicode & whitespace normalization
        t = t.replace("\u202f", " ").replace("\u00a0", " ")
        t = t.replace("\u2011", "-")  # non-breaking hyphen
        t = t.replace("—", ", ").replace("–", ", ")  # em/en dashes -> comma pause
        t = t.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")

        # 2. Markdown stripping
        t = re.sub(r"```[a-zA-Z]*\n?.*?\n?```", "", t, flags=re.DOTALL)
        t = re.sub(r"`([^`]+)`", r"\1", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
        t = re.sub(r"\*([^*]+)\*", r"\1", t)
        t = re.sub(r"^[•\-\*]\s+", "", t, flags=re.MULTILINE)
        t = re.sub(r"#+\s*", "", t)

        # 3. Salutation / Opening Pacing
        # "sir. The book..." -> "Sir, The book..." (avoids awkward 1-word sentence split)
        t = re.sub(r"^sir\.\s+", "Sir, ", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=[.!?])\s+sir\.\s+", ", sir. ", t, flags=re.IGNORECASE)

        # 4. Honorifics and Titles
        for pat, rep in cls.HONORIFICS.items():
            t = re.sub(pat, rep, t)

        # 5. Abbreviations
        for pat, rep in cls.ABBREVIATIONS.items():
            t = re.sub(pat, rep, t)

        # 6. Proper names
        for pat, rep in cls.NAME_CASING.items():
            t = re.sub(pat, rep, t)

        # 7. Letter-by-letter Acronyms
        for acr in cls.SPELL_OUT_ACRONYMS:
            spaced = " ".join(list(acr))
            t = re.sub(rf"\b{acr}\b", spaced, t)

        # 8. Long digit sequences (e.g. ISBNs, tracking numbers) -> group digits
        def _format_digits(m: re.Match) -> str:
            digits = m.group(0)
            # Group into chunks of 3 or 4 with comma pauses
            groups = [digits[i:i + 3] for i in range(0, len(digits), 3)]
            return ", ".join(groups)

        t = re.sub(r"\b\d{5,}\b", _format_digits, t)

        # 9. Clean up residual formatting
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r",\s*,+", ",", t)  # remove double commas
        t = re.sub(r"\(\s*([^)]+)\s*\)", r", \1, ", t)  # parentheticals into clause pauses

        return t
