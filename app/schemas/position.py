from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalStr, OptionalDecimalStr


class PriceFreshness(BaseModel):
    source: str
    timeliness: str
    as_of: datetime | None = None
    received_at: datetime | None = None
    age_seconds: float | None = None


class PositionOut(BaseModel):
    security_id: UUID
    ticker: str
    quantity: DecimalStr
    average_cost: OptionalDecimalStr = None
    avg_cost: OptionalDecimalStr = None
    cost_basis: OptionalDecimalStr = None
    current_price: OptionalDecimalStr = None
    price: OptionalDecimalStr = None
    previous_close: OptionalDecimalStr = None
    market_value: OptionalDecimalStr = None
    unrealized_pl: OptionalDecimalStr = None
    day_pl: OptionalDecimalStr = None
    weight: OptionalDecimalStr = None
    sector: str = ""
    asset_type: str = "equity"
    currency: str = "USD"
    fx_rate: OptionalDecimalStr = None
    reporting_value: OptionalDecimalStr = None
    price_source: str
    price_timeliness: str = "unavailable"
    quote_provider_timestamp: datetime | None = None
    quote_received_at: datetime | None = None
    quote_age_seconds: float | None = None
    freshness: PriceFreshness


class PositionContribution(BaseModel):
    ticker: str
    day_pl: DecimalStr
    market_value: OptionalDecimalStr = None
    weight: OptionalDecimalStr = None


class WeightBucket(BaseModel):
    label: str
    market_value: DecimalStr
    weight: DecimalStr


class LotOut(BaseModel):
    ticker: str
    quantity: DecimalStr
    cost_price: DecimalStr
    opened_at: datetime
    status: Literal["open", "closed"]
    sell_price: OptionalDecimalStr = None
    realized_pl: OptionalDecimalStr = None
    closed_at: datetime | None = None
    held_days: int = 0
    holding_period: Literal["short", "long"] = "short"


class PositionsResponse(BaseModel):
    portfolio_id: UUID
    cost_basis: OptionalDecimalStr = None
    market_value: OptionalDecimalStr = None
    unrealized_pl: OptionalDecimalStr = None
    day_pl: OptionalDecimalStr = None
    cash: OptionalDecimalStr = None
    income: OptionalDecimalStr = None
    realized_pl: OptionalDecimalStr = None
    yield_on_cost: OptionalDecimalStr = None
    projected_income: OptionalDecimalStr = None
    fund_expense: OptionalDecimalStr = None
    income_note: str = (
        "Yield on cost is stored dividend cash divided by cost. "
        "Projected income multiplies the current value by a stored "
        "dividend yield. Fund expense uses a stored expense ratio. "
        "A missing input stays blank. A long holding period is more "
        "than 365 days from the open date and is not tax advice."
    )
    top_contributors: list[PositionContribution] = Field(default_factory=list)
    top_detractors: list[PositionContribution] = Field(default_factory=list)
    sector_allocation: list[WeightBucket] = Field(default_factory=list)
    asset_allocation: list[WeightBucket] = Field(default_factory=list)
    currency_allocation: list[WeightBucket] = Field(default_factory=list)
    lots: list[LotOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    positions: list[PositionOut]
