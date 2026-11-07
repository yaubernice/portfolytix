from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import DecimalStr


class MarketMember(BaseModel):
    ticker: str
    name: str
    exchange: str
    sector: str
    source: str
    active: bool
    refreshed_at: datetime
    latest_bar_date: date | None = None


class MarketMemberPage(BaseModel):
    items: list[MarketMember]
    total: int
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class MarketStatusOut(BaseModel):
    universe: str
    provider: str
    active_members: int
    inactive_members: int
    last_refresh: datetime | None = None
    last_success_at: datetime | None = None
    last_bar_date: date | None = None
    note: str


class MarketMover(BaseModel):
    ticker: str
    name: str
    latest_close: DecimalStr
    previous_close: DecimalStr
    change: DecimalStr
    change_percent: DecimalStr
    latest_bar_date: date
    source: str | None = None


class MarketOverviewOut(BaseModel):
    universe: str
    provider: str
    latest_bar_date: date | None = None
    covered_members: int
    active_members: int
    advancing: int
    declining: int
    unchanged: int
    gainers: list[MarketMover]
    losers: list[MarketMover]
    note: str


class StoredBar(BaseModel):
    date: date
    open: DecimalStr
    high: DecimalStr
    low: DecimalStr
    close: DecimalStr
    adjusted_close: DecimalStr
    volume: int
    source: str | None = None


class StoredBarPage(BaseModel):
    ticker: str
    items: list[StoredBar]
    total: int
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
