"""VESPER Speech-to-Text & Entity Normalization Engine.

Normalizes phonetic speech-to-text transcriptions for Indian banks, financial entities,
and common conversational slips (e.g. 'Sarasworth' -> 'Saraswat Bank', 'Union back' -> 'Union Bank',
'cash delay' -> 'cash withdrawal') to ensure deterministic routing and search precision.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Canonical bank registry and their phonetic STT misrecognitions / informal aliases
INDIAN_BANK_ALIASES: Dict[str, Dict[str, Any]] = {
    "saraswat": {
        "canonical_name": "Saraswat Bank",
        "account_name": "Saraswat",
        "keywords": ["saraswat", "saraswatbank", "saraswath", "sarasworth", "saraswati", "saraswathi", "sarashwat"],
        "email_domains": ["saraswatbank.co.in", "saraswatbank.com"],
        "email_senders": ["alert@saraswatbank.co.in", "alerts@saraswatbank.com", "info@saraswatbank.com"],
    },
    "union": {
        "canonical_name": "Union Bank of India",
        "account_name": "Union Bank",
        "keywords": ["union bank", "union bank of india", "unionbank", "union back", "union", "ubi"],
        "email_domains": ["unionbankofindia.bank.in", "unionbankofindia.com"],
        "email_senders": ["alerts@unionbankofindia.bank.in"],
    },
    "sbi": {
        "canonical_name": "State Bank of India",
        "account_name": "SBI",
        "keywords": ["state bank of india", "state bank", "sbi", "s b i", "statebank"],
        "email_domains": ["sbi.co.in"],
        "email_senders": ["alerts@sbi.co.in", "donotreply@sbi.co.in"],
    },
    "hdfc": {
        "canonical_name": "HDFC Bank",
        "account_name": "HDFC",
        "keywords": ["hdfc bank", "hdfc", "h d f c"],
        "email_domains": ["hdfcbank.net", "hdfcbank.com"],
        "email_senders": ["alerts@hdfcbank.net"],
    },
    "icici": {
        "canonical_name": "ICICI Bank",
        "account_name": "ICICI",
        "keywords": ["icici bank", "icici", "i c i c i"],
        "email_domains": ["icicibank.com"],
        "email_senders": ["alerts@icicibank.com"],
    },
    "axis": {
        "canonical_name": "Axis Bank",
        "account_name": "Axis",
        "keywords": ["axis bank", "axis"],
        "email_domains": ["axisbank.com"],
        "email_senders": ["alerts@axisbank.com"],
    },
    "kotak": {
        "canonical_name": "Kotak Mahindra Bank",
        "account_name": "Kotak",
        "keywords": ["kotak mahindra", "kotak bank", "kotak"],
        "email_domains": ["kotak.com"],
        "email_senders": ["alerts@kotak.com"],
    },
    "pnb": {
        "canonical_name": "Punjab National Bank",
        "account_name": "PNB",
        "keywords": ["punjab national bank", "punjab national", "pnb"],
        "email_domains": ["pnb.co.in"],
        "email_senders": ["alerts@pnb.co.in"],
    },
    "bob": {
        "canonical_name": "Bank of Baroda",
        "account_name": "Bank of Baroda",
        "keywords": ["bank of baroda", "bob", "baroda bank"],
        "email_domains": ["bankofbaroda.com"],
        "email_senders": ["alerts@bankofbaroda.com"],
    },
    "canara": {
        "canonical_name": "Canara Bank",
        "account_name": "Canara",
        "keywords": ["canara bank", "canara"],
        "email_domains": ["canarabank.com"],
        "email_senders": ["alerts@canarabank.com"],
    },
    "cash": {
        "canonical_name": "Cash",
        "account_name": "Cash",
        "keywords": ["cash", "wallet", "physical cash", "paper money", "petty cash"],
        "email_domains": [],
        "email_senders": [],
    },
}

# Phonetic corrections for common spoken speech slips
PHONETIC_CORRECTIONS: List[Tuple[re.Pattern, str]] = [
    # Indian bank names
    (re.compile(r"\b(?:sarasworth|saraswath|saraswati|saraswathi|sarashwat)\s*(?:bank)?\b", re.IGNORECASE), "Saraswat Bank"),
    (re.compile(r"\bunion\s+(?:back|bark|banck)\b", re.IGNORECASE), "Union Bank"),
    (re.compile(r"\bs\s+b\s+i\b", re.IGNORECASE), "SBI"),
    (re.compile(r"\bh\s+d\s+f\s+c\b", re.IGNORECASE), "HDFC"),
    (re.compile(r"\bi\s+c\s+i\s+c\s+i\b", re.IGNORECASE), "ICICI"),

    # Financial action phrases commonly misheard by Whisper/VOSK
    (re.compile(r"\bcash\s+delay\b", re.IGNORECASE), "cash withdrawal"),
    (re.compile(r"\bcash\s+delays\b", re.IGNORECASE), "cash withdrawals"),
    (re.compile(r"\bmoney\s+deducted\b", re.IGNORECASE), "debit transaction"),
    (re.compile(r"\bmoney\s+debited\b", re.IGNORECASE), "debit transaction"),
    (re.compile(r"\bmoney\s+credited\b", re.IGNORECASE), "credit transaction"),

    # UPI & Apps
    (re.compile(r"\bg\s*pay\b", re.IGNORECASE), "GPay"),
    (re.compile(r"\bphone\s*pe\b", re.IGNORECASE), "PhonePe"),
    (re.compile(r"\bpay\s*tm\b", re.IGNORECASE), "Paytm"),
]


def normalize_entities(text: str) -> str:
    """Normalizes phonetic slips, bank names, and common financial phrases in user text."""
    if not text:
        return ""

    result = text
    for pattern, replacement in PHONETIC_CORRECTIONS:
        result = pattern.sub(replacement, result)

    return result


def resolve_bank_alias(name_or_query: str) -> Optional[str]:
    """Resolves an informal or phonetic bank query string to the canonical account name.

    Returns the account name (e.g. 'Saraswat', 'Union Bank', 'SBI', 'Cash') or None.
    """
    if not name_or_query:
        return None

    clean = name_or_query.strip().lower()

    # 1. Direct check against aliases
    for key, bank_info in INDIAN_BANK_ALIASES.items():
        if clean == key:
            return bank_info["account_name"]
        for kw in bank_info["keywords"]:
            if kw == clean:
                return bank_info["account_name"]

    # 2. Substring check
    for key, bank_info in INDIAN_BANK_ALIASES.items():
        for kw in bank_info["keywords"]:
            if kw in clean:
                return bank_info["account_name"]

    return None


def get_bank_info(name_or_query: str) -> Optional[Dict[str, Any]]:
    """Retrieves full metadata for a recognized bank entity."""
    account_name = resolve_bank_alias(name_or_query)
    if not account_name:
        return None

    for bank_info in INDIAN_BANK_ALIASES.values():
        if bank_info["account_name"].lower() == account_name.lower():
            return bank_info

    return None


def extract_bank_and_intent(query: str) -> Tuple[Optional[str], List[str]]:
    """Extracts identified bank name and intent tokens (e.g. atm, debit, credit) from query.

    Returns: (bank_key, [intent_tokens])
    """
    clean = normalize_entities(query).lower()
    detected_bank = None

    for key, bank_info in INDIAN_BANK_ALIASES.items():
        if any(kw in clean for kw in bank_info["keywords"]):
            detected_bank = key
            break

    intents = []
    if "atm" in clean:
        intents.append("atm")
    if any(w in clean for w in ["withdrawal", "withdraw", "withdrawn"]):
        intents.append("withdrawal")
    if any(w in clean for w in ["debit", "debited", "deducted", "deduct", "spent", "paid"]):
        intents.append("debit")
    if any(w in clean for w in ["credit", "credited", "received", "deposit", "deposited"]):
        intents.append("credit")
    if any(w in clean for w in ["transaction", "transactions", "statement", "alert", "alerts"]):
        intents.append("transaction")

    return detected_bank, intents
