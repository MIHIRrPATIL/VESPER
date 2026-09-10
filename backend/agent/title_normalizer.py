"""VESPER Title Normalizer & Action Classifier.

Deterministic post-processing safety net for VESPER's TaskSpecialist & SwarmPlanner.

Solves:
  1. Title Normalization: Strips conversational filler ("please", "remind me to", "go", "to")
     and duplicated trailing times/dates ("at 5.45 today") so titles are clean sentence-cased strings.
  2. Action-Type Classification: Distinguishes between:
     - "reminder": Time-bound alerts (due times, clock alarms, "remind me")
     - "event": Scheduled meetings, appointments, calendar slots
     - "task": Open-ended todos without specific time alarms
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal, Optional

ActionType = Literal["reminder", "task", "event"]

# --------------------------------------------------------------------------
# 1. Action-type classification
# --------------------------------------------------------------------------

_EVENT_TRIGGERS = [
    r"\b(add|create|new|schedule|book|set\s*up)\s+(a\s+|an\s+)?(event|meeting|call|appointment|session|calendar\s+entry|slot)\b",
    r"\bbook\s+(a |an )?(meeting|slot|appointment)\b",
    r"\bput\s+.*\s+on\s+(my\s+)?calendar\b",
    r"\bset up a (meeting|call)\b",
    r"\bmeeting with\b",
    r"\bevent\s+(at|on|for)\b",
    r"\bcalendar\s+event\b",
]

_REMINDER_TRIGGERS = [
    r"\bremind me\b",
    r"\bset a reminder\b",
    r"\bdon'?t let me forget\b",
    r"\bping me\b",
    r"\bnotify me\b",
]

_TASK_TRIGGERS = [
    r"\badd\s+.*\s+to\s+(my\s+)?(tasks?|to-?do)\b",
    r"\bcreate a task\b",
    r"\bi need to\b",
    r"\badd a task\b",
]

_HAS_CLOCK_TIME = re.compile(
    r"\b\d{1,2}[:.]\d{2}\s*(am|pm)?\b|\b\d{1,2}\s*(am|pm)\b|\b\d{1,2}\s*o'?clock\b",
    re.IGNORECASE,
)


def classify_action_type(utterance: str) -> ActionType:
    """Classifies user utterance into 'event', 'reminder', or 'task'."""
    text = utterance.lower()

    for pat in _EVENT_TRIGGERS:
        if re.search(pat, text):
            return "event"
    for pat in _REMINDER_TRIGGERS:
        if re.search(pat, text):
            return "reminder"
    for pat in _TASK_TRIGGERS:
        if re.search(pat, text):
            return "task"

    # No explicit trigger phrase matched. A clock time without calendar language
    # indicates a time-bound nudge (reminder), not an open-ended task.
    if _HAS_CLOCK_TIME.search(text):
        return "reminder"

    return "task"


# --------------------------------------------------------------------------
# 2. Title normalization
# --------------------------------------------------------------------------

_LEADING_FILLER = re.compile(
    r"^("
    r"please\s+|"
    r"remind me(\s+to)?\s+|"
    r"set a reminder(\s+to)?\s+|"
    r"(?:add|create|schedule|set up)\s+(?:an?\s+)?(?:event|meeting|call|session|appointment|calendar\s+entry)\s*(?:(?:at|by|on|for)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:o'?clock)?\s*(?:am|pm)?\s*(?:today|tomorrow|tonight)?\s*(?:that|to|for|:|-)?\s*|\s*(?:that|to|for|:|-)\s*)?|"
    r"add (a\s+|an\s+)?(task|event|meeting)(\s+to)?\s+|"
    r"i need to\s+|"
    r"can you\s+|"
    r"could you\s+|"
    r"go and\s+|"
    r"go\s+|"
    r"to\s+"
    r")",
    re.IGNORECASE,
)

_TRAILING_DATE = r"(today|tomorrow|tonight|this (?:morning|afternoon|evening)|(?:on|by)\s+\w+day)"
_TRAILING_TIME = r"(?:at|by)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:o'?clock)?\s*(?:am|pm)?"
_TRAILING_TIME_DATE = re.compile(
    rf"\s*(?:(?:{_TRAILING_DATE})\s*(?:{_TRAILING_TIME})?|(?:{_TRAILING_TIME})\s*(?:{_TRAILING_DATE})?)\s*$",
    re.IGNORECASE,
)

_TIME_PATTERNS = [
    # "tomorrow at 3pm", "today at 5.45", "Friday at 10am", "today at 9 o'clock"
    r"\b((?:today|tomorrow|tonight|this (?:morning|afternoon|evening)|(?:on|by)\s+\w+day)\s+(?:at|by)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:o'?clock)?\s*(?:am|pm)?)\b",
    # "at 5.45 today", "at 3pm tomorrow", "at 9 o'clock today", "by 5pm on Friday"
    r"\b((?:at|by)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:o'?clock)?\s*(?:am|pm)?\s*(?:today|tomorrow|tonight|this (?:morning|afternoon|evening)|(?:on\s+)?\w+day)?)\b",
    # "9 o'clock today", "9 oclock", "9 o'clock"
    r"\b(\d{1,2}(?:[:.]\d{2})?\s*o'?clock\s*(?:am|pm)?\s*(?:today|tomorrow|tonight)?)\b",
    # "in 15 minutes", "in 2 hours"
    r"\b(in\s+\d+\s+(?:minutes?|mins?|hours?|hrs?|days?))\b",
    # "at 5.45", "at 3pm", "by 10:30am", "at 9 o'clock"
    r"\b((?:at|by)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:o'?clock)?\s*(?:am|pm)?)\b",
    # "5.45 today", "3pm tomorrow", "5:45 pm"
    r"\b(\d{1,2}[:.]\d{2}\s*(?:am|pm)?\s*(?:today|tomorrow)?)\b",
    r"\b(\d{1,2}\s*(?:am|pm)\s*(?:today|tomorrow)?)\b",
    # bare "tomorrow morning", "this evening"
    r"\b(tomorrow (?:morning|afternoon|evening)|today|tomorrow|tonight)\b",
]


def extract_time_phrase(text: str) -> Optional[str]:
    """Extracts conversational time expression (e.g. '5.45 today', 'tomorrow at 3pm', 'in 15 minutes')."""
    if not text:
        return None
    for pat in _TIME_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            clean = m.group(1).strip().rstrip(".,!? ")
            if clean.lower().startswith("at "):
                clean = clean[3:].strip()
            return clean
    return None


def normalize_title(raw_text: str) -> str:
    """Normalizes raw extracted title or reminder fragment into clean, sentence-cased text.

    Examples:
      "go pick up my mom at 5.45 today" -> "Pick up my mom"
      "to deploy the backend by Friday" -> "Deploy the backend"
      "please remind me to buy groceries" -> "Buy groceries"
    """
    if not raw_text:
        return ""

    text = raw_text.strip()

    # Peel off leading conversational filler
    prev = None
    while prev != text:
        prev = text
        text = _LEADING_FILLER.sub("", text, count=1).strip()

    # Peel off trailing date/time fragments duplicated elsewhere
    prev = None
    while prev != text:
        prev = text
        text = text.rstrip(".,!? ")
        text = _TRAILING_TIME_DATE.sub("", text).strip()

    text = text.rstrip(".,!? ")
    text = re.sub(r"\s+", " ", text)

    if not text:
        return raw_text.strip()

    # Sentence-case the first letter while preserving acronyms and proper nouns
    return text[0].upper() + text[1:]


# --------------------------------------------------------------------------
# 3. Combined entry point
# --------------------------------------------------------------------------

@dataclass
class NormalizedAction:
    action_type: ActionType
    title: str
    original_utterance: str
    time_phrase: Optional[str] = None


def build_action(utterance: str, extracted_fragment: Optional[str] = None) -> NormalizedAction:
    """Builds a NormalizedAction with verified action_type, normalized title, and time anchor."""
    clean_frag = extracted_fragment if extracted_fragment is not None else utterance
    return NormalizedAction(
        action_type=classify_action_type(utterance),
        title=normalize_title(clean_frag),
        original_utterance=utterance,
        time_phrase=extract_time_phrase(utterance),
    )
