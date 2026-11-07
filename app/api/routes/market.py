"""Read the maintained market universe. No portfolio is required.

Daily bars on these routes are rows already stored in PostgreSQL. A
request does not call a vendor and does not invent a missing close.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.market_data.session import session_status
from app.market_data.universe import (
    list_members,
    list_prices,
    market_overview,
    market_status,
)
from app.schemas.planning import SessionOut
from app.schemas.universe import (
    MarketMember,
    MarketMemberPage,
    MarketMover,
    MarketOverviewOut,
    MarketStatusOut,
    StoredBar,
    StoredBarPage,
)
from app.services.fx import DISPLAY_CURRENCIES, load_display_rates

router = APIRouter(prefix="/market", tags=["market"])

_NOTE = (
    "Daily bars are delayed vendor closes, not real-time prices. "
    "This list is the configured US large-cap universe, not every stock."
)


@router.get("/session", response_model=SessionOut)
def get_session() -> SessionOut:
    """US cash session, including full holidays and common 13:00 closes."""
    return SessionOut.model_validate(session_status())


@router.get("/fx")
def get_fx_rates(db: Session = Depends(get_db)) -> dict:
    """USD cross rates for display conversion (USD per 1 foreign unit)."""
    payload = load_display_rates(db)
    payload["currencies"] = list(DISPLAY_CURRENCIES)
    return payload


@router.get("/status", response_model=MarketStatusOut)
def get_market_status(db: Session = Depends(get_db)) -> MarketStatusOut:
    record = market_status(db, settings.universe_code)
    return MarketStatusOut(
        universe=record.universe,
        provider=settings.market_data_provider,
        active_members=record.active_members,
        inactive_members=record.inactive_members,
        last_refresh=record.last_refresh,
        last_success_at=record.last_success_at,
        last_bar_date=record.last_bar_date,
        note=_NOTE,
    )


@router.get("/overview", response_model=MarketOverviewOut)
def get_market_overview(db: Session = Depends(get_db)) -> MarketOverviewOut:
    record = market_overview(db, settings.universe_code)
    return MarketOverviewOut(
        universe=record.universe,
        provider=settings.market_data_provider,
        latest_bar_date=record.latest_bar_date,
        covered_members=record.covered_members,
        active_members=record.active_members,
        advancing=record.advancing,
        declining=record.declining,
        unchanged=record.unchanged,
        gainers=[
            MarketMover.model_validate(row, from_attributes=True)
            for row in record.gainers
        ],
        losers=[
            MarketMover.model_validate(row, from_attributes=True)
            for row in record.losers
        ],
        note=_NOTE,
    )


@router.get("/securities", response_model=MarketMemberPage)
def list_market_securities(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    active: bool = True,
    db: Session = Depends(get_db),
) -> MarketMemberPage:
    members, total = list_members(
        db,
        settings.universe_code,
        limit=limit,
        offset=offset,
        active_only=active,
    )
    items = [
        MarketMember.model_validate(row, from_attributes=True) for row in members
    ]
    return MarketMemberPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/securities/{ticker}/prices", response_model=StoredBarPage)
def list_market_prices(
    ticker: str,
    limit: int = Query(default=90, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StoredBarPage:
    found = list_prices(
        db,
        ticker,
        universe=settings.universe_code,
        limit=limit,
        offset=offset,
    )
    if found is None:
        raise NotFoundError(f"Universe security {ticker} not found")
    rows, total = found
    return StoredBarPage(
        ticker=ticker.strip().upper(),
        items=[
            StoredBar(
                date=row.timestamp.date(),
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                adjusted_close=row.adjusted_close,
                volume=row.volume,
                source=row.source,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
