from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AccountType(str, Enum):
    DEPOSITORY = "DEPOSITORY"
    CREDIT = "CREDIT"
    INVESTMENT = "INVESTMENT"
    LOAN = "LOAN"
    REAL_ESTATE = "REAL_ESTATE"
    OTHER = "OTHER"


class SecurityType(str, Enum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    CRYPTO = "CRYPTO"
    BOND = "BOND"
    CASH = "CASH"
    OTHER = "OTHER"


class Account(BaseModel):
    id: str
    name: str
    balance: float
    type: AccountType


class Transaction(BaseModel):
    id: str
    name: str
    amount: float
    date: date


class Security(BaseModel):
    symbol: str
    name: str
    type: SecurityType = SecurityType.OTHER
    current_price: Optional[float] = Field(None, alias="currentPrice")


class Holding(BaseModel):
    id: str
    quantity: float
    account_id: str = Field(alias="accountId")
    security: Security

    @property
    def value(self) -> float:
        if self.security.current_price is None:
            return 0.0
        return self.quantity * self.security.current_price
