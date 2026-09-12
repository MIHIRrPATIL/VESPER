"""VESPER Speech Normalization & Pronunciation Engine.

Shared cross-subsystem normalizer:
  1. Human pacing: natural breathing pauses at punctuation and clauses.
  2. Clear pronunciation: expansion of titles (Mr. -> Mister), abbreviations, and latinisms.
  3. Phonetic spelling of acronyms: ISBN -> I S B N, API -> A P I, OCR -> O C R, etc.
  4. Digit grouping: reads long serials, ISBNs, and barcodes as distinct digit groups.
  5. Unicode cleanup: removes non-breaking spaces, em-dashes, smart quotes, and markdown.
  6. HTML & Code stripping: strips raw HTML tags, script, and style blocks.
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

        # 2. HTML & Code stripping (prevent reading raw HTML doctypes, tags, or scripts)
        import html
        t = re.sub(r"<!DOCTYPE[^>]*>", " ", t, flags=re.IGNORECASE)
        t = re.sub(r"<(script|style|head|title)[^>]*>[\s\S]*?</\1>", " ", t, flags=re.IGNORECASE)
        t = re.sub(r"<[^>]+>", " ", t)
        t = html.unescape(t)
        t = re.sub(r"[\u200b-\u200f\ufeff\u034f\u00ad]", "", t)

        # 2b. Markdown stripping
        t = re.sub(r"```[a-zA-Z]*\n?.*?\n?```", "", t, flags=re.DOTALL)
        t = re.sub(r"`([^`]+)`", r"\1", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
        t = re.sub(r"\*([^*]+)\*", r"\1", t)
        t = re.sub(r"^[•\-\*]\s+", "", t, flags=re.MULTILINE)
        t = re.sub(r"#+\s*", "", t)

        # 3. Salutation / Opening Pacing
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

        # 7b. ISO Datetime and Time normalization (e.g. 2026-09-05T16:15:00+05:30 -> today at 4:15 PM)
        def _format_iso(m: re.Match) -> str:
            prefix = m.group(1) or ""
            iso_str = m.group(2)
            spoken = cls.format_spoken_datetime(iso_str)
            if not spoken:
                return m.group(0)
            if spoken.startswith("today") or spoken.startswith("tomorrow") or spoken.startswith("yesterday") or spoken.startswith("this") or spoken.startswith("on"):
                sp = " " if prefix and prefix.startswith(" ") else ""
                return f"{sp}{spoken}"
            return f"{prefix}{spoken}"

        t = re.sub(
            r"(\s*\bat\s+)?\b(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?)\b",
            _format_iso,
            t,
            flags=re.IGNORECASE,
        )

        # Strip any standalone residual timezone offsets like +05:30 or -07:00
        t = re.sub(r"[+-]\d{2}:\d{2}\b", "", t)

        # 8. Long digit sequences (e.g. ISBNs, tracking numbers) -> group digits
        def _format_digits(m: re.Match) -> str:
            digits = m.group(0)
            groups = [digits[i:i + 3] for i in range(0, len(digits), 3)]
            return ", ".join(groups)

        t = re.sub(r"\b\d{5,}\b", _format_digits, t)

        # 9. Clean up residual formatting
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r",\s*,+", ",", t)  # remove double commas
        t = re.sub(r"\(\s*([^)]+)\s*\)", r", \1, ", t)  # parentheticals into clause pauses

        return t

    @classmethod
    def normalize(cls, text: str) -> str:
        """Alias for normalize_for_speech."""
        return cls.normalize_for_speech(text)

    @classmethod
    def format_spoken_datetime(cls, dt_str: str) -> str:
        """Converts an ISO timestamp or date into articulate spoken English."""
        if not dt_str:
            return ""
        try:
            import datetime
            if "T" in dt_str or " " in dt_str or len(dt_str) == 10:
                dt = datetime.datetime.fromisoformat(dt_str)
                now = datetime.datetime.now().astimezone()
                today = now.date()
                d = dt.date()
                diff = (d - today).days

                hour = dt.hour
                minute = dt.minute
                h12 = hour % 12 or 12
                ampm = "AM" if hour < 12 else "PM"
                time_str = f"{h12}:{minute:02d} {ampm}" if minute else f"{h12} {ampm}"

                day = d.day
                suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
                month_name = d.strftime("%B")
                weekday = d.strftime("%A")

                # Date-only string (no time component)
                if "T" not in dt_str and " " not in dt_str:
                    if diff == 0:
                        return "today"
                    if diff == 1:
                        return "tomorrow"
                    if diff == -1:
                        return "yesterday"
                    if 2 <= diff <= 6:
                        return f"this {weekday}"
                    return f"on {weekday}, {month_name} {day}{suffix}"

                # Datetime with time component
                if diff == 0:
                    return f"today at {time_str}"
                elif diff == 1:
                    return f"tomorrow at {time_str}"
                elif diff == -1:
                    return f"yesterday at {time_str}"
                elif 2 <= diff <= 6:
                    return f"this {weekday} at {time_str}"
                else:
                    return f"on {weekday}, {month_name} {day}{suffix} at {time_str}"
        except Exception:
            pass
        return dt_str
