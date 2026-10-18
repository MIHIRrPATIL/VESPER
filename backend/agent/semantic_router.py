"""Local semantic similarity router for zero-token intent classification.

Uses all-MiniLM-L6-v2 via FastEmbed to classify natural language queries against
canonical intent prototypes in ~10ms on CPU without LLM roundtrips or Groq quota usage.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SemanticIntent(str, Enum):
    """Categorical semantic intents detected via sentence embedding similarity."""

    HANDHELD_OBJECT_RESEARCH = "handheld_object_research"
    VERIFY_RESEARCH = "verify_research"
    EMAIL_THREAD = "email_thread"
    UNREAD_EMAILS = "unread_emails"
    SONG_ORIGIN = "song_origin"
    DAILY_AGENDA = "daily_agenda"
    FINANCE_BALANCE = "finance_balance"
    SYSTEM_STATUS = "system_status"
    MOBILE_NOTIFICATIONS = "mobile_notifications"
    BATTERY_STATUS = "battery_status"
    NONE = "none"


# Canonical prototype examples per intent
INTENT_PROTOTYPES: Dict[SemanticIntent, List[str]] = {
    SemanticIntent.HANDHELD_OBJECT_RESEARCH: [
        "tell me about what I am holding",
        "what is this book I am holding in front of the camera",
        "describe what I am holding in my hand",
        "can you read this object in my hand and tell me about it",
        "what is this item in front of the camera",
        "tell me more about this thing I am showing you",
        "summarize the book in my hand",
        "what does this paper in my hand say",
        "tell me about the book I am holding",
        "what is this product in my hand",
        "can you read what is on this paper in my hand",
        "can you tell me about the details of the receipt that I am holding",
        "tell me about the details of the receipt that I am holding in my hands",
        "what does the receipt in my hand say",
        "read the details of the receipt I am holding",
        "read this bill or receipt in my hand",
        "what is written on the receipt I am holding",
        "check the receipt in my hand",
        "read this invoice or paper I am holding",
        "what are the details of the document I am holding",
        "inspect what is in my grip",
        "read this card or flyer in my hand",
        "what is written on this slip in my hand",
        "check this note or card in my hand",
        "can you read this package or bottle in my hand",
    ],
    SemanticIntent.VERIFY_RESEARCH: [
        "are you sure? try again",
        "no try again",
        "that is wrong, look it up",
        "search properly",
        "nah that ain't it",
        "you are hallucinating, check again",
        "double check that online",
        "verify this with a web search",
        "try researching it again",
        "incorrect, please search for it",
        "that is not right, search the web",
        "please research it more carefully",
        "wrong, check again",
        "I don't think that's right, check Google",
        "are you certain about that, please verify",
        "double check that fact online",
        "check your facts with a search engine",
        "please verify that information on the internet",
    ],
    SemanticIntent.EMAIL_THREAD: [
        "check the entire email thread",
        "show me the full email chain",
        "read the whole conversation thread",
        "check the most recent conversation chain with them",
        "show me the email thread we were discussing",
        "get the full email thread",
        "view the conversation history for this email",
        "show me the entire thread",
    ],
    SemanticIntent.UNREAD_EMAILS: [
        "check my unread emails",
        "do I have any unread emails",
        "show me my unread emails",
        "check my inbox for unread messages",
        "read my latest unread emails",
        "what new unread emails do I have",
        "list my unread messages",
        "check for new unread emails",
        "check my emails",
        "do I have any new emails",
    ],
    SemanticIntent.SONG_ORIGIN: [
        "what movie is this song from",
        "which film is this track from",
        "who sang this song playing right now",
        "who directed the movie this song is from",
        "what soundtrack is this track from",
        "which movie features this current song",
    ],
    SemanticIntent.DAILY_AGENDA: [
        "what is on my schedule today",
        "give me my daily briefing",
        "show me my agenda for today",
        "what meetings do I have lined up",
        "check my calendar and tasks for today",
        "what are my priorities for today",
        "what do I have planned today",
        "what are my tasks for today",
        "what are my tasks today",
        "what tasks do I have today",
        "show my tasks for today",
        "check my tasks today",
        "what does my day look like",
        "what do I have on my plate today",
        "run down my schedule for today",
        "what are my to-dos today",
        "brief me on my day today",
        "give me my morning rundown",
        "what is on my itinerary today",
    ],
    SemanticIntent.FINANCE_BALANCE: [
        "what is my bank balance",
        "how much money do I have",
        "check my financial balance",
        "what is my net worth",
        "show me my account balance",
        "how much cash is in my accounts",
        "view my financial balance",
        "check my current funds",
    ],
    SemanticIntent.SYSTEM_STATUS: [
        "how is the system running",
        "show me system vitals",
        "what is the cpu and ram usage",
        "how much cpu and memory is left",
        "system resource check",
        "check system vitals",
        "how is my computer running",
        "show system telemetry",
        "give me a brief system and cluster status report",
        "system and cluster status report",
        "system and cluster status",
        "cluster status report",
        "how is the cluster running",
        "how are my workstation resources looking",
        "processor and RAM usage",
        "machine health and diagnostics",
        "system telemetry and performance",
        "system load and resource consumption",
    ],
    SemanticIntent.MOBILE_NOTIFICATIONS: [
        "what notifications did I get on my phone",
        "check my phone notifications",
        "do I have any notifications on my phone",
        "show my mobile notifications",
        "any new alerts on my phone",
        "check my mobile alerts",
        "what alerts arrived on my phone",
        "any messages or notifications on my phone",
        "summarize my phone notifications",
        "check notifications from my phone",
        "did I get any notifications",
        "any alerts on whatsapp or slack",
    ],
    SemanticIntent.BATTERY_STATUS: [
        "what is my phone battery",
        "check battery on my devices",
        "how much battery does my phone have",
        "is my phone charging",
        "what is the battery level on my laptop",
        "check battery status",
        "how much charge is left on my phone",
        "battery levels across my devices",
        "are any of my devices low on battery",
        "is my phone plugged in",
    ],
    SemanticIntent.NONE: [
        "who is holding the world record for the marathon",
        "who holds the world record in the 100 meters",
        "who was holding the baby in that movie",
        "they are holding a meeting in room four",
        "we are holding a conference next week",
        "holding company quarterly revenue",
        "what is holding up the train",
        "who is holding the event tonight",
        "holding elections next month",
        "holding a press briefing tomorrow",
        "holding a briefing for reporters",
        "holding an emergency briefing",
        "check my screen time for today",
        "how much screen time have I logged today",
        "screen protector installation tutorial",
        "read my daily horoscope",
        "what is my horoscope for today",
        "check astrological forecast",
        "send an email to my manager",
        "compose a message to Sarah",
        "draft a reply to John",
        "transfer money to my savings account",
        "pay my credit card bill online",
        "who is the battery supplier for Tesla",
        "system of linear equations in algebra",
        "how does an internal combustion engine work",
        "what is the population of Tokyo",
        "tell me a funny joke",
        "write a python script to parse json",
    ],
}

# Similarity thresholds for matching (calibrated by error cost:
# side-effect and physical actions require strict thresholds plus contrast margins,
# while safe zero-side-effect lookups are calibrated for recall)
DEFAULT_THRESHOLDS: Dict[SemanticIntent, float] = {
    SemanticIntent.HANDHELD_OBJECT_RESEARCH: 0.50,  # Side-effect intent, protected by hard negative contrast prototypes + contrast margin
    SemanticIntent.VERIFY_RESEARCH: 0.48,           # Triggers external web search
    SemanticIntent.EMAIL_THREAD: 0.52,
    SemanticIntent.UNREAD_EMAILS: 0.50,             # Read-only lookup
    SemanticIntent.SONG_ORIGIN: 0.50,
    SemanticIntent.DAILY_AGENDA: 0.46,              # Read-only lookup
    SemanticIntent.FINANCE_BALANCE: 0.50,           # Read-only lookup
    SemanticIntent.SYSTEM_STATUS: 0.46,             # Read-only lookup
    SemanticIntent.MOBILE_NOTIFICATIONS: 0.48,      # Read-only lookup
    SemanticIntent.BATTERY_STATUS: 0.50,            # Read-only lookup
    SemanticIntent.NONE: 0.45,                      # Contrast prototype baseline
}

# Regression and generalization canary fixtures.
# Contains both unseen paraphrases (not in INTENT_PROTOTYPES) and adversarial near-misses.
SELF_TEST_CASES: List[Tuple[str, SemanticIntent]] = [
    # False-positive / adversarial near-miss rejections
    ("who is holding the world record for the marathon", SemanticIntent.NONE),
    ("they are holding a meeting in room 4", SemanticIntent.NONE),
    ("check my screen time for today", SemanticIntent.NONE),
    ("read my daily horoscope", SemanticIntent.NONE),
    ("don't check my email", SemanticIntent.NONE),
    ("what is my bank balance and read my unread emails", SemanticIntent.NONE),
    # Paraphrased intent matches (not in prototype bank)
    ("can you examine the book I am holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("that statement is incorrect, please search the web", SemanticIntent.VERIFY_RESEARCH),
    ("pull up the full conversation history for this message", SemanticIntent.EMAIL_THREAD),
    ("are there any fresh messages in my inbox", SemanticIntent.UNREAD_EMAILS),
    ("from which film is this soundtrack from", SemanticIntent.SONG_ORIGIN),
    ("what obligations are scheduled for me today", SemanticIntent.DAILY_AGENDA),
    ("how much money is currently in my checking account", SemanticIntent.FINANCE_BALANCE),
    ("display resource vitals for this workstation", SemanticIntent.SYSTEM_STATUS),
    ("did any push alerts arrive on my mobile device", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("how much power is left in my phone", SemanticIntent.BATTERY_STATUS),
]

# Regex for detecting coordinating conjunctions that indicate multiple distinct commands
COORDINATION_PATTERN = re.compile(
    r"\b(?:"
    r"and\s+(?:also\s+)?(?:check|read|show|list|get|tell|play|what|how|look|open|send|draft|search|run|start)\b"
    r"|then\s+(?:check|read|show|list|get|play|tell|what|how|look|open|send|start)\b"
    r"|also\s+(?:check|read|show|list|get|tell|play|look|what|how)\b"
    r"|as\s+well\s+as\s+(?:check|read|show|list|get|tell|play)\b"
    r"|plus\s+(?:check|read|show|list|get|tell|play)\b"
    r")",
    re.IGNORECASE,
)

# Regex for detecting explicit negations that small embedding models confound
NEGATION_PATTERN = re.compile(
    r"\b(don't|dont|do not|never|stop|cancel|avoid|skip|without|no longer|halt)\b",
    re.IGNORECASE,
)


def normalize_for_router(query: str) -> str:
    """Strips conversational wake words, speech fillers, and politeness wrappers."""
    q = (query or "").strip()
    # Strip wake words (Alfred, Vesper, Jarvis)
    q = re.sub(r"^(?:(?:hey|ok|okay|hello|hi)\s+)?(?:alfred|vesper|jarvis)\b[,:]?\s*", "", q, flags=re.IGNORECASE)
    # Strip speech fillers (uh, um, ah, er, like, well)
    q = re.sub(r"^(?:uh|um|ah|er|like|well)\b[,:]?\s*", "", q, flags=re.IGNORECASE)
    # Strip leading polite requests
    q = re.sub(r"^(?:please\s+)?(?:can you\s+|could you\s+|would you\s+|tell me\s+)?(?:just\s+)?", "", q, flags=re.IGNORECASE)
    return q.strip("?.!, ")


def has_coordination(query: str) -> bool:
    """Detects if query contains coordinating conjunctions indicating multi-intent commands."""
    q_lower = query.lower()
    if COORDINATION_PATTERN.search(q_lower):
        return True
    if " and " in q_lower:
        parts = q_lower.split(" and ", 1)
        if len(parts) == 2:
            left, right = parts[0].strip(), parts[1].strip()
            cmd_verbs = {"what", "what's", "check", "read", "show", "list", "get", "tell", "play", "inspect", "how", "is"}
            left_words = set(re.findall(r"\b\w+\b", left))
            right_words = set(re.findall(r"\b\w+\b", right))
            if (left_words & cmd_verbs) and (right_words & cmd_verbs):
                return True
    return False


def has_negation(query: str) -> bool:
    """Detects if query contains negation words that must be handed to Tier 3."""
    return bool(NEGATION_PATTERN.search(query))


def has_unhandled_slots(intent: SemanticIntent, query: str) -> bool:
    """Checks if a query contains slots/entities that Tier 2 cannot handle parameterless."""
    q_lower = query.lower()
    if intent in (SemanticIntent.UNREAD_EMAILS, SemanticIntent.EMAIL_THREAD):
        # If user specifies a sender, person, or topic, Tier 2 cannot extract slots parameterless.
        # Exclude anaphora deictics ("from this/that/the email/thread") and date anchors ("from today/yesterday")
        if re.search(r"\b(?:with|regarding|about|sent by)\s+[a-zA-Z0-9_\s]+\b", q_lower):
            return True
        if re.search(r"\bfrom\s+(?!(?:this|that|the)\s+(?:email|thread|message)\b|(?:today|yesterday|now)\b)[a-zA-Z0-9_\s]+\b", q_lower):
            return True
        if any(w in q_lower for w in ["send", "compose", "write", "reply", "draft"]):
            return True
    elif intent == SemanticIntent.FINANCE_BALANCE:
        # If user asks to transfer, pay, send money, or spend, it is a mutation, not read-only balance
        if any(w in q_lower for w in ["transfer", "pay", "send", "deposit", "withdraw", "spent", "spending"]):
            return True
    elif intent == SemanticIntent.DAILY_AGENDA:
        # If user asks to add or schedule, it is a mutation
        if any(w in q_lower for w in ["add", "create", "schedule a meeting", "new meeting", "remind me"]):
            return True
    return False


@dataclass(frozen=True)
class RouteResult:
    """Result of one classification pass.

    Tuple-unpackable as `(intent, confidence, prototype)` so existing call
    sites like `intent, conf, proto = router.classify(query)` keep working
    unchanged.
    """

    intent: SemanticIntent
    confidence: float
    prototype: Optional[str] = None
    runner_up: Optional[SemanticIntent] = None
    runner_up_confidence: float = 0.0
    reason: Optional[str] = None

    @property
    def matched(self) -> bool:
        return self.intent != SemanticIntent.NONE

    @property
    def margin(self) -> float:
        """Gap between the winning intent and the next-best candidate."""
        return self.confidence - self.runner_up_confidence

    def __iter__(self):
        return iter((self.intent, self.confidence, self.prototype))

    def __getitem__(self, idx):
        return (self.intent, self.confidence, self.prototype)[idx]


class SemanticIntentRouter:
    """Classifies user queries against canonical intent prototypes using cosine similarity."""

    _instance: Optional["SemanticIntentRouter"] = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        thresholds: Optional[Dict[SemanticIntent, float]] = None,
        cache_size: int = 256,
        margin_warn_threshold: float = 0.03,
        decision_margin: float = 0.03,
        contrast_margin: float = 0.02,
    ) -> None:
        self.model_name = model_name
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.margin_warn_threshold = margin_warn_threshold
        self.decision_margin = decision_margin
        self.contrast_margin = contrast_margin

        # Fail fast at construction time: every intent needs an explicit
        # threshold. A silent fallback here would let a newly-added intent
        # mis-fire (too low) or never fire (too high) without anyone
        # noticing until it showed up as a user-facing bug.
        missing = set(INTENT_PROTOTYPES) - set(self.thresholds)
        if missing:
            raise ValueError(
                f"Missing similarity thresholds for intents: {sorted(m.value for m in missing)}"
            )

        self._model: Optional[Any] = None
        self._init_lock = threading.Lock()
        self._initialized = False
        self._init_failed = False

        # Flattened prototype bank -- one matrix and one label array,
        # instead of one small matrix per intent. Lets classify() score
        # every prototype in a single matmul rather than N_intents of them.
        self._proto_vectors: Optional[np.ndarray] = None
        self._proto_intents: List[SemanticIntent] = []
        self._proto_texts: List[str] = []

        self._cache_cap = cache_size
        self._query_cache: Dict[str, RouteResult] = {}

    # -- initialization -------------------------------------------------------

    def _ensure_initialized(self) -> bool:
        """Lazy-loads the embedding model and flattens the prototype bank.

        Thread-safe, and fails fast: if initialization fails once (e.g. no
        network to fetch the model on first run), it will NOT retry on
        every subsequent call. The original implementation re-attempted
        the full model load -- including a fresh download attempt -- on
        every single classify() call after a failure, which turns one
        offline moment into unbounded added latency on every voice
        command from then on, instead of just falling through to Tier 3.
        """
        if self._initialized:
            return True
        if self._init_failed:
            return False

        with self._init_lock:
            if self._initialized:
                return True
            if self._init_failed:
                return False

            try:
                from fastembed import TextEmbedding

                logger.info(f"[SemanticRouter] Initializing FastEmbed model '{self.model_name}'...")
                self._model = TextEmbedding(self.model_name)

                vectors: List[np.ndarray] = []
                for intent, prototypes in INTENT_PROTOTYPES.items():
                    embs = list(self._model.embed(prototypes))
                    for text, emb in zip(prototypes, embs):
                        vectors.append(emb / (np.linalg.norm(emb) + 1e-9))
                        self._proto_intents.append(intent)
                        self._proto_texts.append(text)

                self._proto_vectors = np.vstack(vectors)
                self._initialized = True
                logger.info(
                    f"[SemanticRouter] Ready: {len(self._proto_texts)} prototypes "
                    f"across {len(INTENT_PROTOTYPES)} intents."
                )
                return True
            except Exception:
                self._init_failed = True
                logger.exception(
                    "[SemanticRouter] Failed to initialize FastEmbed model. Semantic "
                    "routing is disabled for this process; Tier 3 LLM planning will "
                    "handle everything Tier 2 would have caught."
                )
                return False

    # -- classification ---------------------------------------------------------

    def classify(self, query: str) -> RouteResult:
        """Classifies a query against canonical intent prototypes.

        Returns a RouteResult (still tuple-unpackable as the old
        `(intent, confidence, prototype)` shape). If no intent crosses its
        threshold, or if negation / multi-intent coordination / unhandled slots
        are detected, `.intent` is SemanticIntent.NONE so Tier 3 can plan it.
        """
        raw_query = (query or "").strip()
        if not raw_query:
            return RouteResult(SemanticIntent.NONE, 0.0)

        # 1. Multi-intent Coordination Guard: Multi-intent queries lose an intent if resolved here
        if has_coordination(raw_query):
            logger.info(f"[SemanticRouter] Multi-intent coordination detected in query='{raw_query}' -> delegating to Tier 3 swarm")
            return RouteResult(SemanticIntent.NONE, 0.0, reason="multi_intent_coordination")

        # 2. Normalize input before embedding (strip wake words and speech fillers)
        norm_query = normalize_for_router(raw_query)
        if not norm_query:
            norm_query = raw_query

        cached = self._query_cache.get(norm_query)
        if cached is not None:
            return cached

        if not self._ensure_initialized() or self._proto_vectors is None or self._model is None:
            return RouteResult(SemanticIntent.NONE, 0.0)

        try:
            q_emb = list(self._model.embed([norm_query]))[0]
            q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)

            # Batched dot product against all prototypes in a single matmul
            sims = self._proto_vectors @ q_norm

            best_per_intent: Dict[SemanticIntent, Tuple[float, int]] = {}
            for idx, intent in enumerate(self._proto_intents):
                sim = float(sims[idx])
                current = best_per_intent.get(intent)
                if current is None or sim > current[0]:
                    best_per_intent[intent] = (sim, idx)

            # Score against NONE / Hard Negatives
            none_sim, none_idx = best_per_intent.get(SemanticIntent.NONE, (0.0, -1))

            # Candidates passing their calibrated threshold (excluding NONE)
            candidates = [
                (intent, sim, idx)
                for intent, (sim, idx) in best_per_intent.items()
                if intent != SemanticIntent.NONE and sim >= self.thresholds.get(intent, 1.0)
            ]
            candidates.sort(key=lambda t: t[1], reverse=True)

            if candidates:
                winner_intent, winner_sim, winner_idx = candidates[0]
                runner_up_intent, runner_up_sim = (
                    (candidates[1][0], candidates[1][1]) if len(candidates) > 1 else (None, 0.0)
                )

                # Check 1: Contrast Penalty (if query is closer to a hard negative)
                if none_sim >= (winner_sim - self.contrast_margin):
                    logger.info(
                        f"[SemanticRouter] Rejected via hard-negative contrast: winner={winner_intent.value} ({winner_sim:.3f}) "
                        f"vs negative={none_sim:.3f} ('{self._proto_texts[none_idx]}') query='{raw_query}'"
                    )
                    res = RouteResult(
                        SemanticIntent.NONE,
                        confidence=winner_sim,
                        runner_up=winner_intent,
                        runner_up_confidence=none_sim,
                        reason="contrast_penalty",
                    )
                    self._cache_result(norm_query, res)
                    return res

                # Check 2: Action-Negation Guard (e.g. "don't check my email", "never check balance")
                # Delegates action negations to Tier 3. Verify research is exempt because verification is
                # intrinsically a negative/rejection of a previous statement.
                if winner_intent != SemanticIntent.VERIFY_RESEARCH and has_negation(raw_query):
                    logger.info(
                        f"[SemanticRouter] Action-negation detected in query='{raw_query}' for {winner_intent.value} -> delegating to Tier 3 LLM"
                    )
                    res = RouteResult(
                        SemanticIntent.NONE,
                        confidence=winner_sim,
                        runner_up=winner_intent,
                        runner_up_confidence=winner_sim,
                        reason="negation_detected",
                    )
                    self._cache_result(norm_query, res)
                    return res

                # Check 3: Margin check between top 2 positive intents
                if runner_up_intent is not None and (winner_sim - runner_up_sim) < self.decision_margin:
                    logger.warning(
                        f"[SemanticRouter] Ambiguous narrow margin ({winner_sim - runner_up_sim:.3f} < {self.decision_margin}) "
                        f"between {winner_intent.value} and {runner_up_intent.value} for query='{raw_query}' -> delegating to Tier 3"
                    )
                    res = RouteResult(
                        SemanticIntent.NONE,
                        confidence=winner_sim,
                        runner_up=winner_intent,
                        runner_up_confidence=runner_up_sim,
                        reason="ambiguous_margin",
                    )
                    self._cache_result(norm_query, res)
                    return res

                # Check 4: Unhandled Slots / Parameterized Intent check
                if has_unhandled_slots(winner_intent, raw_query):
                    logger.info(
                        f"[SemanticRouter] Intent {winner_intent.value} has unhandled slots in query='{raw_query}' -> delegating to Tier 3"
                    )
                    res = RouteResult(
                        SemanticIntent.NONE,
                        confidence=winner_sim,
                        prototype=self._proto_texts[winner_idx],
                        runner_up=runner_up_intent,
                        runner_up_confidence=runner_up_sim,
                        reason="unhandled_slots",
                    )
                    self._cache_result(norm_query, res)
                    return res

                result = RouteResult(
                    intent=winner_intent,
                    confidence=winner_sim,
                    prototype=self._proto_texts[winner_idx],
                    runner_up=runner_up_intent,
                    runner_up_confidence=runner_up_sim,
                )
                logger.info(
                    f"[SemanticRouter] intent={winner_intent.value} conf={winner_sim:.3f} "
                    f"margin={result.margin:.3f} proto='{result.prototype}' query='{raw_query}'"
                )
                if result.margin < self.margin_warn_threshold and runner_up_intent is not None:
                    logger.warning(
                        f"[SemanticRouter] Narrow margin ({result.margin:.3f}) between "
                        f"{winner_intent.value} and {runner_up_intent.value} for "
                        f"query='{raw_query}' -- consider re-tuning prototypes/thresholds."
                    )
            else:
                best_overall = float(np.max(sims)) if len(sims) else 0.0
                result = RouteResult(SemanticIntent.NONE, max(0.0, best_overall), reason="below_threshold")

            self._cache_result(norm_query, result)
            return result

        except Exception:
            logger.exception(f"[SemanticRouter] Error during classification of query='{raw_query}'")
            return RouteResult(SemanticIntent.NONE, 0.0)

    def _cache_result(self, query: str, result: RouteResult) -> None:
        if len(self._query_cache) >= self._cache_cap:
            self._query_cache.pop(next(iter(self._query_cache)))  # drop oldest (dict insertion order)
        self._query_cache[query] = result

    # -- diagnostics ------------------------------------------------------------

    def run_self_test(self) -> List[Tuple[str, SemanticIntent, SemanticIntent, bool]]:
        """Runs SELF_TEST_CASES, returns (query, expected, actual, passed) rows.

        Cheap enough to call on startup as a canary, or wrap in a one-line
        pytest to catch a threshold/prototype edit that silently breaks an
        existing case (e.g. the Exhibit A marathon false-positive).
        """
        rows = []
        for query, expected in SELF_TEST_CASES:
            actual = self.classify(query).intent
            rows.append((query, expected, actual, actual == expected))
        return rows

    @classmethod
    def get_instance(cls) -> "SemanticIntentRouter":
        """Thread-safe singleton accessor for the shared embedding model."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = SemanticIntentRouter()
        return cls._instance
