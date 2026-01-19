"""Tests for models module."""

from datetime import date

from copilot_money.models import (
    Account,
    AccountType,
    Holding,
    Security,
    SecurityType,
    Transaction,
)


class TestAccount:
    """Test Account model."""

    def test_create_account(self):
        account = Account(
            id="acc_123",
            name="My Checking",
            type=AccountType.DEPOSITORY,
            balance=1000.50,
        )
        assert account.id == "acc_123"
        assert account.name == "My Checking"
        assert account.type == AccountType.DEPOSITORY
        assert account.balance == 1000.50


class TestTransaction:
    """Test Transaction model."""

    def test_create_transaction(self):
        txn = Transaction(
            id="txn_123",
            date=date(2026, 1, 15),
            amount=-50.00,
            name="Coffee Shop",
        )
        assert txn.id == "txn_123"
        assert txn.amount == -50.00
        assert txn.name == "Coffee Shop"


class TestSecurity:
    """Test Security model."""

    def test_create_security(self):
        security = Security(
            symbol="VTI",
            name="Vanguard Total Stock Market ETF",
            type=SecurityType.ETF,
            currentPrice=250.00,
        )
        assert security.symbol == "VTI"
        assert security.type == SecurityType.ETF
        assert security.current_price == 250.00


class TestHolding:
    """Test Holding model."""

    def test_holding_value_with_price(self):
        security = Security(
            symbol="VTI",
            name="Vanguard Total Stock Market ETF",
            type=SecurityType.ETF,
            currentPrice=250.00,
        )
        holding = Holding(
            id="hold_123",
            quantity=2.0,
            accountId="acc_123",
            security=security,
        )
        assert holding.value == 500.00

    def test_holding_value_without_price(self):
        security = Security(
            symbol="CASH",
            name="Cash Sweep",
            type=SecurityType.CASH,
        )
        holding = Holding(
            id="hold_456",
            quantity=10.0,
            accountId="acc_456",
            security=security,
        )
        assert holding.value == 0.0
