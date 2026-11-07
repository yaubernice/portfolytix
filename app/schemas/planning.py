from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DecimalStr, OptionalDecimalStr, PositiveDecimal


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    target_amount: PositiveDecimal
    target_date: date
    monthly_contribution: DecimalStr = Decimal("0")


class ScenarioOut(BaseModel):
    annual_rate: DecimalStr
    future_value: DecimalStr
    monthly_contribution: DecimalStr
    label: str


class GoalOut(BaseModel):
    id: UUID
    name: str
    target_amount: DecimalStr
    target_date: date
    monthly_contribution: DecimalStr
    months_remaining: int
    progress: OptionalDecimalStr = None
    required_monthly_at_zero: OptionalDecimalStr = None
    required_monthly_at_four_percent: OptionalDecimalStr = None
    scenarios: list[ScenarioOut]
    note: str


class ContributionOut(BaseModel):
    monthly: DecimalStr
    months: int
    contributed: DecimalStr
    shares: OptionalDecimalStr = None
    price: OptionalDecimalStr = None
    equal_weight: list[dict[str, str]]
    note: str


class LookThroughRow(BaseModel):
    ticker: str
    direct_weight: DecimalStr
    look_through_weight: DecimalStr


class LookThroughOut(BaseModel):
    rows: list[LookThroughRow]
    notes: list[str]


class JournalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=2000)
    ticker: str | None = Field(default=None, max_length=16)


class JournalOut(BaseModel):
    id: UUID
    ticker: str | None
    note: str
    created_at: datetime


class BehaviorOut(BaseModel):
    trade_count: int
    average_holding_days: OptionalDecimalStr = None
    buys_after_runup: int | None
    buys_with_history: int
    note: str
    entries: list[JournalOut]


class ShareLinkOut(BaseModel):
    token: str
    path: str


class SharedPosition(BaseModel):
    ticker: str
    quantity: DecimalStr
    weight: OptionalDecimalStr = None
    market_value: OptionalDecimalStr = None


class SharedBookOut(BaseModel):
    name: str
    is_paper: bool
    market_value: OptionalDecimalStr = None
    total_return: OptionalDecimalStr = None
    positions: list[SharedPosition]
    disclaimer: str


class SessionOut(BaseModel):
    open: bool
    reason: Literal["open", "weekend", "holiday", "hours"]
    as_of: str
    timezone: str
    closes_at: str


class AccountExport(BaseModel):
    email: str
    portfolios: list[dict[str, object]]
