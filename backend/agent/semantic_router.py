"""Local semantic similarity router for zero-token intent classification.

Uses all-MiniLM-L6-v2 via FastEmbed to classify natural language queries against
canonical intent prototypes in ~10ms on CPU without LLM roundtrips or Groq quota usage.
"""

from enum import Enum
import logging
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
    SemanticIntent.HANDHELD_OBJECT_RESEARCH: 0.60,
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


class SemanticIntentRouter:
    """Classifies user queries against canonical intent prototypes using cosine similarity."""

    _instance: Optional["SemanticIntentRouter"] = None

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        thresholds: Optional[Dict[SemanticIntent, float]] = None,
    ) -> None:
        self.model_name = model_name
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self._model = None
        self._proto_matrices: Dict[SemanticIntent, np.ndarray] = {}
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy-loads the embedding model and computes normalized prototype matrices."""
        if self._initialized:
            return True

        try:
            from fastembed import TextEmbedding

            logger.info(f"[SemanticRouter] Initializing FastEmbed model '{self.model_name}'...")
            self._model = TextEmbedding(self.model_name)

            for intent, prototypes in INTENT_PROTOTYPES.items():
                embs = list(self._model.embed(prototypes))
                norms = [e / (np.linalg.norm(e) + 1e-9) for e in embs]
                self._proto_matrices[intent] = np.array(norms)

            self._initialized = True
            logger.info("[SemanticRouter] Prototype matrices initialized successfully.")
            return True
        except Exception as e:
            logger.error(f"[SemanticRouter] Failed to initialize FastEmbed model: {e}")
            return False

    def classify(self, query: str) -> Tuple[SemanticIntent, float, Optional[str]]:
        """Classifies a query against canonical intent prototypes.

        Returns:
            Tuple of (matched_intent, confidence_score, best_matching_prototype).
            If no intent crosses its threshold, returns (SemanticIntent.NONE, max_sim, None).
        """
        if not query or not query.strip():
            return SemanticIntent.NONE, 0.0, None

        if not self._ensure_initialized() or self._model is None:
            return SemanticIntent.NONE, 0.0, None

        try:
            q_emb = list(self._model.embed([query.strip()]))[0]
            q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)

            best_intent = SemanticIntent.NONE
            best_sim = -1.0
            best_prototype: Optional[str] = None

            for intent, matrix in self._proto_matrices.items():
                sims = np.dot(matrix, q_norm)
                max_idx = int(np.argmax(sims))
                max_sim = float(sims[max_idx])

                threshold = self.thresholds.get(intent, 0.60)
                if max_sim >= threshold and max_sim > best_sim:
                    best_sim = max_sim
                    best_intent = intent
                    best_prototype = INTENT_PROTOTYPES[intent][max_idx]

            if best_intent != SemanticIntent.NONE:
                logger.info(
                    f"[SemanticRouter] Matched intent={best_intent.value} (conf={best_sim:.3f}, proto='{best_prototype}') for query='{query}'"
                )
                return best_intent, best_sim, best_prototype

            return SemanticIntent.NONE, max(0.0, best_sim), None
        except Exception as e:
            logger.error(f"[SemanticRouter] Error during classification: {e}")
            return SemanticIntent.NONE, 0.0, None

    @classmethod
    def get_instance(cls) -> "SemanticIntentRouter":
        """Singleton accessor for shared embedding model."""
        if cls._instance is None:
            cls._instance = SemanticIntentRouter()
        return cls._instance
