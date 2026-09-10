"""Finance Repository for Supabase.

Handles accounts, double-entry transactions with balance adjustments,
peer-to-peer debts, recurring/automated transactions, and financial analytics.
"""

from __future__ import annotations

import calendar
import datetime as dt
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from supabase import Client

from backend.data.client import get_supabase_client
from backend.data.models import (
    AccountCreate,
    AccountModel,
    AccountType,
    AccountUpdate,
    DebtCreate,
    DebtModel,
    DebtUpdate,
    FrequencyType,
    RecurringTransactionCreate,
    RecurringTransactionModel,
    RecurringTransactionUpdate,
    TransactionCreate,
    TransactionModel,
    TransactionType,
    TransactionUpdate,
)

logger = logging.getLogger("vesper.data.finance")


def compute_next_due_date(
    current_date: dt.date,
    frequency: str,
    day_of_month: Optional[int] = None,
) -> dt.date:
    """Calculates the subsequent execution date for a recurring transaction rule."""
    freq = frequency.lower()
    if freq == "daily":
        return current_date + dt.timedelta(days=1)
    elif freq == "weekly":
        return current_date + dt.timedelta(weeks=1)
    elif freq == "biweekly":
        return current_date + dt.timedelta(weeks=2)
    elif freq == "monthly":
        year = current_date.year + (1 if current_date.month == 12 else 0)
        month = 1 if current_date.month == 12 else current_date.month + 1
        target_day = day_of_month or current_date.day
        max_days = calendar.monthrange(year, month)[1]
        day = min(target_day, max_days)
        return dt.date(year, month, day)
    elif freq == "quarterly":
        month = current_date.month + 3
        year = current_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        target_day = day_of_month or current_date.day
        max_days = calendar.monthrange(year, month)[1]
        day = min(target_day, max_days)
        return dt.date(year, month, day)
    elif freq == "yearly":
        year = current_date.year + 1
        month = current_date.month
        target_day = day_of_month or current_date.day
        max_days = calendar.monthrange(year, month)[1]
        day = min(target_day, max_days)
        return dt.date(year, month, day)
    return current_date + dt.timedelta(days=30)


