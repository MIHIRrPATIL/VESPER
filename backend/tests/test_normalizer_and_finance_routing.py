"""Tests for entity normalizer, smart Gmail query construction, and finance routing."""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock

from backend.agent.normalizer import (
    extract_bank_and_intent,
    get_bank_info,
    normalize_entities,
    resolve_bank_alias,
)
from backend.agent.planner import SwarmPlanner
from backend.agent.specialists.email_specialist import EmailSpecialist
from backend.agent.specialists.finance_specialist import FinanceSpecialist
from backend.data.models import AccountModel, AccountType, TransactionModel, TransactionType
from backend.data.repositories.finance import FinanceRepository


# ── 1. Normalizer Unit Tests ──────────────────────────────────────────────────

def test_normalize_entities_phonetic_banks():
    assert "Saraswat Bank" in normalize_entities("look for a transaction from Sarasworth")
    assert "Saraswat Bank" in normalize_entities("check emails from saraswati bank")
    assert "Union Bank" in normalize_entities("check balance in union back")
    assert "SBI" in normalize_entities("check account in s b i")


def test_normalize_entities_financial_terms():
    assert "cash withdrawal" in normalize_entities("see if there are any new ATM transactions or any other cash delay")
    assert "debit transaction" in normalize_entities("money deducted from my account")
    assert "credit transaction" in normalize_entities("money credited from company")


def test_resolve_bank_alias():
    assert resolve_bank_alias("sarasworth") == "Saraswat"
    assert resolve_bank_alias("saraswath") == "Saraswat"
    assert resolve_bank_alias("saraswati bank") == "Saraswat"
    assert resolve_bank_alias("union back") == "Union Bank"
    assert resolve_bank_alias("union bank of india") == "Union Bank"
    assert resolve_bank_alias("state bank of india") == "SBI"
    assert resolve_bank_alias("sbi") == "SBI"
    assert resolve_bank_alias("cash") == "Cash"
    assert resolve_bank_alias("wallet") == "Cash"


def test_extract_bank_and_intent():
    bank, intents = extract_bank_and_intent("recent ATM transactions from saraswat bank")
    assert bank == "saraswat"
    assert "atm" in intents
    assert "transaction" in intents

    bank2, intents2 = extract_bank_and_intent("money deducted emails from Sarasworth")
    assert bank2 == "saraswat"
    assert "debit" in intents2


# ── 2. Smart Gmail Query Generation Tests ─────────────────────────────────────

def test_build_smart_gmail_queries_bank_and_intent():
    queries = EmailSpecialist.build_smart_gmail_queries("Yes, look for a transaction from Sarasworth.")
    assert any("saraswat" in q.lower() for q in queries)
    assert any("transaction" in q.lower() or "alert" in q.lower() for q in queries)

    queries2 = EmailSpecialist.build_smart_gmail_queries(
        "can you look for any recent ATM transactions or any money deducted emails from saraswat bank"
    )
    assert any("saraswat" in q.lower() for q in queries2)
    assert any("atm" in q.lower() or "debit" in q.lower() for q in queries2)


def test_build_smart_gmail_queries_general_atm():
    queries = EmailSpecialist.build_smart_gmail_queries("see if there are any new ATM transactions or any other cash delay")
    assert any("atm" in q.lower() for q in queries)
    assert any("cash withdrawal" in q.lower() for q in queries)


# ── 3. Finance Specialist Tests ───────────────────────────────────────────────

