"""Unit tests for VESPER Personal Finance REST API & Repository."""

import pytest
from fastapi.testclient import TestClient
from backend.gateway.app import app
from backend.data.repositories.finance import FinanceRepository


@pytest.fixture
def client():
    return TestClient(app)


def test_finance_overview_endpoint(client):
    """Verifies /api/finance/overview returns core accounts and structure."""
    response = client.get("/api/finance/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_net_worth" in data
    assert "bank_balance" in data
    assert "cash_balance" in data
    assert "accounts" in data
    assert "debts" in data
    assert len(data["accounts"]) >= 4

    account_names = [a["name"].lower() for a in data["accounts"]]
    assert any("union" in name for name in account_names)
    assert any("sbi" in name for name in account_names)
    assert any("saraswat" in name for name in account_names)
    assert any("cash" in name for name in account_names)


def test_accounts_listing_and_default(client):
    """Verifies default account is set and editable."""
    response = client.get("/api/finance/accounts")
    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) >= 4

    default_acc = next((a for a in accounts if a["is_default"]), None)
    assert default_acc is not None
    assert "union" in default_acc["name"].lower() or default_acc["is_default"] is True


def test_create_and_delete_transaction(client):
    """Verifies creating an expense and deleting it cleanly."""
    # 1. Get accounts to get an account_id
    accs_res = client.get("/api/finance/accounts")
    accounts = accs_res.json()
    acc = accounts[0]
    initial_balance = acc["balance"]

    # 2. Add an expense
    txn_res = client.post(
        "/api/finance/transactions",
        json={
            "amount": 25.0,
            "type": "expense",
            "category": "Test Category",
            "description": "Pytest transaction",
            "account_id": acc["id"],
        },
    )
    assert txn_res.status_code == 201
    txn = txn_res.json()
    assert txn["amount"] == 25.0

    # 3. Check updated balance
    acc_after = client.get(f"/api/finance/accounts/{acc['id']}").json()
    assert acc_after["balance"] == initial_balance - 25.0

    # 4. Delete the transaction (restores balance)
    del_res = client.delete(f"/api/finance/transactions/{txn['id']}")
    assert del_res.status_code == 200

    # 5. Check restored balance
    acc_restored = client.get(f"/api/finance/accounts/{acc['id']}").json()
    assert acc_restored["balance"] == initial_balance


def test_recurring_transactions_crud(client):
    """Verifies creating, listing, and deleting a recurring schedule."""
    # Create recurring rule
    create_res = client.post(
        "/api/finance/recurring",
        json={
            "name": "Pytest Spotify",
            "amount": 119.0,
            "type": "expense",
            "frequency": "monthly",
            "category": "Entertainment",
        },
    )
    assert create_res.status_code == 201
    rule = create_res.json()
    assert rule["name"] == "Pytest Spotify"
    assert rule["amount"] == 119.0

    # List
    list_res = client.get("/api/finance/recurring")
    assert list_res.status_code == 200
    rules = list_res.json()
    assert any(r["id"] == rule["id"] for r in rules)

    # Delete
    del_res = client.delete(f"/api/finance/recurring/{rule['id']}")
    assert del_res.status_code == 200