class FinanceRepository:
    """Repository handling all financial accounts, transactions, debts, and recurring schedules."""

    CORE_ACCOUNTS: List[Dict[str, Any]] = [
        {"name": "Union Bank", "type": AccountType.BANK, "is_default": True, "balance": 0.0},
        {"name": "SBI", "type": AccountType.BANK, "is_default": False, "balance": 0.0},
        {"name": "Saraswat", "type": AccountType.BANK, "is_default": False, "balance": 0.0},
        {"name": "Cash", "type": AccountType.CASH, "is_default": False, "balance": 0.0},
    ]

    def __init__(self, client: Optional[Client] = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        if self._client is not None:
            return self._client
        return get_supabase_client()

    # ── Initialization & Provisioning ────────────────────────────────────────

    def ensure_default_accounts(self, user_id: str = "default_user") -> List[AccountModel]:
        """Ensures the 4 core accounts exist: Union Bank (Default), SBI, Saraswat, and Cash.
        Migrates legacy 'Primary Account' to 'Union Bank' if found.
        """
        res = self.client.table("accounts").select("*").eq("user_id", user_id).execute()
        existing = [AccountModel.model_validate(row) for row in res.data or []]
        existing_names = {a.name.lower(): a for a in existing}

        # 1. Check for legacy 'Primary Account' to seamlessly migrate
        if "primary account" in existing_names and "union bank" not in existing_names:
            primary = existing_names["primary account"]
            self.client.table("accounts").update({
                "name": "Union Bank",
                "is_default": True,
                "type": "bank",
            }).eq("id", primary.id).execute()
            logger.info("Migrated legacy 'Primary Account' to 'Union Bank' [id=%s]", primary.id)
            res = self.client.table("accounts").select("*").eq("user_id", user_id).execute()
            existing = [AccountModel.model_validate(row) for row in res.data or []]
            existing_names = {a.name.lower(): a for a in existing}

        # 2. Provision any missing core accounts
        created = False
        for core in self.CORE_ACCOUNTS:
            name_key = core["name"].lower()
            if name_key not in existing_names:
                insert_data = {
                    "user_id": user_id,
                    "name": core["name"],
                    "type": core["type"].value,
                    "balance": core["balance"],
                    "currency": "INR",
                    "is_default": core["is_default"],
                    "metadata": {"system_provisioned": True},
                }
                self.client.table("accounts").insert(insert_data).execute()
                created = True
                logger.info("Provisioned core account '%s'", core["name"])

        # 3. Ensure exactly one default account exists
        if created or existing:
            res = self.client.table("accounts").select("*").eq("user_id", user_id).execute()
            existing = [AccountModel.model_validate(row) for row in res.data or []]
            has_default = any(a.is_default for a in existing)
            if not has_default and existing:
                union = next((a for a in existing if "union" in a.name.lower()), existing[0])
                self.client.table("accounts").update({"is_default": True}).eq("id", union.id).execute()
                res = self.client.table("accounts").select("*").eq("user_id", user_id).execute()
                existing = [AccountModel.model_validate(row) for row in res.data or []]

        return existing

    # ── Accounts CRUD ────────────────────────────────────────────────────────

    def create_account(self, account: AccountCreate) -> AccountModel:
        """Creates a new financial account. If set as default, clears default on other accounts."""
        if account.is_default:
            self.client.table("accounts").update({"is_default": False}).eq("user_id", account.user_id).execute()

        data = {
            "user_id": account.user_id,
            "name": account.name.strip(),
            "type": account.type.value,
            "balance": float(account.balance),
            "currency": account.currency.upper(),
            "is_default": bool(account.is_default),
            "metadata": account.metadata,
        }
        res = self.client.table("accounts").insert(data).execute()
        if not res.data:
            raise RuntimeError("Failed to create account in Supabase.")
        return AccountModel.model_validate(res.data[0])

    def get_accounts(self, user_id: str = "default_user") -> List[AccountModel]:
        """Returns all accounts belonging to the user, provisioning defaults if needed."""
        res = self.client.table("accounts").select("*").eq("user_id", user_id).order("name").execute()
        if not res.data:
            return self.ensure_default_accounts(user_id=user_id)
        return [AccountModel.model_validate(row) for row in res.data]

    def get_default_account(self, user_id: str = "default_user") -> AccountModel:
        """Returns the primary/default account for transactions."""
        accounts = self.get_accounts(user_id=user_id)
        default = next((a for a in accounts if a.is_default), None)
        if default:
            return default
        union = next((a for a in accounts if "union" in a.name.lower()), None)
        if union:
            return union
        return accounts[0]

    def get_account(self, account_id: str) -> Optional[AccountModel]:
        """Looks up an account by its unique ID."""
        res = self.client.table("accounts").select("*").eq("id", account_id).execute()
        if res.data:
            return AccountModel.model_validate(res.data[0])
        return None

    def get_account_by_name(self, name: str, user_id: str = "default_user") -> Optional[AccountModel]:
        """Looks up an account by fuzzy name match and phonetic aliases (e.g. 'Sarasworth', 'Union back', 'SBI', 'Cash')."""
        accounts = self.get_accounts(user_id=user_id)
        query = name.strip().lower()

        # 1. Check canonical bank alias resolver first (handles phonetic slips like 'sarasworth', 'union back')
        try:
            from backend.agent.normalizer import resolve_bank_alias
            resolved_canonical = resolve_bank_alias(query)
            if resolved_canonical:
                for a in accounts:
                    if a.name.lower() == resolved_canonical.lower():
                        return a
        except Exception as e:
            logger.debug(f"[FinanceRepo] Alias resolution exception: {e}")

        # 2. Direct exact match
        for a in accounts:
            if a.name.lower() == query:
                return a

        # 3. Fuzzy / alias match
        for a in accounts:
            a_lower = a.name.lower()
            if query in a_lower or a_lower in query:
                return a
        if "sbi" in query or "state bank" in query:
            return next((a for a in accounts if "sbi" in a.name.lower()), None)
        if "union" in query:
            return next((a for a in accounts if "union" in a.name.lower()), None)
        if "saraswat" in query or "sarasworth" in query or "saraswati" in query:
            return next((a for a in accounts if "saraswat" in a.name.lower()), None)
        if "cash" in query or "wallet" in query:
            return next((a for a in accounts if "cash" in a.name.lower() or a.type == "cash"), None)
        return None

    def update_account(self, account_id: str, update: AccountUpdate) -> Optional[AccountModel]:
        """Updates account details (name, balance, type, is_default, metadata)."""
        current = self.get_account(account_id)
        if not current:
            return None

        update_dict: Dict[str, Any] = {}
        if update.name is not None:
            update_dict["name"] = update.name.strip()
        if update.type is not None:
            update_dict["type"] = update.type.value
        if update.balance is not None:
            update_dict["balance"] = float(update.balance)
        if update.currency is not None:
            update_dict["currency"] = update.currency.upper()
        if update.metadata is not None:
            update_dict["metadata"] = update.metadata

        if update.is_default is True:
            self.client.table("accounts").update({"is_default": False}).eq("user_id", current.user_id).execute()
            update_dict["is_default"] = True
        elif update.is_default is False:
            update_dict["is_default"] = False

        update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

        res = self.client.table("accounts").update(update_dict).eq("id", account_id).execute()
        if res.data:
            return AccountModel.model_validate(res.data[0])
        return None

    def delete_account(self, account_id: str) -> bool:
        """Deletes an account from Supabase."""
        res = self.client.table("accounts").delete().eq("id", account_id).execute()
        return len(res.data or []) > 0

    # ── Transactions CRUD ────────────────────────────────────────────────────

    def add_transaction(self, txn: TransactionCreate) -> TransactionModel:
        """Logs a transaction and atomically adjusts affected account balances.
        If no account_id is supplied, defaults to the user's default account (Union Bank).
        """
        target_account_id = txn.account_id
        if not target_account_id:
            default_acc = self.get_default_account(user_id=txn.user_id)
            target_account_id = default_acc.id

        txn_data = {
            "user_id": txn.user_id,
            "type": txn.type.value,
            "amount": float(txn.amount),
            "category": txn.category,
            "description": txn.description,
            "account_id": target_account_id,
            "to_account_id": txn.to_account_id,
            "date": txn.date.isoformat() if txn.date else datetime.now(timezone.utc).date().isoformat(),
            "metadata": txn.metadata,
        }
        res = self.client.table("transactions").insert(txn_data).execute()
        if not res.data:
            raise RuntimeError("Failed to insert transaction into Supabase.")

        created_txn = TransactionModel.model_validate(res.data[0])

        # Adjust Account Balances
        if target_account_id:
            acc_res = self.client.table("accounts").select("*").eq("id", target_account_id).execute()
            if acc_res.data:
                row = dict(acc_res.data[0])
                curr_balance = float(row.get("balance") or 0.0)
                if txn.type == TransactionType.EXPENSE:
                    new_balance = curr_balance - txn.amount
                elif txn.type == TransactionType.INCOME:
                    new_balance = curr_balance + txn.amount
                elif txn.type == TransactionType.TRANSFER:
                    new_balance = curr_balance - txn.amount
                else:
                    new_balance = curr_balance

                self.client.table("accounts").update({
                    "balance": new_balance,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", target_account_id).execute()

        # If Transfer, credit the destination account
        if txn.type == TransactionType.TRANSFER and txn.to_account_id:
            to_acc_res = self.client.table("accounts").select("*").eq("id", txn.to_account_id).execute()
            if to_acc_res.data:
                row = dict(to_acc_res.data[0])
                curr_to_balance = float(row.get("balance") or 0.0)
                new_to_balance = curr_to_balance + txn.amount
                self.client.table("accounts").update({
                    "balance": new_to_balance,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", txn.to_account_id).execute()

        return created_txn

    def get_transactions(
        self,
        user_id: str = "default_user",
        limit: int = 50,
        offset: int = 0,
        account_id: Optional[str] = None,
        type: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TransactionModel]:
        """Returns filtered transactions with pagination and search."""
        query = self.client.table("transactions").select("*").eq("user_id", user_id)

        if account_id:
            query = query.or_(f"account_id.eq.{account_id},to_account_id.eq.{account_id}")
        if type:
            query = query.eq("type", type)
        if category:
            query = query.ilike("category", f"%{category}%")
        if search:
            query = query.or_(f"description.ilike.%{search}%,category.ilike.%{search}%")
        if start_date:
            query = query.gte("date", start_date)
        if end_date:
            query = query.lte("date", end_date)

        res = query.order("date", desc=True).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return [TransactionModel.model_validate(row) for row in res.data or []]

    def get_recent_transactions(
        self,
        user_id: str = "default_user",
        limit: int = 20,
    ) -> List[TransactionModel]:
        """Returns the most recent transactions."""
        return self.get_transactions(user_id=user_id, limit=limit)

    def get_transaction(self, transaction_id: str) -> Optional[TransactionModel]:
        """Looks up a single transaction by ID."""
        res = self.client.table("transactions").select("*").eq("id", transaction_id).execute()
        if res.data:
            return TransactionModel.model_validate(res.data[0])
        return None

    def update_transaction(self, transaction_id: str, update: TransactionUpdate) -> Optional[TransactionModel]:
        """Updates a transaction and reconciles balance deltas on both source and destination accounts."""
        old_txn = self.get_transaction(transaction_id)
        if not old_txn:
            return None

        # 1. Reverse old transaction effects on accounts
        if old_txn.account_id:
            acc_res = self.client.table("accounts").select("balance").eq("id", old_txn.account_id).execute()
            if acc_res.data:
                bal = float(acc_res.data[0]["balance"])
                if old_txn.type == "expense":
                    bal += old_txn.amount
                elif old_txn.type == "income":
                    bal -= old_txn.amount
                elif old_txn.type == "transfer":
                    bal += old_txn.amount
                self.client.table("accounts").update({"balance": bal}).eq("id", old_txn.account_id).execute()

        if old_txn.type == "transfer" and old_txn.to_account_id:
            to_acc_res = self.client.table("accounts").select("balance").eq("id", old_txn.to_account_id).execute()
            if to_acc_res.data:
                to_bal = float(to_acc_res.data[0]["balance"]) - old_txn.amount
                self.client.table("accounts").update({"balance": to_bal}).eq("id", old_txn.to_account_id).execute()

        # 2. Build updated data
        new_type = update.type.value if update.type else old_txn.type
        new_amount = float(update.amount) if update.amount is not None else old_txn.amount
        new_account_id = update.account_id if update.account_id is not None else old_txn.account_id
        new_to_account_id = update.to_account_id if update.to_account_id is not None else old_txn.to_account_id

        update_dict: Dict[str, Any] = {}
        if update.type is not None:
            update_dict["type"] = new_type
        if update.amount is not None:
            update_dict["amount"] = new_amount
        if update.category is not None:
            update_dict["category"] = update.category
        if update.description is not None:
            update_dict["description"] = update.description
        if update.account_id is not None:
            update_dict["account_id"] = new_account_id
        if update.to_account_id is not None:
            update_dict["to_account_id"] = new_to_account_id
        if update.date is not None:
            update_dict["date"] = update.date.isoformat()
        if update.metadata is not None:
            update_dict["metadata"] = update.metadata

        res = self.client.table("transactions").update(update_dict).eq("id", transaction_id).execute()
        if not res.data:
            return None

        # 3. Apply new transaction balance effects
        if new_account_id:
            acc_res = self.client.table("accounts").select("balance").eq("id", new_account_id).execute()
            if acc_res.data:
                bal = float(acc_res.data[0]["balance"])
                if new_type == "expense":
                    bal -= new_amount
                elif new_type == "income":
                    bal += new_amount
                elif new_type == "transfer":
                    bal -= new_amount
                self.client.table("accounts").update({"balance": bal}).eq("id", new_account_id).execute()

        if new_type == "transfer" and new_to_account_id:
            to_acc_res = self.client.table("accounts").select("balance").eq("id", new_to_account_id).execute()
            if to_acc_res.data:
                to_bal = float(to_acc_res.data[0]["balance"]) + new_amount
                self.client.table("accounts").update({"balance": to_bal}).eq("id", new_to_account_id).execute()

        return TransactionModel.model_validate(res.data[0])

    def delete_transaction(self, transaction_id: str) -> bool:
        """Deletes a transaction and reverses its effect on the associated account balance(s)."""
        res = self.client.table("transactions").select("*").eq("id", transaction_id).execute()
        if not res.data:
            return False

        txn = TransactionModel.model_validate(res.data[0])
        if txn.account_id:
            acc_res = self.client.table("accounts").select("balance").eq("id", txn.account_id).execute()
            if acc_res.data:
                curr_balance = float(acc_res.data[0]["balance"])
                if txn.type == "expense":
                    new_balance = curr_balance + txn.amount
                elif txn.type == "income":
                    new_balance = curr_balance - txn.amount
                elif txn.type == "transfer":
                    new_balance = curr_balance + txn.amount
                else:
                    new_balance = curr_balance
                self.client.table("accounts").update({"balance": new_balance}).eq("id", txn.account_id).execute()

        if txn.type == "transfer" and txn.to_account_id:
            to_acc_res = self.client.table("accounts").select("balance").eq("id", txn.to_account_id).execute()
            if to_acc_res.data:
                to_bal = float(to_acc_res.data[0]["balance"]) - txn.amount
                self.client.table("accounts").update({"balance": to_bal}).eq("id", txn.to_account_id).execute()

        self.client.table("transactions").delete().eq("id", transaction_id).execute()
        return True

    # ── Peer Debts CRUD ("Owed By" & "Owed To") ──────────────────────────────

    def record_debt(self, debt: DebtCreate) -> DebtModel:
        """Records a new peer debt (owe or owed)."""
        data = {
            "user_id": debt.user_id,
            "person": debt.person.strip().title(),
            "amount": float(debt.amount),
            "direction": debt.direction.value,
            "description": debt.description,
            "metadata": debt.metadata,
        }
        res = self.client.table("debts").insert(data).execute()
        if not res.data:
            raise RuntimeError("Failed to record debt in Supabase.")
        return DebtModel.model_validate(res.data[0])

    def get_all_debts(self, user_id: str = "default_user", include_settled: bool = True) -> List[DebtModel]:
        """Returns all debts, optionally filtering out settled ones."""
        query = self.client.table("debts").select("*").eq("user_id", user_id)
        if not include_settled:
            query = query.eq("settled", False)
        res = query.order("created_at", desc=True).execute()
        return [DebtModel.model_validate(row) for row in res.data or []]

    def get_active_debts(self, user_id: str = "default_user") -> List[DebtModel]:
        """Returns all unsettled debts."""
        return self.get_all_debts(user_id=user_id, include_settled=False)

    def get_debt(self, debt_id: str) -> Optional[DebtModel]:
        """Looks up a single debt by ID."""
        res = self.client.table("debts").select("*").eq("id", debt_id).execute()
        if res.data:
            return DebtModel.model_validate(res.data[0])
        return None

    def update_debt(self, debt_id: str, update: DebtUpdate) -> Optional[DebtModel]:
        """Updates a peer debt entry."""
        update_dict: Dict[str, Any] = {}
        if update.person is not None:
            update_dict["person"] = update.person.strip().title()
        if update.amount is not None:
            update_dict["amount"] = float(update.amount)
        if update.direction is not None:
            update_dict["direction"] = update.direction.value
        if update.description is not None:
            update_dict["description"] = update.description
        if update.settled is not None:
            update_dict["settled"] = update.settled
            if update.settled:
                update_dict["settled_at"] = datetime.now(timezone.utc).isoformat()
            else:
                update_dict["settled_at"] = None
        if update.metadata is not None:
            update_dict["metadata"] = update.metadata

        res = self.client.table("debts").update(update_dict).eq("id", debt_id).execute()
        if res.data:
            return DebtModel.model_validate(res.data[0])
        return None

    def delete_debt(self, debt_id: str) -> bool:
        """Deletes a debt record."""
        res = self.client.table("debts").delete().eq("id", debt_id).execute()
        return len(res.data or []) > 0

    def settle_debt(
        self,
        debt_id: str,
        log_transaction: bool = False,
        account_id: Optional[str] = None,
    ) -> bool:
        """Marks a debt as settled. Optionally auto-creates a double-entry transaction
        into Union Bank (or specified account) to account for the cashflow.
        """
        debt = self.get_debt(debt_id)
        if not debt:
            return False

        now_iso = datetime.now(timezone.utc).isoformat()
        res = (
            self.client.table("debts")
            .update({"settled": True, "settled_at": now_iso})
            .eq("id", debt_id)
            .execute()
        )
        success = len(res.data or []) > 0

        if success and log_transaction:
            # If direction is 'owed' -> Someone owed me money and paid me back -> Income!
            # If direction is 'owe' -> I owed someone and paid them back -> Expense!
            target_acc = account_id or self.get_default_account(user_id=debt.user_id).id
            if debt.direction == "owed":
                self.add_transaction(
                    TransactionCreate(
                        user_id=debt.user_id,
                        type=TransactionType.INCOME,
                        amount=debt.amount,
                        category="Debt Repayment",
                        description=f"Received debt settlement from {debt.person}",
                        account_id=target_acc,
                        metadata={"settled_debt_id": debt_id, "person": debt.person},
                    )
                )
            else:
                self.add_transaction(
                    TransactionCreate(
                        user_id=debt.user_id,
                        type=TransactionType.EXPENSE,
                        amount=debt.amount,
                        category="Debt Settlement",
                        description=f"Paid settled debt to {debt.person}",
                        account_id=target_acc,
                        metadata={"settled_debt_id": debt_id, "person": debt.person},
                    )
                )

        return success

    def update_debt_amount(self, debt_id: str, new_amount: float) -> bool:
        """Updates the remaining amount on an existing debt."""
        res = self.client.table("debts").update({"amount": new_amount}).eq("id", debt_id).execute()
        return len(res.data or []) > 0

    def get_person_debt_summaries(self, user_id: str = "default_user") -> Dict[str, Any]:
        """Groups all active debts by person, computing individual and global net positions."""
        debts = self.get_active_debts(user_id=user_id)
        person_map: Dict[str, Dict[str, Any]] = {}
        total_owed_to_user = 0.0
        total_user_owes = 0.0

        for d in debts:
            p = d.person.strip().title()
            if p not in person_map:
                person_map[p] = {
                    "person": p,
                    "owed_to_user": 0.0,
                    "user_owes": 0.0,
                    "net_amount": 0.0,
                    "debts": [],
                }

            if d.direction == "owed":
                person_map[p]["owed_to_user"] += d.amount
                total_owed_to_user += d.amount
            else:
                person_map[p]["user_owes"] += d.amount
                total_user_owes += d.amount

            person_map[p]["debts"].append(d.model_dump())

        # Compute net for each person
        # Positive = They owe user; Negative = User owes them
        person_list = []
        for p, data in person_map.items():
            data["net_amount"] = data["owed_to_user"] - data["user_owes"]
            person_list.append(data)

        # Sort by largest net receivable first
        person_list.sort(key=lambda x: x["net_amount"], reverse=True)

        return {
            "total_owed_to_user": total_owed_to_user,
            "total_user_owes": total_user_owes,
            "net_debt_position": total_owed_to_user - total_user_owes,
            "people": person_list,
        }

    # ── Recurring & Automated Transactions ───────────────────────────────────

    def create_recurring_transaction(self, rec: RecurringTransactionCreate) -> RecurringTransactionModel:
        """Registers a periodic automated transaction rule."""
        target_account_id = rec.account_id
        if not target_account_id:
            default_acc = self.get_default_account(user_id=rec.user_id)
            target_account_id = default_acc.id

        today = datetime.now(timezone.utc).date()
        next_due = rec.next_due_date or compute_next_due_date(
            rec.start_date or today,
            rec.frequency.value,
            rec.day_of_month,
        )

        data = {
            "user_id": rec.user_id,
            "name": rec.name.strip(),
            "amount": float(rec.amount),
            "type": rec.type.value,
            "category": rec.category,
            "account_id": target_account_id,
            "to_account_id": rec.to_account_id,
            "frequency": rec.frequency.value,
            "day_of_month": rec.day_of_month,
            "day_of_week": rec.day_of_week,
            "start_date": (rec.start_date or today).isoformat(),
            "end_date": rec.end_date.isoformat() if rec.end_date else None,
            "next_due_date": next_due.isoformat(),
            "active": rec.active,
            "auto_execute": rec.auto_execute,
            "metadata": rec.metadata,
        }
        res = self.client.table("recurring_transactions").insert(data).execute()
        if not res.data:
            raise RuntimeError("Failed to create recurring transaction rule.")
        return RecurringTransactionModel.model_validate(res.data[0])

    def get_recurring_transactions(
        self,
        user_id: str = "default_user",
        active_only: bool = False,
    ) -> List[RecurringTransactionModel]:
        """Lists all recurring transaction rules."""
        query = self.client.table("recurring_transactions").select("*").eq("user_id", user_id)
        if active_only:
            query = query.eq("active", True)
        res = query.order("next_due_date").execute()
        return [RecurringTransactionModel.model_validate(row) for row in res.data or []]

    def get_recurring_transaction(self, recurring_id: str) -> Optional[RecurringTransactionModel]:
        """Looks up a recurring rule by ID."""
        res = self.client.table("recurring_transactions").select("*").eq("id", recurring_id).execute()
        if res.data:
            return RecurringTransactionModel.model_validate(res.data[0])
        return None

    def update_recurring_transaction(
        self,
        recurring_id: str,
        update: RecurringTransactionUpdate,
    ) -> Optional[RecurringTransactionModel]:
        """Updates a recurring transaction rule."""
        update_dict: Dict[str, Any] = {}
        if update.name is not None:
            update_dict["name"] = update.name.strip()
        if update.amount is not None:
            update_dict["amount"] = float(update.amount)
        if update.type is not None:
            update_dict["type"] = update.type.value
        if update.category is not None:
            update_dict["category"] = update.category
        if update.account_id is not None:
            update_dict["account_id"] = update.account_id
        if update.to_account_id is not None:
            update_dict["to_account_id"] = update.to_account_id
        if update.frequency is not None:
            update_dict["frequency"] = update.frequency.value
        if update.day_of_month is not None:
            update_dict["day_of_month"] = update.day_of_month
        if update.day_of_week is not None:
            update_dict["day_of_week"] = update.day_of_week
        if update.start_date is not None:
            update_dict["start_date"] = update.start_date.isoformat()
        if update.end_date is not None:
            update_dict["end_date"] = update.end_date.isoformat()
        if update.next_due_date is not None:
            update_dict["next_due_date"] = update.next_due_date.isoformat()
        if update.active is not None:
            update_dict["active"] = update.active
        if update.auto_execute is not None:
            update_dict["auto_execute"] = update.auto_execute
        if update.metadata is not None:
            update_dict["metadata"] = update.metadata

        update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        res = self.client.table("recurring_transactions").update(update_dict).eq("id", recurring_id).execute()
        if res.data:
            return RecurringTransactionModel.model_validate(res.data[0])
        return None

    def delete_recurring_transaction(self, recurring_id: str) -> bool:
        """Deletes a recurring transaction rule."""
        res = self.client.table("recurring_transactions").delete().eq("id", recurring_id).execute()
        return len(res.data or []) > 0

    def execute_recurring_transaction(self, recurring_id: str) -> TransactionModel:
        """Manually or automatically triggers execution of a recurring rule:
        Logs the transaction, updates balances, advances next_due_date.
        """
        rec = self.get_recurring_transaction(recurring_id)
        if not rec:
            raise ValueError(f"Recurring transaction '{recurring_id}' not found.")

        # Log actual transaction
        today = datetime.now(timezone.utc).date()
        txn = self.add_transaction(
            TransactionCreate(
                user_id=rec.user_id,
                type=TransactionType(rec.type),
                amount=rec.amount,
                category=rec.category or "Recurring",
                description=f"[Automated] {rec.name}",
                account_id=rec.account_id,
                to_account_id=rec.to_account_id,
                date=today,
                metadata={"recurring_id": rec.id, "frequency": rec.frequency},
            )
        )

        # Advance next_due_date and record last_executed_at
        current_due = dt.date.fromisoformat(str(rec.next_due_date)) if rec.next_due_date else today
        next_due = compute_next_due_date(current_due, rec.frequency, rec.day_of_month)

        update_payload = {
            "last_executed_at": datetime.now(timezone.utc).isoformat(),
            "next_due_date": next_due.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.client.table("recurring_transactions").update(update_payload).eq("id", rec.id).execute()
        logger.info("Executed recurring transaction '%s' (₹%s). Next due: %s", rec.name, rec.amount, next_due)
        return txn

    def process_due_recurring_transactions(self, user_id: str = "default_user") -> List[TransactionModel]:
        """Scans for all active recurring transactions that are due (next_due_date <= today) and auto-executes them."""
        today = datetime.now(timezone.utc).date().isoformat()
        res = (
            self.client.table("recurring_transactions")
            .select("*")
            .eq("user_id", user_id)
            .eq("active", True)
            .eq("auto_execute", True)
            .lte("next_due_date", today)
            .execute()
        )
        executed: List[TransactionModel] = []
        for row in res.data or []:
            rec = RecurringTransactionModel.model_validate(row)
            try:
                txn = self.execute_recurring_transaction(rec.id)
                executed.append(txn)
            except Exception as e:
                logger.error("Failed executing recurring rule '%s': %s", rec.name, e)
        return executed

    # ── Financial Overview & Analytics ───────────────────────────────────────

    def get_spending_by_category(self, user_id: str = "default_user") -> Dict[str, float]:
        """Aggregates total expenses by category."""
        res = (
            self.client.table("transactions")
            .select("category, amount")
            .eq("user_id", user_id)
            .eq("type", "expense")
            .execute()
        )
        totals: Dict[str, float] = {}
        for row in res.data or []:
            r = dict(row)
            cat = r.get("category") or "Uncategorized"
            amt = float(r.get("amount") or 0.0)
            totals[cat] = totals.get(cat, 0.0) + amt
        return totals

    def get_financial_overview(self, user_id: str = "default_user") -> Dict[str, Any]:
        """Comprehensive snapshot of liquid wealth, bank vs cash reserves, debts, and cashflow."""
        accounts = self.get_accounts(user_id=user_id)
        total_bank = sum(a.balance for a in accounts if a.type == "bank")
        total_cash = sum(a.balance for a in accounts if a.type == "cash")
        total_net_worth = sum(a.balance for a in accounts)

        debt_summary = self.get_person_debt_summaries(user_id=user_id)
        spending_by_cat = self.get_spending_by_category(user_id=user_id)

        # 30-day cashflow metrics
        thirty_days_ago = (datetime.now(timezone.utc).date() - dt.timedelta(days=30)).isoformat()
        res = (
            self.client.table("transactions")
            .select("type, amount")
            .eq("user_id", user_id)
            .gte("date", thirty_days_ago)
            .execute()
        )
        month_expense = 0.0
        month_income = 0.0
        for row in res.data or []:
            t_type = row.get("type")
            amt = float(row.get("amount") or 0.0)
            if t_type == "expense":
                month_expense += amt
            elif t_type == "income":
                month_income += amt

        default_acc = next((a for a in accounts if a.is_default), accounts[0] if accounts else None)

        return {
            "total_net_worth": total_net_worth,
            "bank_balance": total_bank,
            "cash_balance": total_cash,
            "default_account_id": default_acc.id if default_acc else None,
            "default_account_name": default_acc.name if default_acc else "Union Bank",
            "accounts": [a.model_dump() for a in accounts],
            "debts": debt_summary,
            "monthly_burn": month_expense,
            "monthly_income": month_income,
            "monthly_net_savings": month_income - month_expense,
            "spending_by_category": spending_by_cat,
        }
