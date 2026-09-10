"""Local semantic similarity router for zero-token intent classification.

Uses all-MiniLM-L6-v2 via FastEmbed to classify natural language queries against
canonical intent prototypes in ~10ms on CPU without LLM roundtrips or Groq quota usage.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

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
    ],
    SemanticIntent.FINANCE_BALANCE: [
        "what is my bank balance",
        "how much money do I have",
        "check my financial balance",
        "what is my net worth",
        "show me my account balance",
        "how much cash is in my accounts",
    ],
    SemanticIntent.SYSTEM_STATUS: [
        "how is the system running",
        "show me system vitals",
        "what is the cpu and ram usage",
        "how much battery and memory is left",
        "system resource check",
        "check system vitals",
        "how is my computer running",
        "show system telemetry",
        "give me a brief system and cluster status report",
        "system and cluster status report",
        "system and cluster status",
        "cluster status report",
        "how is the cluster running",
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
}

# Similarity thresholds for matching (empirically calibrated)
DEFAULT_THRESHOLDS: Dict[SemanticIntent, float] = {
    SemanticIntent.HANDHELD_OBJECT_RESEARCH: 0.50,
    SemanticIntent.VERIFY_RESEARCH: 0.55,
    SemanticIntent.EMAIL_THREAD: 0.58,
    SemanticIntent.UNREAD_EMAILS: 0.58,
    SemanticIntent.SONG_ORIGIN: 0.60,
    SemanticIntent.DAILY_AGENDA: 0.60,
    SemanticIntent.FINANCE_BALANCE: 0.60,
    SemanticIntent.SYSTEM_STATUS: 0.60,
    SemanticIntent.MOBILE_NOTIFICATIONS: 0.58,
    SemanticIntent.BATTERY_STATUS: 0.58,
}

# Regression fixtures. Mirrors backend/tests/test_agent.py's false-positive
# checks (e.g. the "marathon record" query must never match a handheld
# intent) -- kept here too so `run_self_test()` gives a fast sanity check
# without spinning up pytest, e.g. right after startup or a prototype edit.
SELF_TEST_CASES: List[Tuple[str, SemanticIntent]] = [
    ("who is holding the world record for the marathon", SemanticIntent.NONE),
    ("tell me about this book I am holding", SemanticIntent.HANDHELD_OBJECT_RESEARCH),
    ("no try again", SemanticIntent.VERIFY_RESEARCH),
    ("check the entire email thread", SemanticIntent.EMAIL_THREAD),
    ("what movie is this song from", SemanticIntent.SONG_ORIGIN),
    ("what is on my schedule today", SemanticIntent.DAILY_AGENDA),
    ("what is my bank balance", SemanticIntent.FINANCE_BALANCE),
    ("show me system vitals", SemanticIntent.SYSTEM_STATUS),
    ("check my phone notifications", SemanticIntent.MOBILE_NOTIFICATIONS),
    ("is my phone charging", SemanticIntent.BATTERY_STATUS),
]


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

    @property
    def matched(self) -> bool:
        return self.intent != SemanticIntent.NONE

    @property
    def margin(self) -> float:
        """Gap between the winning intent and the next-best candidate.
        Useful for spotting queries where two intents nearly tied -- a
        signal worth logging even though a decision still gets made."""
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
    ) -> None:
        self.model_name = model_name
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.margin_warn_threshold = margin_warn_threshold

        # Fail fast at construction time: every intent needs an explicit
        # threshold. A silent fallback here would let a newly-added intent
        # mis-fire (too low) or never fire (too high) without anyone
        # noticing until it showed up as a user-facing bug.
        missing = set(INTENT_PROTOTYPES) - set(self.thresholds)
        if missing:
            raise ValueError(
                f"Missing similarity thresholds for intents: {sorted(m.value for m in missing)}"
            )

        self._model = None
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
        threshold, `.intent` is SemanticIntent.NONE.
        """
        query = (query or "").strip()
        if not query:
            return RouteResult(SemanticIntent.NONE, 0.0)

        cached = self._query_cache.get(query)
        if cached is not None:
            return cached

        if not self._ensure_initialized() or self._proto_vectors is None:
            return RouteResult(SemanticIntent.NONE, 0.0)

        try:
            q_emb = list(self._model.embed([query]))[0]
            q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)

            # One batched matmul against every prototype (N_total,) instead
            # of one matmul per intent -- same result, fewer Python-level
            # round trips, and it scales flat as more intents get added.
            sims = self._proto_vectors @ q_norm

            best_per_intent: Dict[SemanticIntent, Tuple[float, int]] = {}
            for idx, intent in enumerate(self._proto_intents):
                sim = float(sims[idx])
                current = best_per_intent.get(intent)
                if current is None or sim > current[0]:
                    best_per_intent[intent] = (sim, idx)

            ranked = sorted(
                (
                    (intent, sim, idx)
                    for intent, (sim, idx) in best_per_intent.items()
                    if sim >= self.thresholds[intent]
                ),
                key=lambda t: t[1],
                reverse=True,
            )

            if ranked:
                winner_intent, winner_sim, winner_idx = ranked[0]
                runner_up_intent, runner_up_sim = (
                    (ranked[1][0], ranked[1][1]) if len(ranked) > 1 else (None, 0.0)
                )
                result = RouteResult(
                    intent=winner_intent,
                    confidence=winner_sim,
                    prototype=self._proto_texts[winner_idx],
                    runner_up=runner_up_intent,
                    runner_up_confidence=runner_up_sim,
                )
                logger.info(
                    f"[SemanticRouter] intent={winner_intent.value} conf={winner_sim:.3f} "
                    f"margin={result.margin:.3f} proto='{result.prototype}' query='{query}'"
                )
                if result.margin < self.margin_warn_threshold and runner_up_intent is not None:
                    logger.warning(
                        f"[SemanticRouter] Narrow margin ({result.margin:.3f}) between "
                        f"{winner_intent.value} and {runner_up_intent.value} for "
                        f"query='{query}' -- consider re-tuning prototypes/thresholds."
                    )
            else:
                best_overall = float(np.max(sims)) if len(sims) else 0.0
                result = RouteResult(SemanticIntent.NONE, max(0.0, best_overall))

            self._cache_result(query, result)
            return result

        except Exception:
            logger.exception(f"[SemanticRouter] Error during classification of query='{query}'")
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
