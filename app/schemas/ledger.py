from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import OptionalDecimalStr, PositiveDecimal


class CashCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["deposit", "withdrawal", "dividend"]
    amount: PositiveDecimal
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fx_rate: PositiveDecimal | None = None
    ticker: str | None = Field(default=None, max_length=16)
    timestamp: datetime | None = None
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def currency_needs_a_rate(self) -> "CashCreate":
        self.currency = self.currency.upper()
        if self.ticker is not None:
            self.ticker = self.ticker.strip().upper() or None
        if self.kind == "dividend" and not self.ticker:
            raise ValueError("A dividend needs the ticker that paid it")
        if self.kind != "dividend" and self.ticker is not None:
            raise ValueError("Only a dividend is tied to a ticker")
        if self.currency != "USD" and self.fx_rate is None:
            raise ValueError(
                "A non-USD amount needs the USD rate you used. "
                "No rate is invented."
            )
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class CashOut(BaseModel):
    id: UUID
    portfolio_id: UUID
    kind: Literal["deposit", "withdrawal", "dividend"]
    amount: PositiveDecimal
    currency: str
    fx_rate: OptionalDecimalStr = None
    usd_amount: OptionalDecimalStr = None
    ticker: str | None = None
    timestamp: datetime
    note: str | None = None
    created_at: datetime


class SplitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    numerator: int = Field(gt=0, le=1000)
    denominator: int = Field(gt=0, le=1000)
    timestamp: datetime | None = None

    @model_validator(mode="after")
    def ratio_changes_shares(self) -> "SplitCreate":
        self.ticker = self.ticker.strip().upper()
        if self.numerator == self.denominator:
            raise ValueError("A split has to change the share count")
        return self


class SplitOut(BaseModel):
    id: UUID
    portfolio_id: UUID
    security_id: UUID
    ticker: str
    numerator: int
    denominator: int
    timestamp: datetime
    created_at: datetime
