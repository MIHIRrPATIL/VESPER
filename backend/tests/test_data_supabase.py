"""Automated Test Suite for Supabase Data Layer.

Verifies TaskRepository, FinanceRepository, and ShodhMemoryRepository operations
directly against the live Supabase PostgreSQL backend.
"""

from __future__ import annotations

import uuid
import pytest

from backend.data import (
    AccountCreate,
    DebtCreate,
    FinanceRepository,
    MemoryCreate,
    PriorityLevel,
    ShodhMemoryRepository,
    TaskCreate,
    TaskRepository,
    TransactionCreate,
    TransactionType,
    get_supabase_client,
)
from backend.data.models import DebtDirection


@pytest.fixture(scope="module")
def supabase():
    """Returns initialized Supabase client."""
    return get_supabase_client()


# ── 1. Tasks Tests ────────────────────────────────────────────────────────

def test_task_crud_lifecycle(supabase):
    repo = TaskRepository(supabase)
    unique_suffix = uuid.uuid4().hex[:6]
    test_title = f"Pytest Task {unique_suffix}"

    # 1. Create Task
    task_input = TaskCreate(
        title=test_title,
        priority=PriorityLevel.HIGH,
        metadata={"test_tag": "pytest", "extensibility": True},
    )
    created_task = repo.create(task_input)

    assert created_task.id is not None
    assert created_task.title == test_title
    assert created_task.priority == "high"
    assert created_task.done is False
    assert created_task.metadata.get("extensibility") is True

    # 2. Get Task
    fetched = repo.get(created_task.id)
    assert fetched is not None
    assert fetched.id == created_task.id
    assert fetched.title == test_title

    # 3. List Tasks
    task_list = repo.list(include_completed=False)
    assert any(t.id == created_task.id for t in task_list)

    # 4. Mark Done
    marked = repo.mark_done(created_task.id, done=True)
    assert marked is True

    updated = repo.get(created_task.id)
    assert updated is not None
    assert updated.done is True

    # 5. Delete Task
    deleted = repo.delete(created_task.id)
    assert deleted is True

    assert repo.get(created_task.id) is None


# ── 2. Finance Ledger & Accounts Tests ────────────────────────────────────

def test_finance_account_and_transactions(supabase):
    repo = FinanceRepository(supabase)
    unique_suffix = uuid.uuid4().hex[:6]
    account_name = f"Pytest Account {unique_suffix}"

    # 1. Create Account with 10,000 INR
    acc_input = AccountCreate(
        name=account_name,
        balance=10000.0,
        currency="INR",
        metadata={"account_holder": "Mihir"},
    )
    account = repo.create_account(acc_input)
    assert account.id is not None
    assert account.name == account_name
    assert (account.balance) == 10000.0

    try:
        # 2. Add Expense of 2,500 INR
        txn_input = TransactionCreate(
            type=TransactionType.EXPENSE,
            amount=2500.0,
            category="Groceries",
            description="Weekly test supplies",
            account_id=account.id,
        )
        txn = repo.add_transaction(txn_input)
        assert txn.id is not None
        assert (txn.amount) == 2500.0

        # Verify Account Balance Adjusted to 7,500 INR
        acc_updated = repo.get_account_by_name(account_name)
        assert acc_updated is not None
        assert (acc_updated.balance) == 7500.0
        # 3. Add Income of 5,000 INR
        income_txn = TransactionCreate(
            type=TransactionType.INCOME,
            amount=5000.0,
            category="Consulting",
            description="Freelance payout",
            account_id=account.id,
        )
        repo.add_transaction(income_txn)

        # Verify Account Balance Adjusted to 12,500 INR
        acc_after_income = repo.get_account_by_name(account_name)
        assert acc_after_income is not None
        assert (acc_after_income.balance) == 12500.0

    finally:
        # Cleanup
        supabase.table("accounts").delete().eq("id", account.id).execute()


def test_peer_debt_tracking(supabase):
    repo = FinanceRepository(supabase)
    unique_suffix = uuid.uuid4().hex[:6]
    person_name = f"Partner {unique_suffix}"

    # 1. Record Debt
    debt_input = DebtCreate(
        person=person_name,
        amount=1200.0,
        direction=DebtDirection.OWED,
        description="Dinner bill split",
    )
    debt = repo.record_debt(debt_input)
    assert debt.id is not None
    assert debt.person == person_name
    assert (debt.amount) == 1200.0
    assert debt.settled is False

    try:
        # 2. Check Active Debts
        active_debts = repo.get_active_debts()
        assert any(d.id == debt.id for d in active_debts)

        # 3. Settle Debt
        settled = repo.settle_debt(debt.id)
        assert settled is True

        # Verify No Longer in Active Debts
        active_debts_after = repo.get_active_debts()
        assert not any(d.id == debt.id for d in active_debts_after)

    finally:
        # Cleanup
        supabase.table("debts").delete().eq("id", debt.id).execute()


# ── 3. Shodh-Memory Tests ─────────────────────────────────────────────────

def test_shodh_memory_lifecycle(supabase):
    repo = ShodhMemoryRepository(supabase)
    unique_suffix = uuid.uuid4().hex[:6]
    statement_text = f"Mihir likes working with ambient jazz at midnight ({unique_suffix})"

    # 1. Store Fact
    mem_input = MemoryCreate(
        statement=statement_text,
        category="work_routine",
        confidence=0.95,
        metadata={"source": "conversation_inference"},
    )
    memory = repo.store_fact(mem_input)
    assert memory.id is not None
    assert memory.statement == statement_text
    assert memory.category == "work_routine"
    assert memory.access_count == 0

    try:
        # 2. Search Fact by Text
        search_results = repo.search_by_text(f"ambient jazz at midnight ({unique_suffix})")
        assert len(search_results) >= 1
        assert search_results[0].id == memory.id

        # 3. Record Access
        repo.record_access(memory.id)

        # 4. Check Updated Access Count
        mem_list = repo.list_memories(category="work_routine")
        matching = [m for m in mem_list if m.id == memory.id]
        assert len(matching) == 1
        assert matching[0].access_count == 1

    finally:
        # Cleanup
        repo.delete(memory.id)
