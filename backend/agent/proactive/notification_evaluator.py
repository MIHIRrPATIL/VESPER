"""VESPER Multi-Domain Notification Evaluator.

Features:
  1. 30-second thread coalescing / clubbing buffer.
  2. Noise & summary filtering (ignoring WhatsApp group counters and user's 'You' messages).
  3. Verbatim financial transaction extraction (Bank SMS / UPI).
  4. Peer debt & bill split parsing.
  5. Structured JSON VIP task extraction with casual chat suppression.
  6. Ambient OTP extraction.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.agent.proactive.action_queue import StagedAction, action_queue
from backend.sync.notification_service import MobileNotification, NotificationPriority

logger = logging.getLogger("vesper.agent.proactive.notif")

# Known bank and payment sender identifiers
BANK_SENDER_PATTERNS = [
    r"[A-Z]{2}-HDFCBK", r"[A-Z]{2}-ICICIB", r"[A-Z]{2}-SBINB",
    r"[A-Z]{2}-AXISBK", r"[A-Z]{2}-KOTAKB", r"[A-Z]{2}-PNBSMS",
    r"[A-Z]{2}-PAYTM",  r"[A-Z]{2}-CRED",   r"[A-Z]{2}-GPAY",
    r"[A-Z]{2}-PHONEPE", r"[A-Z]{2}-BOB",   r"[A-Z]{2}-CANBNK",
    r"hdfc", r"icici", r"sbi", r"axis", r"kotak", r"paytm", r"cred", r"gpay"
]

USER_NAME = "Mihir"
USER_ALIASES = [r"\bmihir\b", r"@mihir\b", r"\bpatil\b"]


class EvaluationResult(BaseModel):
    """Result returned by NotificationEvaluator indicating whether notification was triaged."""
    handled: bool
    staged_action: Optional[StagedAction] = None
    reason: Optional[str] = None


class NotificationEvaluator:
    """Evaluates mobile companion alerts across financial, task, and communication domains."""

    _instance: Optional["NotificationEvaluator"] = None

    def __init__(self) -> None:
        # Buffer for thread coalescing: key = (pkg, thread/title) -> (last_time, messages)
        self._thread_buffer: Dict[str, Tuple[float, List[str]]] = {}
        self._coalescing_window_sec: float = 20.0

    @classmethod
    def get_instance(cls) -> "NotificationEvaluator":
        if cls._instance is None:
            cls._instance = NotificationEvaluator()
        return cls._instance

    async def evaluate(self, notif: MobileNotification) -> EvaluationResult:
        """Main entry point for evaluating an incoming notification."""
        # 1. Filter internal noise, summary headers, and user's own outgoing messages
        if self._is_summary_or_outgoing(notif):
            return EvaluationResult(handled=True, reason="summary_or_outgoing")

        # 1b. Filter commercial advertisements, promotional SMS, discount offers, and expiring credits
        if self._is_promotional_or_spam(notif):
            return EvaluationResult(handled=True, reason="promotional_or_spam")

        # 2. Suppress casual personal banter without calling LLM
        if self._is_casual_banter(notif.text):
            return EvaluationResult(handled=True, reason="casual_banter")

        # 3. Check for Financial SMS / UPI transactions first (Deterministic & Exact)
        fin_action = self._try_parse_financial(notif)
        if fin_action:
            staged = action_queue.stage_action(fin_action)
            return EvaluationResult(handled=True, staged_action=staged)

        # 4. Check for Peer Debt / Bill Split patterns
        debt_action = self._try_parse_peer_debt(notif)
        if debt_action:
            staged = action_queue.stage_action(debt_action)
            return EvaluationResult(handled=True, staged_action=staged)

        # 5. Check for OTP / 2FA code (Instant Ambient HUD, no staging)
        otp_code = self._try_extract_otp(notif)
        if otp_code:
            logger.info(f"[NotificationEvaluator] Extracted ambient OTP: '{otp_code}' from {notif.title}")
            return EvaluationResult(handled=True, reason="ambient_otp")

        # 5b. Group message triage rule:
        # If notification is from a group chat, only extract tasks if it specifically mentions the user ("Mihir").
        # If it's a 1-on-1 direct message, user mention is not required.
        if self._is_group_notification(notif) and not self._mentions_user(notif.text):
            logger.info(
                f"[NotificationEvaluator] Group notification '{notif.title}' did not mention user ('{USER_NAME}'); "
                f"suppressing task extraction."
            )
            return EvaluationResult(handled=True, reason="group_message_not_addressed_to_user")

        # 6. VIP Task & Action Item Extraction (Only for MEDIUM, HIGH, URGENT)
        if notif.priority in (NotificationPriority.URGENT, NotificationPriority.HIGH, NotificationPriority.MEDIUM):
            task_action = await self._try_extract_vip_task(notif)
            if task_action:
                staged = action_queue.stage_action(task_action)
                return EvaluationResult(handled=True, staged_action=staged)

        return EvaluationResult(handled=False)

    def _is_group_notification(self, notif: MobileNotification) -> bool:
        """Determines if an incoming notification originated from a group conversation."""
        if getattr(notif, "is_group_conversation", False):
            return True

        title = notif.title.strip()
        # Pattern 1: WhatsApp / messaging group format: "GroupName (N messages): Sender" or "GroupName (N): Sender"
        if re.search(r"\([^)]*messages?\)\s*:\s*", title, re.IGNORECASE):
            return True
        if re.search(r"\(\d+\)\s*:\s*", title):
            return True

        # Pattern 2: Group name separated by colon, e.g. "IPD GANG WITH JAY: Hitanshu Gala"
        if ":" in title:
            prefix = title.split(":", 1)[0].strip()
            group_words = ["group", "gang", "team", "project", "batch", "club", "squad", "family", "class", "dept", "announcements"]
            if any(w in prefix.lower() for w in group_words):
                return True
            if len(prefix.split()) >= 2:
                return True

        return False

    def _mentions_user(self, text: str) -> bool:
        """Checks if the message explicitly mentions or addresses the user."""
        t = text.lower()
        return any(re.search(alias, t, re.IGNORECASE) for alias in USER_ALIASES)


    def _is_casual_banter(self, text: str) -> bool:
        """Fast deterministic check for common non-actionable chat messages."""
        t = text.lower().strip()
        banter_phrases = [
            "yes my love", "relax", "lol nice", "ok sure see you then",
            "see you tomorrow", "sounds good", "haha", "cool", "take care",
            "good morning", "good night", "love you", "on my way",
        ]
        if any(p in t for p in banter_phrases):
            return True
        if len(t.split()) <= 2 and t in ("ok", "yes", "sure", "nice", "cool", "yeah", "yup", "nope", "bye"):
            return True
        return False

    def _is_summary_or_outgoing(self, notif: MobileNotification) -> bool:
        """Filters group summary headers and messages sent by the user."""
        title_lower = notif.title.lower().strip()
        text_lower = notif.text.lower().strip()

        # Outgoing message from user
        if title_lower in ("you", "me"):
            return True

        # WhatsApp group summary counter
        if re.search(r"\b\d+\s+messages?\s+from\s+\d+\s+chats?\b", text_lower):
            return True
        if re.search(r"\b\d+\s+new\s+messages?\b", text_lower):
            return True

        # Generic status ticks
        if text_lower in ("just now", "now", "online"):
            return True

        return False

    def _is_promotional_or_spam(self, notif: MobileNotification) -> bool:
        """Filters out commercial advertisements, marketing SMS, coupons, and expiring point promos."""
        title = notif.title.strip()
        text = notif.text.strip()
        combined = f"{title} {text}".lower()

        # 1. Indian TRAI SMS promotional / business headers (e.g. AD-PHRMSY-P, VM-SWIGGY, BP-ZOMATO, JD-FLPKRT)
        # Exception: Do NOT block legitimate bank transaction senders
        is_bank_sender = any(re.search(p, title, re.IGNORECASE) for p in BANK_SENDER_PATTERNS)
        is_commercial_sms_header = bool(re.match(r"^[A-Za-z]{2}-[A-Za-z0-9]{3,12}(?:-[A-Za-z0-9]+)?$", title))

        if is_commercial_sms_header and not is_bank_sender:
            # Check if this is an ad / promotional SMS
            promo_tokens = [
                "expire", "credit", "points", "coupon", "promo", "discount", "save extra", "off",
                "cashback", "sale", "shop now", "order now", "buy now", "medicines", "free delivery",
                "hurry", "limited period", "offer", "deal", "win up to", "congratulations",
                "apply now", "loan", "voucher", "tc", "t&c", "1kx.in", "bit.ly", "tinyurl",
            ]
            if any(tok in combined for tok in promo_tokens):
                logger.info(f"[NotificationEvaluator] Filtered commercial SMS promo from {title}: '{text[:60]}'")
                return True

            # If sender starts with explicit advertising prefix AD- or DM- or TM-
            if re.match(r"^(?:AD|DM|TM|QP|XY|BA|BW)-", title, re.IGNORECASE):
                logger.info(f"[NotificationEvaluator] Filtered explicit ad header from {title}")
                return True

        # 2. General promotional content check across any messaging app
        promo_patterns = [
            r"\b(?:credits?|points?|balance|voucher)\s+(?:will\s+)?expire\b",
            r"\bsave\s+extra\s+\d+%",
            r"\bflat\s+\d+%\s+off\b",
            r"\bupto\s+\d+%\s+off\b",
            r"\buse\s+(?:code|coupon)\b",
            r"\bexclusive\s+offer\b",
            r"\blimited\s+time\s+offer\b",
            r"\border\s+(?:medicines|groceries|food)\s+(?:now|today)\b",
            r"\b1kx\.in/[A-Za-z0-9/]+",
        ]
        if any(re.search(pat, combined, re.IGNORECASE) for pat in promo_patterns):
            logger.info(f"[NotificationEvaluator] Filtered promotional content from {title}: '{text[:60]}'")
            return True

        return False

    def _try_parse_financial(self, notif: MobileNotification) -> Optional[StagedAction]:
        """Deterministic regex parser for Indian bank debit/credit and UPI messages.

        Enforces verbatim read-back and raw evidence storage.
        """
        combined = f"{notif.title} {notif.text}"
        combined_lower = combined.lower()

        # Check for debit or spent keywords
        is_debit = any(w in combined_lower for w in [
            "debited", "spent", "paid", "sent", "transferred", "txn of", "purchase of"
        ])
        if not is_debit:
            return None

        # Extract Amount in INR (₹ or Rs or INR)
        amt_match = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)", combined, re.IGNORECASE)
        if not amt_match:
            # Fallback pattern: e.g. "for 1,850.00"
            amt_match = re.search(r"\b(?:amount|amt|for)\s+(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", combined, re.IGNORECASE)

        if not amt_match:
            return None

        raw_amt_str = amt_match.group(1).replace(",", "")
        try:
            amount = float(raw_amt_str)
        except ValueError:
            return None

        if amount <= 0:
            return None

        # Extract merchant/payee
        merchant = "Unknown Merchant"
        merchant_match = re.search(
            r"(?:at|to|vpa|info|towards)\s+([A-Za-z0-9\.\s\-_&]{2,30}?)(?:\s+on|\s+ref|\s+avl|\s+balance|\s+date|\.|$)",
            combined,
            re.IGNORECASE,
        )
        if merchant_match:
            candidate = merchant_match.group(1).strip()
            if candidate and not any(w in candidate.lower() for w in ["your", "account", "a/c", "card"]):
                merchant = candidate

        # Infer category
        m_lower = merchant.lower()
        if any(f in m_lower for f in ["swiggy", "zomato", "mcdonald", "starbucks", "domino", "restaurant", "cafe", "food"]):
            category = "Dining"
        elif any(u in m_lower for u in ["uber", "ola", "rapido", "metro", "fuel", "petrol", "shell"]):
            category = "Transport"
        elif any(s in m_lower for s in ["amazon", "flipkart", "myntra", "blinkit", "zepto", "instamart", "mart"]):
            category = "Shopping"
        else:
            category = "General Expense"

        action_id = f"act_fin_{int(time.time())}_{int(amount)}"
        verbatim_text = f"INR {amount:,.2f} at {merchant}"
        speech_prompt = (
            f"Sir, a debit of exactly {amount:,.2f} rupees at {merchant} was detected. "
            f"Shall I log this under your {category} budget?"
        )

        return StagedAction(
            id=action_id,
            domain="finance",
            action="log_transaction",
            params={
                "amount": amount,
                "category": category,
                "description": f"Expense at {merchant}",
                "transaction_type": "expense",
            },
            verbatim_text=verbatim_text,
            raw_evidence={
                "source_package": notif.package_name,
                "source_title": notif.title,
                "raw_text": notif.text,
                "post_time": getattr(notif, "post_time", getattr(notif, "timestamp", time.time())),
            },
            speech_prompt=speech_prompt,
            priority="HIGH",
        )

    def _try_parse_peer_debt(self, notif: MobileNotification) -> Optional[StagedAction]:
        """Detects peer split bills and debts (e.g. 'you owe me 600 for cab')."""
        combined = f"{notif.title} {notif.text}"
        combined_lower = combined.lower()

        is_debt_phrase = any(phrase in combined_lower for phrase in [
            "you owe", "your share", "share is", "split the bill", "paid for the", "gpay me"
        ])
        if not is_debt_phrase:
            return None

        amt_match = re.search(r"(?:rs\.?|inr|₹|\$)?\s*(\d+(?:,\d+)*(?:\.\d{1,2})?)\b", combined, re.IGNORECASE)
        if not amt_match:
            return None

        try:
            amount = float(amt_match.group(1).replace(",", ""))
        except ValueError:
            return None

        if amount <= 0 or amount > 500000:
            return None

        peer_name = notif.title.strip()
        action_id = f"act_debt_{int(time.time())}_{int(amount)}"
        verbatim_text = f"Debt of INR {amount:,.2f} to {peer_name}"
        speech_prompt = (
            f"Sir, {peer_name} indicated a share of {amount:,.2f} rupees. "
            f"Shall I record a debt of {amount:,.2f} rupees owed to {peer_name}?"
        )

        return StagedAction(
            id=action_id,
            domain="finance",
            action="manage_debt",
            params={
                "action": "borrow",
                "action_type": "borrow",
                "person": peer_name,
                "amount": amount,
                "description": f"Split share from {peer_name}",
            },
            verbatim_text=verbatim_text,
            raw_evidence={
                "sender": peer_name,
                "raw_message": notif.text,
            },
            speech_prompt=speech_prompt,
            priority="HIGH",
        )

    def _try_extract_otp(self, notif: MobileNotification) -> Optional[str]:
        """Regex for OTP / verification codes to surface immediately on HUD."""
        combined = f"{notif.title} {notif.text}"
        match = re.search(r"\b(?:otp|code|pin|verification)\b.*?\b(\d{4,8})\b", combined, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    async def _try_extract_vip_task(self, notif: MobileNotification) -> Optional[StagedAction]:
        """Uses fast LLM with strict JSON schema to identify tasks and suppress casual chat."""
        try:
            from backend.agent.llm import LLMClient

            llm = LLMClient()
            prompt = (
                f"You are Alfred, a proactive AI butler triaging incoming mobile messages.\n"
                f"Message received:\n"
                f"  From: {notif.title}\n"
                f"  Text: {notif.text}\n\n"
                f"Determine if this message contains an IMPORTANT, concrete, actionable request, assignment, or deadline directly intended for the user from a real contact or team.\n"
                f"CRITICAL FILTERING RULES (respond with actionable: false):\n"
                f"- The message must be genuinely IMPORTANT. Casual check-ins, minor chatter, jokes, rhetorical questions, or low-priority social comments are NEVER actionable tasks, even if directed at the user.\n"
                f"- Advertisements, brand promotions, discounts, coupon codes, and store sales are NEVER tasks.\n"
                f"- Expiring points/credits notifications (e.g. PharmEasy, Zomato, Swiggy, Uber) are NEVER tasks.\n"
                f"- Transaction confirmations, delivery updates, and automated receipts are NOT tasks.\n"
                f"- Casual banter, greetings, emotional updates, or generic comments are NOT actionable.\n\n"
                f"Respond in valid JSON format with keys:\n"
                f"  \"actionable\": true or false,\n"
                f"  \"importance\": \"high\" | \"normal\" | \"low\",\n"
                f"  \"task\": \"concise actionable title (under 8 words) if actionable, else empty string\",\n"
                f"  \"reason\": \"brief explanation\"\n"
            )

            messages = [
                {"role": "system", "content": "You are a concise triage classifier. Always respond in JSON format."},
                {"role": "user", "content": prompt},
            ]

            data, _ = await llm.generate_json(messages, temperature=0.1)
            if not isinstance(data, dict) or not data.get("actionable"):
                return None

            if str(data.get("importance", "")).lower() == "low":
                return None

            task_title = (data.get("task") or "").strip()
            if not task_title or len(task_title) < 3:
                return None


            action_id = f"act_task_{int(time.time())}"
            verbatim_text = f"Task: {task_title}"
            speech_prompt = (
                f"Sir, an actionable message from {notif.title} was detected. "
                f"Shall I create a task: '{task_title}'?"
            )

            return StagedAction(
                id=action_id,
                domain="tasks",
                action="add_task",
                params={"title": task_title, "priority": "HIGH"},
                verbatim_text=verbatim_text,
                raw_evidence={
                    "sender": notif.title,
                    "message": notif.text,
                    "triage_reason": data.get("reason", ""),
                },
                speech_prompt=speech_prompt,
                priority="HIGH",
            )
        except Exception as e:
            logger.warning(f"[NotificationEvaluator] VIP task extraction error: {e}")
            return None


notification_evaluator = NotificationEvaluator.get_instance()
