"""VESPER Finance Specialist Agent.

Manages personal finances in Indian Rupees (₹), double-entry ledger accounts,
peer debt tracking (lending, borrowing, expense splitting, running tabs, partial repayments),
contacts disambiguation, and dynamic financial goals in Supabase PostgreSQL.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.data.client import get_supabase_client
from backend.data.models import (
    AccountCreate,
    AccountModel,
    AccountType,
    DebtCreate,
    DebtDirection,
    TransactionCreate,
    TransactionType,
)
from backend.data.repositories.finance import FinanceRepository

logger = logging.getLogger("vesper.agent.specialists.finance")


class FinanceSpecialist(BaseSpecialist):
    """Specialist agent for personal finances, peer debts, expense splitting, and goals in ₹ (INR)."""

    def __init__(self, repo: Optional[FinanceRepository] = None) -> None:
        self.repo = repo or FinanceRepository(get_supabase_client())
        # Working memory for conversational pronouns ("with them", "same person", "the same guys")
        self._last_split_people: List[str] = []
        self._last_person: Optional[str] = None

    @property
    def name(self) -> str:
        return "finance"

    @property
    def description(self) -> str:
        return "Manages accounts in ₹, logs expenses/income, tracks peer debts (lending/borrowing/splitting/running tabs), and manages financial goals."

    def get_capabilities(self) -> str:
        return (
            "Check account balances in ₹, log expenses and income, split bills with friends, "
            "track running debt balances per person, record partial repayments, and manage dynamic financial goals."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_balance",
                "description": "Retrieves total net worth and account balance breakdown in ₹ (INR).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_name": {"type": "string", "description": "Optional specific account name to query."},
                    },
                },
            },
            {
                "name": "log_transaction",
                "description": "Logs an income or expense transaction in ₹ and updates account balance.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "description": "Amount in ₹ (INR)."},
                        "type": {"type": "string", "enum": ["expense", "income"], "description": "Transaction type."},
                        "category": {"type": "string", "description": "Category (e.g. food, tech, rent, travel, salary)."},
                        "description": {"type": "string", "description": "Description of the transaction."},
                        "account_name": {"type": "string", "description": "Account to charge (default: Primary)."},
                    },
                    "required": ["amount", "type"],
                },
            },
            {
                "name": "split_expense",
                "description": "Splits a bill or expense among friends and records individual receivable debts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "total_amount": {"type": "number", "description": "Total bill amount in ₹."},
                        "people": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of friends sharing the bill (or 'them' / 'same people').",
                        },
                        "description": {"type": "string", "description": "What the expense was for (e.g. Dinner, Uber)."},
                    },
                    "required": ["total_amount"],
                },
            },
            {
                "name": "manage_debt",
                "description": "Records money lent, borrowed, partial repayments, settles debts, or queries running tabs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["lend", "borrow", "settle", "list"],
                            "description": "Debt action: 'lend' (they owe you), 'borrow' (you owe them), 'settle', 'list'.",
                        },
                        "person": {"type": "string", "description": "Name of the person (or 'him' / 'them' / 'same person')."},
                        "amount": {"type": "number", "description": "Amount in ₹ (or repayment amount when settling)."},
                        "description": {"type": "string", "description": "Optional note or reason."},
                    },
                    "required": ["action"],
                },
            },
            {
                "name": "manage_financial_goal",
                "description": "Creates, updates, or checks dynamic savings or spending budget goals stored in the database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["set", "update", "list", "check_budget"],
                            "description": "Goal action to perform.",
                        },
                        "name": {"type": "string", "description": "Goal name (e.g. 'Monthly Living Budget', 'GPU Savings')."},
                        "target_amount": {"type": "number", "description": "Target amount in ₹."},
                        "current_amount": {"type": "number", "description": "Current saved amount in ₹ (for updates)."},
                        "deadline": {"type": "string", "description": "Optional deadline (e.g. '2026-12-31')."},
                    },
                    "required": ["action"],
                },
            },
        ]

    # ── Contacts & Name Resolution in Supabase ───────────────────────────────

    def _resolve_person_name(self, raw_name: str) -> str:
        """Resolves raw or informal name against contacts in Supabase."""
        cleaned = raw_name.strip()
        cleaned_lower = cleaned.lower()

        # Handle working memory pronouns
        if cleaned_lower in ["him", "her", "them", "the same person", "same person", "that guy"]:
            if self._last_person:
                return self._last_person

        client = get_supabase_client()
        try:
            res = client.table("shodh_memories").select("*").eq("category", "contact").execute()
            for row in res.data or []:
                if isinstance(row, dict):
                    meta = row.get("metadata")
                    if isinstance(meta, dict):
                        name = meta.get("name")
                        name_str = str(name) if name is not None else ""
                        raw_aliases = meta.get("aliases")
                        aliases = [str(a).lower() for a in raw_aliases] if isinstance(raw_aliases, list) else []
                        if cleaned_lower == name_str.lower() or cleaned_lower in aliases:
                            return name_str
        except Exception:
            pass

        # Fallback to Title-Cased string and cache in memory
        canonical = cleaned.capitalize()
        return canonical

    def _auto_register_contact(self, canonical_name: str) -> None:
        """Silently ensures a contact entry exists in Supabase so future queries recognize them."""
        client = get_supabase_client()
        try:
            res = (
                client.table("shodh_memories")
                .select("id")
                .eq("category", "contact")
                .ilike("statement", f"%Contact: {canonical_name}%")
                .execute()
            )
            if not res.data:
                client.table("shodh_memories").insert({
                    "statement": f"Contact: {canonical_name}",
                    "category": "contact",
                    "confidence": 1.0,
                    "metadata": {
                        "name": canonical_name,
                        "aliases": [canonical_name.lower()],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                }).execute()
        except Exception:
            pass

    # ── Accounts & Balances ──────────────────────────────────────────────────

    def _get_or_create_primary_account(self, user_id: str = "default_user") -> AccountModel:
        """Returns the primary bank account, creating one if empty."""
        accounts = self.repo.get_accounts(user_id=user_id)
        if accounts:
            return accounts[0]

        return self.repo.create_account(
            AccountCreate(
                name="Primary Account",
                user_id=user_id,
                type=AccountType.BANK,
                balance=15000.0,
                currency="INR",
            )
        )

    async def get_balance_summary(self, account_name: Optional[str] = None) -> SpecialistResult:
        """Calculates balance summary and net worth in ₹."""
        accounts = self.repo.get_accounts()
        if not accounts:
            primary = self._get_or_create_primary_account()
            accounts = [primary]

        total_net_worth = sum(a.balance for a in accounts)

        if account_name:
            acc = next((a for a in accounts if account_name.lower() in a.name.lower()), None)
            if not acc:
                return SpecialistResult(
                    success=False,
                    action="get_balance",
                    error=f"Account '{account_name}' not found.",
                )
            speech = f"Your {acc.name} has an active balance of ₹{acc.balance:,.2f}, sir."
            return SpecialistResult(
                success=True,
                action="get_balance",
                data={"account": acc.name, "balance": acc.balance, "currency": "INR"},
                speech_summary=speech,
                card_payload={"type": "finance_balance_card", "accounts": [acc.model_dump()]},
            )

        acc_breakdown = ", ".join([f"{a.name}: ₹{a.balance:,.0f}" for a in accounts])
        speech = f"Your total balance across accounts is ₹{total_net_worth:,.2f} ({acc_breakdown}), sir."

        return SpecialistResult(
            success=True,
            action="get_balance",
            data={
                "total_net_worth": total_net_worth,
                "currency": "INR",
                "accounts": [a.model_dump() for a in accounts],
            },
            speech_summary=speech,
            card_payload={
                "type": "finance_balance_card",
                "total_balance": total_net_worth,
                "currency": "INR",
                "accounts": [a.model_dump() for a in accounts],
            },
        )

    # ── Transactions ─────────────────────────────────────────────────────────

    async def log_transaction(
        self,
        amount: float,
        txn_type: str = "expense",
        category: Optional[str] = None,
        description: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> SpecialistResult:
        """Logs an income/expense in ₹ and updates account balance."""
        primary_acc = self._get_or_create_primary_account()
        t_type = TransactionType.INCOME if "inc" in txn_type.lower() else TransactionType.EXPENSE
        cat = category or ("Salary" if t_type == TransactionType.INCOME else "General Expense")
        desc = description or f"{t_type.value.capitalize()} of ₹{amount:,.2f}"

        txn = self.repo.add_transaction(
            TransactionCreate(
                amount=abs(amount),
                type=t_type,
                category=cat,
                description=desc,
                account_id=primary_acc.id,
            )
        )

        updated_acc = self.repo.get_account(primary_acc.id)
        new_balance = updated_acc.balance if updated_acc else primary_acc.balance

        speech = (
            f"Recorded {t_type.value} of ₹{abs(amount):,.2f} under {cat}. "
            f"Your current balance is ₹{new_balance:,.2f}, sir."
        )

        return SpecialistResult(
            success=True,
            action="log_transaction",
            data={
                "transaction_id": txn.id,
                "amount": txn.amount,
                "type": txn.type,
                "category": txn.category,
                "new_balance": new_balance,
            },
            speech_summary=speech,
            card_payload={
                "type": "finance_transaction_card",
                "amount": txn.amount,
                "type": txn.type,
                "category": txn.category,
                "description": txn.description,
                "balance": new_balance,
            },
        )

    # ── Peer Debts, Running Tabs & Splitting ─────────────────────────────────

    def _get_person_running_tab(self, person: str) -> Dict[str, Any]:
        """Calculates running debt total for a specific person."""
        active = self.repo.get_active_debts()
        matched = [d for d in active if d.person.lower() == person.lower()]
        owed_to_me = [d for d in matched if d.direction == "owed"]
        i_owe = [d for d in matched if d.direction == "owe"]

        sum_owed = sum(d.amount for d in owed_to_me)
        sum_owe = sum(d.amount for d in i_owe)
        net_balance = sum_owed - sum_owe

        return {
            "person": person,
            "debts": matched,
            "total_owed_to_me": sum_owed,
            "total_i_owe": sum_owe,
            "net_balance": net_balance,
            "count": len(matched),
        }

    async def split_expense(
        self, total_amount: float, people: Optional[List[str]] = None, description: Optional[str] = None
    ) -> SpecialistResult:
        """Splits an expense, resolves names, updates running tabs, and records debts."""
        # Check conversational memory pronouns
        resolved_people: List[str] = []
        if not people or any(p.lower() in ["them", "same people", "the same", "the same guys", "the same person"] for p in people):
            if self._last_split_people:
                resolved_people = list(self._last_split_people)
            else:
                return SpecialistResult(
                    success=False,
                    action="split_expense",
                    error="Please specify who to split the bill with, sir.",
                    speech_summary="With whom would you like me to split this expense, sir?",
                )
        else:
            for p in people:
                canon = self._resolve_person_name(p)
                resolved_people.append(canon)
                self._auto_register_contact(canon)

        total_members = len(resolved_people) + 1  # user + friends
        share_per_person = round(total_amount / total_members, 2)
        desc = description or "Bill Split"

        debts_created = []
        tab_summaries = []

        for person in resolved_people:
            debt = self.repo.record_debt(
                DebtCreate(
                    person=person,
                    amount=share_per_person,
                    direction=DebtDirection.OWED,
                    description=f"Share of {desc} (Total ₹{total_amount:,.0f})",
                )
            )
            debts_created.append({"person": person, "amount": share_per_person, "debt_id": debt.id})

            # Calculate updated running tab for this person
            tab = self._get_person_running_tab(person)
            if tab["count"] > 1:
                tab_summaries.append(f"{person} owes ₹{share_per_person:,.0f} (running tab: ₹{tab['total_owed_to_me']:,.0f})")
            else:
                tab_summaries.append(f"{person} owes ₹{share_per_person:,.0f}")

        # Update working session memory
        self._last_split_people = resolved_people
        self._last_person = resolved_people[0]

        speech = (
            f"Split ₹{total_amount:,.2f} among {total_members} people at ₹{share_per_person:,.2f} each. "
            f"Recorded: {', '.join(tab_summaries)}, sir."
        )

        return SpecialistResult(
            success=True,
            action="split_expense",
            data={
                "total_amount": total_amount,
                "share_per_person": share_per_person,
                "debts": debts_created,
                "people": resolved_people,
            },
            speech_summary=speech,
            card_payload={
                "type": "debt_split_card",
                "total": total_amount,
                "share": share_per_person,
                "debts": debts_created,
            },
        )

    async def manage_debt(
        self,
        action: str,
        person: Optional[str] = None,
        amount: Optional[float] = None,
        description: Optional[str] = None,
    ) -> SpecialistResult:
        """Handles lending, borrowing, partial repayments, debt settlement, and running tabs."""
        act = action.lower().strip()

        # Handle global scope words vs specific names
        if person and person.lower().strip() in ["all", "everyone", "any", "anyone", "anybody", "everybody", "all people", "none", "*"]:
            canon_person = None
        elif person:
            canon_person = self._resolve_person_name(person)
        else:
            canon_person = None

        # 1. Settle Debt / Partial Repayments
        if act in ["settle", "clear", "paid", "repay"]:
            if not canon_person:
                return SpecialistResult(success=False, action="manage_debt", error="Person name is required to settle debt.")

            active = self.repo.get_active_debts()
            matched = [d for d in active if d.person.lower() == canon_person.lower() and d.direction == "owed"]
            if not matched:
                return SpecialistResult(
                    success=False,
                    action="manage_debt",
                    error=f"No active unsettled debts found for '{canon_person}'.",
                    speech_summary=f"I found no unsettled debts recorded for {canon_person}, sir.",
                )

            # Sort oldest to newest
            matched_sorted = sorted(matched, key=lambda x: x.created_at or datetime.min)
            total_owed_before = sum(d.amount for d in matched_sorted)

            # If no amount specified, settle all debts for this person
            if not amount or amount >= total_owed_before:
                for d in matched_sorted:
                    self.repo.settle_debt(d.id)
                speech = f"Marked {canon_person}'s full balance of ₹{total_owed_before:,.2f} as settled, sir."
                return SpecialistResult(
                    success=True,
                    action="manage_debt",
                    data={"person": canon_person, "settled_amount": total_owed_before, "remaining_balance": 0.0},
                    speech_summary=speech,
                    card_payload={"type": "debt_settled_card", "person": canon_person, "amount": total_owed_before, "remaining": 0.0},
                )

            # Partial repayment: apply amount across debts from oldest to newest
            remaining_payment = amount
            for d in matched_sorted:
                if remaining_payment >= d.amount:
                    self.repo.settle_debt(d.id)
                    remaining_payment -= d.amount
                elif remaining_payment > 0:
                    new_debt_amt = round(d.amount - remaining_payment, 2)
                    self.repo.update_debt_amount(d.id, new_debt_amt)
                    remaining_payment = 0.0
                    break

            new_tab = self._get_person_running_tab(canon_person)
            new_bal = new_tab["total_owed_to_me"]
            speech = (
                f"Recorded partial repayment of ₹{amount:,.2f} from {canon_person}. "
                f"Their remaining balance owed to you is now ₹{new_bal:,.2f}, sir."
            )

            return SpecialistResult(
                success=True,
                action="manage_debt",
                data={"person": canon_person, "paid_amount": amount, "remaining_balance": new_bal},
                speech_summary=speech,
                card_payload={"type": "debt_settled_card", "person": canon_person, "paid": amount, "remaining": new_bal},
            )

        # 2. List Debts & Running Tab Aggregation
        elif act in ["list", "query", "check"]:
            active = self.repo.get_active_debts()
            if not active:
                return SpecialistResult(
                    success=True,
                    action="manage_debt",
                    data={"debts": [], "total_owed": 0.0, "total_owe": 0.0},
                    speech_summary="You currently have no outstanding debts or receivables, sir.",
                    card_payload={"type": "debt_list_card", "debts": []},
                )

            # If querying a specific person's running tab
            if canon_person:
                tab = self._get_person_running_tab(canon_person)
                if tab["count"] == 0:
                    return SpecialistResult(
                        success=True,
                        action="manage_debt",
                        speech_summary=f"{canon_person} currently has a clean tab with no active debts, sir.",
                        card_payload={"type": "person_tab_card", "person": canon_person, "balance": 0.0},
                    )
                speech = f"{canon_person} currently owes you ₹{tab['total_owed_to_me']:,.2f} across {tab['count']} items, sir."
                return SpecialistResult(
                    success=True,
                    action="manage_debt",
                    data=tab,
                    speech_summary=speech,
                    card_payload={"type": "person_tab_card", "person": canon_person, "balance": tab["total_owed_to_me"]},
                )

            # Aggregate by person for consolidated report
            owed_by_person: Dict[str, Dict[str, Any]] = {}
            owe_to_person: Dict[str, Dict[str, Any]] = {}

            for d in active:
                target = owed_by_person if d.direction == "owed" else owe_to_person
                if d.person not in target:
                    target[d.person] = {"person": d.person, "total": 0.0, "count": 0}
                target[d.person]["total"] += d.amount
                target[d.person]["count"] += 1

            parts = []
            if owed_by_person:
                lines = [f"{p} (₹{info['total']:,.0f})" for p, info in owed_by_person.items()]
                total_owed = sum(info["total"] for info in owed_by_person.values())
                parts.append(f"Friends owe you ₹{total_owed:,.2f} ({', '.join(lines)})")
            if owe_to_person:
                lines = [f"{p} (₹{info['total']:,.0f})" for p, info in owe_to_person.items()]
                total_owe = sum(info["total"] for info in owe_to_person.values())
                parts.append(f"you owe ₹{total_owe:,.2f} ({', '.join(lines)})")

            speech = " and ".join(parts) + ", sir."
            return SpecialistResult(
                success=True,
                action="manage_debt",
                data={"owed_by_person": owed_by_person, "owe_to_person": owe_to_person},
                speech_summary=speech,
                card_payload={"type": "debt_list_card", "owed": owed_by_person, "owe": owe_to_person},
            )

        # 3. Record Lend / Borrow
        if not canon_person or not amount:
            return SpecialistResult(success=False, action="manage_debt", error="Person and amount are required.")

        direction = DebtDirection.OWE if act in ["borrow", "owe"] else DebtDirection.OWED
        desc = description or ("Borrowed funds" if direction == DebtDirection.OWE else "Lent money")

        debt_obj = self.repo.record_debt(
            DebtCreate(
                person=canon_person,
                amount=abs(amount),
                direction=direction,
                description=desc,
            )
        )

        self._auto_register_contact(canon_person)
        self._last_person = canon_person

        # Check running tab
        tab = self._get_person_running_tab(canon_person)
        if direction == DebtDirection.OWED:
            if tab["count"] > 1:
                speech = f"Recorded ₹{debt_obj.amount:,.2f} lent to {canon_person}. Their cumulative tab owed to you is now ₹{tab['total_owed_to_me']:,.2f}, sir."
            else:
                speech = f"Recorded that {canon_person} owes you ₹{debt_obj.amount:,.2f}, sir."
        else:
            speech = f"Recorded that you owe {canon_person} ₹{debt_obj.amount:,.2f}, sir."

        return SpecialistResult(
            success=True,
            action="manage_debt",
            data={
                "debt_id": debt_obj.id,
                "person": canon_person,
                "amount": debt_obj.amount,
                "running_tab": tab["total_owed_to_me"],
            },
            speech_summary=speech,
            card_payload={
                "type": "debt_created_card",
                "person": canon_person,
                "amount": debt_obj.amount,
                "running_tab": tab["total_owed_to_me"],
            },
        )

    # ── Dynamic Financial Goals in Database ──────────────────────────────────

    async def manage_goals(
        self,
        action: str,
        name: Optional[str] = None,
        target_amount: Optional[float] = None,
        current_amount: Optional[float] = None,
        deadline: Optional[str] = None,
    ) -> SpecialistResult:
        """Stores, updates, and tracks dynamic financial goals in Supabase PostgreSQL."""
        client = get_supabase_client()
        act = action.lower().strip()

        res = client.table("shodh_memories").select("*").eq("category", "financial_goal").execute()
        existing_goals = res.data or []

        if act in ["set", "create", "add"]:
            if not name or not target_amount:
                return SpecialistResult(success=False, action="manage_financial_goal", error="Goal name and target amount are required.")

            goal_meta = {
                "name": name.strip(),
                "target_amount": target_amount,
                "current_amount": current_amount if current_amount is not None else 0.0,
                "deadline": deadline,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            client.table("shodh_memories").insert({
                "statement": f"Financial Goal: {name.strip()} with target of ₹{target_amount:,.2f}",
                "category": "financial_goal",
                "confidence": 1.0,
                "metadata": goal_meta,
            }).execute()

            speech = f"Created dynamic financial goal '{name.strip()}' targeting ₹{target_amount:,.2f}, recorded in the database, sir."
            return SpecialistResult(
                success=True,
                action="manage_financial_goal",
                data=goal_meta,
                speech_summary=speech,
                card_payload={"type": "financial_goal_card", "goal": goal_meta},
            )

        elif act in ["list", "check", "check_budget"]:
            if not existing_goals:
                return SpecialistResult(
                    success=True,
                    action="manage_financial_goal",
                    data={"goals": []},
                    speech_summary="You have no active financial goals configured in the database, sir.",
                    card_payload={"type": "financial_goal_list_card", "goals": []},
                )

            goals_list = [g.get("metadata", {}) for g in existing_goals if isinstance(g, dict)]
            goal_lines = []
            for g in goals_list:
                if isinstance(g, dict):
                    g_name = str(g.get("name") or "Goal")
                    raw_target = g.get("target_amount")
                    raw_curr = g.get("current_amount")
                    target = float(raw_target) if isinstance(raw_target, (int, float, str)) and raw_target else 0.0
                    curr = float(raw_curr) if isinstance(raw_curr, (int, float, str)) and raw_curr else 0.0
                    pct = (curr / target * 100) if target > 0 else 0
                    goal_lines.append(f"{g_name}: ₹{curr:,.0f} of ₹{target:,.0f} ({pct:.0f}%)")

            speech = "Your current financial goals in the database are: " + "; ".join(goal_lines) + ", sir."
            return SpecialistResult(
                success=True,
                action="manage_financial_goal",
                data={"goals": goals_list},
                speech_summary=speech,
                card_payload={"type": "financial_goal_list_card", "goals": goals_list},
            )

        return SpecialistResult(success=False, action="manage_financial_goal", error=f"Unknown goal action '{action}'.")

    # ── Execution Router ─────────────────────────────────────────────────────

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        act = action.lower().strip()

        # 1. Balance Queries
        if act in ["get_balance", "balance", "net_worth", "account_balance"]:
            acc_name = params.get("account_name")
            return await self.get_balance_summary(acc_name)

        # 2. Transaction Logging
        elif act in ["log_transaction", "add_transaction", "record_expense", "record_income", "spend"]:
            amt = float(params.get("amount") or 0.0)
            t_type = str(params.get("type") or "expense")
            cat = params.get("category")
            desc = params.get("description")
            acc = params.get("account_name")
            return await self.log_transaction(amt, txn_type=t_type, category=cat, description=desc, account_name=acc)

        # 3. Expense Splitting
        elif act in ["split_expense", "split_bill", "split"]:
            tot = float(params.get("total_amount") or params.get("amount") or 0.0)
            ppl = params.get("people", [])
            if isinstance(ppl, str):
                ppl = [p.strip() for p in ppl.split(",") if p.strip()]
            desc = params.get("description")
            return await self.split_expense(tot, people=ppl, description=desc)

        # 4. Debts, Running Tabs & Partial Repayments
        elif act in ["manage_debt", "lend", "borrow", "settle_debt", "settle", "list_debts", "debts"]:
            d_act = params.get("action", act)
            if act in ["lend", "borrow", "settle", "debts"]:
                d_act = act
            person = params.get("person")
            amt = float(params.get("amount") or 0.0) if params.get("amount") else None
            desc = params.get("description")
            return await self.manage_debt(d_act, person=person, amount=amt, description=desc)

        # 5. Financial Goals
        elif act in ["manage_financial_goal", "set_goal", "goals", "budget", "financial_goals"]:
            g_act = params.get("action", "list" if act in ["goals", "budget"] else "set")
            name = params.get("name")
            target = float(params.get("target_amount") or params.get("amount") or 0.0)
            curr = float(params.get("current_amount") or 0.0)
            dead = params.get("deadline")
            return await self.manage_goals(g_act, name=name, target_amount=target, current_amount=curr, deadline=dead)

        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}' on finance specialist.")
