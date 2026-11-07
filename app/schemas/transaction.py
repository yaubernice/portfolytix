from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.transaction import TransactionType
from app.schemas.common import PositiveDecimal


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    transaction_type: TransactionType
    quantity: PositiveDecimal
    price: PositiveDecimal
    timestamp: datetime | None = Field(
        default=None,
        description="Fill time. Defaults to now (UTC) when omitted.",
    )
    price_basis: Literal["quote", "entered"] = "quote"

    @field_validator("quantity")
    @classmethod
    def whole_shares(cls, value: Decimal) -> Decimal:
        if value != value.to_integral_value():
            raise ValueError("Quantity must be a whole number of shares")
        return value


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_type: TransactionType | None = None
    quantity: PositiveDecimal | None = None
    price: PositiveDecimal | None = None
    timestamp: datetime | None = None
    price_basis: Literal["quote", "entered"] = "entered"

    @field_validator("quantity")
    @classmethod
    def whole_shares_when_set(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value != value.to_integral_value():
            raise ValueError("Quantity must be a whole number of shares")
        return value


class TransactionImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[TransactionCreate] = Field(min_length=1, max_length=100)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    security_id: UUID
    ticker: str
    transaction_type: TransactionType
    quantity: PositiveDecimal
    price: PositiveDecimal
    timestamp: datetime
    created_at: datetime
