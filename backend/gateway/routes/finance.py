"""Finance REST API Router for VESPER Gateway.

Provides endpoints for accounts, transactions, debts, recurring schedules, and analytics.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.data.models import (
    AccountCreate,
    AccountModel,
    AccountUpdate,
    DebtCreate,
    DebtModel,
    DebtUpdate,
    RecurringTransactionCreate,
    RecurringTransactionModel,
    RecurringTransactionUpdate,
    TransactionCreate,
    TransactionModel,
    TransactionUpdate,
)
from backend.data.repositories.finance import FinanceRepository

logger = logging.getLogger("vesper.gateway.finance")

router = APIRouter(prefix="/api/finance", tags=["finance"])


def get_finance_repo() -> FinanceRepository:
    return FinanceRepository()


# ── Overview & Analytics ─────────────────────────────────────────────────────

@router.get("/overview")
async def get_overview(user_id: str = Query("default_user")) -> Dict[str, Any]:
    """Returns complete financial health summary, balances, debt totals, and monthly cashflow."""
    repo = get_finance_repo()
    return repo.get_financial_overview(user_id=user_id)


@router.get("/analytics")
async def get_analytics(user_id: str = Query("default_user")) -> Dict[str, Any]:
    """Returns spending breakdown by category and 30-day cashflow metrics."""
    repo = get_finance_repo()
    overview = repo.get_financial_overview(user_id=user_id)
    return {
        "monthly_burn": overview["monthly_burn"],
        "monthly_income": overview["monthly_income"],
        "monthly_net_savings": overview["monthly_net_savings"],
        "spending_by_category": overview["spending_by_category"],
    }


# ── Accounts Endpoints ───────────────────────────────────────────────────────

@router.get("/accounts", response_model=List[AccountModel])
async def list_accounts(user_id: str = Query("default_user")) -> List[AccountModel]:
    """Returns all accounts for user, provisioning default 4 accounts if empty."""
    repo = get_finance_repo()
    return repo.get_accounts(user_id=user_id)


@router.post("/accounts", response_model=AccountModel, status_code=status.HTTP_201_CREATED)
async def create_account(account: AccountCreate) -> AccountModel:
    """Creates a new financial account."""
    repo = get_finance_repo()
    try:
        return repo.create_account(account)
    except Exception as e:
        logger.error("Failed to create account: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/accounts/{account_id}", response_model=AccountModel)
async def get_account(account_id: str) -> AccountModel:
    """Retrieves a single account by ID."""
    repo = get_finance_repo()
    acc = repo.get_account(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.put("/accounts/{account_id}", response_model=AccountModel)
async def update_account(account_id: str, update: AccountUpdate) -> AccountModel:
    """Updates account details (name, balance, type, default status)."""
    repo = get_finance_repo()
    acc = repo.update_account(account_id, update)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.post("/accounts/{account_id}/set-default", response_model=AccountModel)
async def set_default_account(account_id: str) -> AccountModel:
    """Designates this account as the primary default account for credits/debits."""
    repo = get_finance_repo()
    acc = repo.update_account(account_id, AccountUpdate(is_default=True))
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str) -> Dict[str, Any]:
    """Deletes an account."""
    repo = get_finance_repo()
    success = repo.delete_account(account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Account not found or could not be deleted")
    return {"success": True, "deleted_account_id": account_id}


# ── Transactions Endpoints ───────────────────────────────────────────────────

@router.get("/transactions", response_model=List[TransactionModel])
async def list_transactions(
    user_id: str = Query("default_user"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    account_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
) -> List[TransactionModel]:
    """Lists filtered transactions with search and pagination."""
    repo = get_finance_repo()
    return repo.get_transactions(
        user_id=user_id,
        limit=limit,
        offset=offset,
        account_id=account_id,
        type=type,
        category=category,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/transactions", response_model=TransactionModel, status_code=status.HTTP_201_CREATED)
async def create_transaction(txn: TransactionCreate) -> TransactionModel:
    """Creates a new transaction and adjusts account balances. Defaults to Union Bank if account_id omitted."""
    repo = get_finance_repo()
    try:
        return repo.add_transaction(txn)
    except Exception as e:
        logger.error("Failed to log transaction: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/transactions/{transaction_id}", response_model=TransactionModel)
async def get_transaction(transaction_id: str) -> TransactionModel:
    """Retrieves a single transaction by ID."""
    repo = get_finance_repo()
    txn = repo.get_transaction(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.put("/transactions/{transaction_id}", response_model=TransactionModel)
async def update_transaction(transaction_id: str, update: TransactionUpdate) -> TransactionModel:
    """Updates a transaction and re-reconciles account balances."""
    repo = get_finance_repo()
    txn = repo.update_transaction(transaction_id, update)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str) -> Dict[str, Any]:
    """Deletes a transaction and reverses its balance adjustment."""
    repo = get_finance_repo()
    success = repo.delete_transaction(transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True, "deleted_transaction_id": transaction_id}


# ── Peer Debts Endpoints ("Owed By" / "Owed To") ─────────────────────────────

@router.get("/debts")
async def list_debts(
    user_id: str = Query("default_user"),
    include_settled: bool = Query(True),
) -> Dict[str, Any]:
    """Returns all debts along with grouped person-level summaries."""
    repo = get_finance_repo()
    debts = repo.get_all_debts(user_id=user_id, include_settled=include_settled)
    summary = repo.get_person_debt_summaries(user_id=user_id)
    return {
        "debts": [d.model_dump() for d in debts],
        "summary": summary,
    }


@router.post("/debts", response_model=DebtModel, status_code=status.HTTP_201_CREATED)
async def create_debt(debt: DebtCreate) -> DebtModel:
    """Records a new peer debt."""
    repo = get_finance_repo()
    try:
        return repo.record_debt(debt)
    except Exception as e:
        logger.error("Failed to record debt: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/debts/{debt_id}", response_model=DebtModel)
async def update_debt(debt_id: str, update: DebtUpdate) -> DebtModel:
    """Updates a peer debt entry."""
    repo = get_finance_repo()
    d = repo.update_debt(debt_id, update)
    if not d:
        raise HTTPException(status_code=404, detail="Debt record not found")
    return d


@router.post("/debts/{debt_id}/settle")
async def settle_debt(
    debt_id: str,
    log_transaction: bool = Query(False, description="Whether to log an automatic cashflow transaction"),
    account_id: Optional[str] = Query(None, description="Account to credit/debit upon settlement"),
) -> Dict[str, Any]:
    """Marks a debt as settled, optionally logging an automatic payment transaction to Union Bank or chosen account."""
    repo = get_finance_repo()
    success = repo.settle_debt(debt_id, log_transaction=log_transaction, account_id=account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Debt record not found or could not be settled")
    return {"success": True, "settled_debt_id": debt_id, "transaction_logged": log_transaction}


@router.delete("/debts/{debt_id}")
async def delete_debt(debt_id: str) -> Dict[str, Any]:
    """Deletes a debt record."""
    repo = get_finance_repo()
    success = repo.delete_debt(debt_id)
    if not success:
        raise HTTPException(status_code=404, detail="Debt record not found")
    return {"success": True, "deleted_debt_id": debt_id}


# ── Recurring & Automated Transactions Endpoints ─────────────────────────────

@router.get("/recurring", response_model=List[RecurringTransactionModel])
async def list_recurring_transactions(
    user_id: str = Query("default_user"),
    active_only: bool = Query(False),
) -> List[RecurringTransactionModel]:
    """Returns recurring transaction rules."""
    repo = get_finance_repo()
    return repo.get_recurring_transactions(user_id=user_id, active_only=active_only)


@router.post("/recurring", response_model=RecurringTransactionModel, status_code=status.HTTP_201_CREATED)
async def create_recurring_transaction(rec: RecurringTransactionCreate) -> RecurringTransactionModel:
    """Registers a periodic automated transaction rule."""
    repo = get_finance_repo()
    try:
        return repo.create_recurring_transaction(rec)
    except Exception as e:
        logger.error("Failed to register recurring transaction: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/recurring/{recurring_id}", response_model=RecurringTransactionModel)
async def update_recurring_transaction(recurring_id: str, update: RecurringTransactionUpdate) -> RecurringTransactionModel:
    """Updates a recurring transaction rule."""
    repo = get_finance_repo()
    rec = repo.update_recurring_transaction(recurring_id, update)
    if not rec:
        raise HTTPException(status_code=404, detail="Recurring rule not found")
    return rec


@router.post("/recurring/{recurring_id}/execute", response_model=TransactionModel)
async def execute_recurring_rule_now(recurring_id: str) -> TransactionModel:
    """Manually triggers immediate execution of a recurring rule."""
    repo = get_finance_repo()
    try:
        return repo.execute_recurring_transaction(recurring_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/recurring/process-due", response_model=List[TransactionModel])
async def process_all_due_recurring(user_id: str = Query("default_user")) -> List[TransactionModel]:
    """Executes all recurring transactions whose next_due_date <= today."""
    repo = get_finance_repo()
    return repo.process_due_recurring_transactions(user_id=user_id)


@router.delete("/recurring/{recurring_id}")
async def delete_recurring_transaction(recurring_id: str) -> Dict[str, Any]:
    """Deletes a recurring transaction rule."""
    repo = get_finance_repo()
    success = repo.delete_recurring_transaction(recurring_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recurring rule not found")
    return {"success": True, "deleted_recurring_id": recurring_id}
