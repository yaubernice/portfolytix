from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import OptionalDecimalStr, PositiveDecimal


class WatchlistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class WatchlistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class WatchlistItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    security_id: UUID


class WatchlistItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_price: PositiveDecimal | None = None
    alert_when: Literal["above", "below"] | None = None
    clear_target: bool = False

    @model_validator(mode="after")
    def target_and_direction(self) -> "WatchlistItemUpdate":
        if self.clear_target:
            return self
        if (self.target_price is None) != (self.alert_when is None):
            raise ValueError("A price target needs both a price and above or below")
        return self


class WatchlistItemOut(BaseModel):
    id: UUID
    security_id: UUID
    ticker: str
    name: str
    exchange: str
    target_price: OptionalDecimalStr = None
    alert_when: Literal["above", "below"] | None = None
    created_at: datetime


class WatchlistSummary(BaseModel):
    id: UUID
    name: str
    item_count: int
    created_at: datetime
    updated_at: datetime


class WatchlistPage(BaseModel):
    items: list[WatchlistSummary]
    total: int
    limit: int
    offset: int


class WatchlistDetail(WatchlistSummary):
    items: list[WatchlistItemOut]
    items_total: int
    items_limit: int
    items_offset: int
