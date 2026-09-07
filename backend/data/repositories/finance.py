"""Finance Repository for Supabase.

Handles accounts, double-entry transactions with balance adjustments,
and peer-to-peer debts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from supabase import Client

from backend.data.client import get_supabase_client
from backend.data.models import (
    AccountCreate,
    AccountModel,
    DebtCreate,
    DebtModel,
    TransactionCreate,
    TransactionModel,
    TransactionType,
)

logger = logging.getLogger("vesper.data.finance")


class FinanceRepository:
    """Repository handling all financial accounts, transactions, and debts."""

    def __init__(self, client: Optional[Client] = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        if self._client is not None:
            return self._client
        return get_supabase_client()

    # ── Accounts ──────────────────────────────────────────────────────────

    def create_account(self, account: AccountCreate) -> AccountModel:
        """Creates a new financial account (bank, cash, wallet)."""
        data = {
            "user_id": account.user_id,
            "name": account.name,
            "type": account.type.value,
            "balance": (account.balance),
            "currency": account.currency,
            "metadata": account.metadata,
        }
        res = self.client.table("accounts").insert(data).execute()
        if not res.data:
            raise RuntimeError("Failed to create account in Supabase.")
        return AccountModel.model_validate(res.data[0])

    def get_accounts(self, user_id: str = "default_user") -> list[AccountModel]:
        """Returns all accounts belonging to the user."""
        res = self.client.table("accounts").select("*").eq("user_id", user_id).order("name").execute()
        return [AccountModel.model_validate(row) for row in res.data]

    def get_account_by_name(self, name: str, user_id: str = "default_user") -> Optional[AccountModel]:
        """Looks up an account by name (e.g. 'Union Bank')."""
        res = self.client.table("accounts").select("*").eq("user_id", user_id).ilike("name", name).execute()
        if res.data:
            return AccountModel.model_validate(res.data[0])
        return None

    def get_account(self, account_id: str) -> Optional[AccountModel]:
        """Looks up an account by its unique ID."""
        res = self.client.table("accounts").select("*").eq("id", account_id).execute()
        if res.data:
            return AccountModel.model_validate(res.data[0])
        return None

    # ── Transactions ──────────────────────────────────────────────────────

    def add_transaction(self, txn: TransactionCreate) -> TransactionModel:
        """Logs a transaction and atomically adjusts affected account balances."""
        txn_data = {
            "user_id": txn.user_id,
            "type": txn.type.value,
            "amount": (txn.amount),
            "category": txn.category,
            "description": txn.description,
            "account_id": txn.account_id,
            "to_account_id": txn.to_account_id,
            "date": txn.date.isoformat() if txn.date else datetime.now(timezone.utc).date().isoformat(),
            "metadata": txn.metadata,
        }
        res = self.client.table("transactions").insert(txn_data).execute()
        if not res.data:
            raise RuntimeError("Failed to insert transaction into Supabase.")

        created_txn = TransactionModel.model_validate(res.data[0])

        # Adjust Account Balances
        if txn.account_id:
            acc_res = self.client.table("accounts").select("*").eq("id", txn.account_id).execute()
            if acc_res.data:
                row = dict(acc_res.data[0])  # type: ignore[arg-type]
                curr_balance = float(row["balance"])
                if txn.type == TransactionType.EXPENSE:
                    new_balance = curr_balance - (txn.amount)
                elif txn.type == TransactionType.INCOME:
                    new_balance = curr_balance + (txn.amount)
                elif txn.type == TransactionType.TRANSFER:
                    new_balance = curr_balance - (txn.amount)
                else:
                    new_balance = curr_balance

                self.client.table("accounts").update({"balance": new_balance}).eq("id", txn.account_id).execute()

        # If Transfer, credit the destination account
        if txn.type == TransactionType.TRANSFER and txn.to_account_id:
            to_acc_res = self.client.table("accounts").select("*").eq("id", txn.to_account_id).execute()
            if to_acc_res.data:
                row = dict(to_acc_res.data[0])  # type: ignore[arg-type]
                curr_to_balance = float(row["balance"])
                new_to_balance = curr_to_balance + (txn.amount)
                self.client.table("accounts").update({"balance": new_to_balance}).eq("id", txn.to_account_id).execute()

        return created_txn

    def get_recent_transactions(
        self,
        user_id: str = "default_user",
        limit: int = 20,
    ) -> list[TransactionModel]:
        """Returns the most recent transactions."""
        res = (
            self.client.table("transactions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [TransactionModel.model_validate(row) for row in res.data]

    def delete_transaction(self, transaction_id: str) -> bool:
        """Deletes a transaction and reverses its effect on the associated account balance."""
        res = self.client.table("transactions").select("*").eq("id", transaction_id).execute()
        if not res.data:
            return False

        txn = TransactionModel.model_validate(res.data[0])
        if txn.account_id:
            acc_res = self.client.table("accounts").select("*").eq("id", txn.account_id).execute()
            if acc_res.data:
                row = dict(acc_res.data[0])  # type: ignore[arg-type]
                curr_balance = float(row["balance"])
                if txn.type == TransactionType.EXPENSE:
                    new_balance = curr_balance + txn.amount
                elif txn.type == TransactionType.INCOME:
                    new_balance = curr_balance - txn.amount
                else:
                    new_balance = curr_balance
                self.client.table("accounts").update({"balance": new_balance}).eq("id", txn.account_id).execute()

        self.client.table("transactions").delete().eq("id", transaction_id).execute()
        return True

    def get_spending_by_category(self, user_id: str = "default_user") -> dict[str, float]:
        """Aggregates total expenses by category."""
        res = (
            self.client.table("transactions")
            .select("category, amount")
            .eq("user_id", user_id)
            .eq("type", "expense")
            .execute()
        )
        totals: dict[str, float] = {}
        for row in res.data:
            r = dict(row)  # type: ignore[arg-type]
            cat = r.get("category") or "Uncategorized"
            amt = float(r.get("amount") or 0.0)
            totals[cat] = totals.get(cat, 0.0) + amt
        return totals

    # ── Debts ─────────────────────────────────────────────────────────────

    def record_debt(self, debt: DebtCreate) -> DebtModel:
        """Records a new peer debt (owe or owed)."""
        data = {
            "user_id": debt.user_id,
            "person": debt.person,
            "amount": (debt.amount),
            "direction": debt.direction.value,
            "description": debt.description,
            "metadata": debt.metadata,
        }
        res = self.client.table("debts").insert(data).execute()
        if not res.data:
            raise RuntimeError("Failed to record debt in Supabase.")
        return DebtModel.model_validate(res.data[0])

    def get_active_debts(self, user_id: str = "default_user") -> list[DebtModel]:
        """Returns all unsettled debts."""
        res = (
            self.client.table("debts")
            .select("*")
            .eq("user_id", user_id)
            .eq("settled", False)
            .order("created_at", desc=True)
            .execute()
        )
        return [DebtModel.model_validate(row) for row in res.data]

    def settle_debt(self, debt_id: str) -> bool:
        """Marks a debt as settled."""
        from datetime import timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        res = (
            self.client.table("debts")
            .update({"settled": True, "settled_at": now_iso})
            .eq("id", debt_id)
            .execute()
        )
        return len(res.data) > 0

    def update_debt_amount(self, debt_id: str, new_amount: float) -> bool:
        """Updates the remaining amount on an existing debt."""
        res = (
            self.client.table("debts")
            .update({"amount": new_amount})
            .eq("id", debt_id)
            .execute()
        )
        return len(res.data) > 0
