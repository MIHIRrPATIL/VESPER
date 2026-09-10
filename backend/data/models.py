"""VESPER Domain Data Models (Pydantic v2).

All models include `extra="allow"` for unlimited room to grow as new features are added.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ── Domain Enums ─────────────────────────────────────────────────────────

class PriorityLevel(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class AccountType(str, Enum):
    BANK = "bank"
    CASH = "cash"
    CREDIT = "credit"
    WALLET = "wallet"


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class DebtDirection(str, Enum):
    OWE = "owe"    # I owe someone else
    OWED = "owed"  # Someone owes me


class FrequencyType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


# ── Base Extensible Model ────────────────────────────────────────────────

class BaseDataModel(BaseModel):
    model_config = ConfigDict(extra="allow", from_attributes=True)


# ── Task Models ──────────────────────────────────────────────────────────

class TaskCreate(BaseDataModel):
    title: str
    user_id: str = "default_user"
    deadline: Optional[dt.datetime] = None
    priority: PriorityLevel = PriorityLevel.NORMAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskModel(BaseDataModel):
    id: str
    user_id: str
    title: str
    deadline: Optional[dt.datetime] = None
    done: bool = False
    priority: str = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None


# ── Finance Models ───────────────────────────────────────────────────────

class AccountCreate(BaseDataModel):
    name: str
    user_id: str = "default_user"
    type: AccountType = AccountType.BANK
    balance: float = 0.0
    currency: str = "INR"
    is_default: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountUpdate(BaseDataModel):
    name: Optional[str] = None
    type: Optional[AccountType] = None
    balance: Optional[float] = None
    currency: Optional[str] = None
    is_default: Optional[bool] = None
    metadata: Optional[dict[str, Any]] = None


class AccountModel(BaseDataModel):
    id: str
    user_id: str
    name: str
    type: str = "bank"
    balance: float = 0.0
    currency: str = "INR"
    is_default: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[dt.datetime] = None


class TransactionCreate(BaseDataModel):
    user_id: str = "default_user"
    type: TransactionType = TransactionType.EXPENSE
    amount: float
    category: Optional[str] = None
    description: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    date: Optional[dt.date] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransactionUpdate(BaseDataModel):
    type: Optional[TransactionType] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    date: Optional[dt.date] = None
    metadata: Optional[dict[str, Any]] = None


class TransactionModel(BaseDataModel):
    id: str
    user_id: str
    type: str
    amount: float
    category: Optional[str] = None
    description: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    date: Optional[dt.date] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[dt.datetime] = None


class DebtCreate(BaseDataModel):
    person: str
    amount: float
    direction: DebtDirection = DebtDirection.OWED
    user_id: str = "default_user"
    description: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DebtUpdate(BaseDataModel):
    person: Optional[str] = None
    amount: Optional[float] = None
    direction: Optional[DebtDirection] = None
    description: Optional[str] = None
    settled: Optional[bool] = None
    metadata: Optional[dict[str, Any]] = None


class DebtModel(BaseDataModel):
    id: str
    user_id: str
    person: str
    amount: float
    direction: str
    description: Optional[str] = None
    settled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[dt.datetime] = None
    settled_at: Optional[dt.datetime] = None


# ── Recurring & Automated Transactions ───────────────────────────────────

class RecurringTransactionCreate(BaseDataModel):
    name: str
    amount: float
    type: TransactionType = TransactionType.EXPENSE
    user_id: str = "default_user"
    category: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    frequency: FrequencyType = FrequencyType.MONTHLY
    day_of_month: Optional[int] = None
    day_of_week: Optional[int] = None
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None
    next_due_date: Optional[dt.date] = None
    active: bool = True
    auto_execute: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecurringTransactionUpdate(BaseDataModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    type: Optional[TransactionType] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    frequency: Optional[FrequencyType] = None
    day_of_month: Optional[int] = None
    day_of_week: Optional[int] = None
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None
    next_due_date: Optional[dt.date] = None
    active: Optional[bool] = None
    auto_execute: Optional[bool] = None
    metadata: Optional[dict[str, Any]] = None


class RecurringTransactionModel(BaseDataModel):
    id: str
    user_id: str
    name: str
    amount: float
    type: str
    category: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    frequency: str = "monthly"
    day_of_month: Optional[int] = None
    day_of_week: Optional[int] = None
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None
    next_due_date: Optional[dt.date] = None
    last_executed_at: Optional[dt.datetime] = None
    active: bool = True
    auto_execute: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None


# ── Shodh-Memory Models ──────────────────────────────────────────────────

class MemoryCreate(BaseDataModel):
    statement: str
    category: str = "general"
    user_id: str = "default_user"
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShodhMemoryModel(BaseDataModel):
    id: str
    user_id: str
    statement: str
    category: str = "general"
    confidence: float = 1.0
    access_count: int = 0
    last_accessed_at: Optional[dt.datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
