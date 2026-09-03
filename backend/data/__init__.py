"""VESPER Persistence & Data Layer (Supabase PostgreSQL + pgvector)."""

from backend.data.client import get_supabase_client, reset_client
from backend.data.models import (
    AccountCreate,
    AccountModel,
    DebtCreate,
    DebtModel,
    MemoryCreate,
    PriorityLevel,
    ShodhMemoryModel,
    TaskCreate,
    TaskModel,
    TransactionCreate,
    TransactionModel,
    TransactionType,
)
from backend.data.repositories import (
    FinanceRepository,
    ShodhMemoryRepository,
    TaskRepository,
)

__all__ = [
    "get_supabase_client",
    "reset_client",
    "TaskModel",
    "TaskCreate",
    "AccountModel",
    "AccountCreate",
    "TransactionModel",
    "TransactionCreate",
    "DebtModel",
    "DebtCreate",
    "ShodhMemoryModel",
    "MemoryCreate",
    "PriorityLevel",
    "TransactionType",
    "TaskRepository",
    "FinanceRepository",
    "ShodhMemoryRepository",
]