class MockFinanceRepo:
    def __init__(self):
        self.accounts = [
            AccountModel(id="acc_ub", user_id="u1", name="Union Bank", type=AccountType.BANK, balance=15000.0, currency="INR", is_default=True),
            AccountModel(id="acc_sbi", user_id="u1", name="SBI", type=AccountType.BANK, balance=5000.0, currency="INR", is_default=False),
            AccountModel(id="acc_sb", user_id="u1", name="Saraswat", type=AccountType.BANK, balance=20000.0, currency="INR", is_default=False),
            AccountModel(id="acc_c", user_id="u1", name="Cash", type=AccountType.CASH, balance=2500.0, currency="INR", is_default=False),
        ]

    def ensure_default_accounts(self, user_id="default_user"):
        return self.accounts

    def get_accounts(self, user_id="default_user"):
        return self.accounts

    def get_account_by_name(self, name: str, user_id="default_user"):
        clean = name.strip().lower()
        alias = resolve_bank_alias(clean)
        for a in self.accounts:
            if a.name.lower() == clean or (alias and a.name.lower() == alias.lower()):
                return a
        return None

    def get_financial_overview(self, user_id="default_user"):
        total_nw = sum(a.balance for a in self.accounts)
        return {
            "total_net_worth": total_nw,
            "bank_balance": 40000.0,
            "cash_balance": 2500.0,
            "accounts": [a.model_dump() for a in self.accounts],
            "debts": {
                "total_owed_to_user": 3500.0,
                "total_user_owes": 0.0,
                "net_debt": 3500.0,
            },
            "monthly_burn": 4500.0,
            "monthly_income": 25000.0,
        }

    def get_recent_transactions(self, limit=4, user_id="default_user"):
        return [
            TransactionModel(
                id="txn_01",
                user_id="u1",
                account_id="acc_sb",
                amount=2200.0,
                type=TransactionType.EXPENSE,
                category="ACH Debit",
                description="ACH Debit:TP ACH PRUDENT",
            )
        ]

    def get_transactions(self, user_id="default_user", limit=5, offset=0, account_id=None, type=None, category=None, search=None):
        return [
            TransactionModel(
                id="txn_01",
                user_id="u1",
                account_id=account_id or "acc_sb",
                amount=2200.0,
                type=TransactionType.EXPENSE,
                category="ACH Debit",
                description="ACH Debit:TP ACH PRUDENT",
            )
        ]


@pytest.mark.asyncio
async def test_finance_specialist_financial_summary():
    repo = MockFinanceRepo()
    fs = FinanceSpecialist(repo=repo)
    res = await fs.execute("get_financial_summary", {})

    assert res.success is True
    assert res.action == "get_financial_summary"
    assert res.data["total_net_worth"] == 42500.0
    assert "₹42,500.00" in res.speech_summary
    assert "Union Bank" in res.speech_summary
    assert "Saraswat" in res.speech_summary
    assert res.card_payload["type"] == "finance_summary_card"
    assert len(res.card_payload["accounts"]) == 4


@pytest.mark.asyncio
async def test_finance_specialist_list_transactions_alias_resolution():
    repo = MockFinanceRepo()
    fs = FinanceSpecialist(repo=repo)
    res = await fs.execute("list_transactions", {"account_name": "Sarasworth"})

    assert res.success is True
    assert res.action == "list_transactions"
    assert res.data["account"] == "Saraswat"
    assert res.card_payload["type"] == "finance_transaction_list_card"
    assert len(res.data["transactions"]) == 1


# ── 4. Planner Deterministic Routing Tests ────────────────────────────────────

def test_planner_financial_standing_routing():
    planner = SwarmPlanner()

    p1 = planner._check_deterministic_prefilter("How am I doing financially?")
    assert p1 is not None
    assert p1.provider_used == "prefilter"
    assert p1.steps[0]["agent"] == "finance"
    assert p1.steps[0]["action"] == "get_financial_summary"

    p2 = planner._check_deterministic_prefilter("What is my financial health?")
    assert p2 is not None
    assert p2.steps[0]["agent"] == "finance"
    assert p2.steps[0]["action"] == "get_financial_summary"

    p3 = planner._check_deterministic_prefilter("How are my finances?")
    assert p3 is not None
    assert p3.steps[0]["agent"] == "finance"
    assert p3.steps[0]["action"] == "get_financial_summary"


def test_planner_balance_with_bank_alias():
    planner = SwarmPlanner()

    p = planner._check_deterministic_prefilter("Check balance in Sarasworth")
    assert p is not None
    assert p.steps[0]["agent"] == "finance"
    assert p.steps[0]["action"] == "get_balance"
    assert p.steps[0]["params"].get("account_name") == "Saraswat"


def test_planner_list_transactions_routing():
    planner = SwarmPlanner()

    p = planner._check_deterministic_prefilter("Show my recent transactions")
    assert p is not None
    assert p.steps[0]["agent"] == "finance"
    assert p.steps[0]["action"] == "list_transactions"


def test_planner_candidate_specialists_selection():
    planner = SwarmPlanner()

    c1 = planner._select_candidate_specialists("How am I doing financially?")
    assert "finance" in c1

    c2 = planner._select_candidate_specialists("Check balance in Sarasworth")
    assert "finance" in c2

    c3 = planner._select_candidate_specialists("Look for an email from Sarasworth")
    assert "email" in c3
