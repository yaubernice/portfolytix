"""S&P 500 constituent list and the symbols due for a daily-bar refresh.

The source is the public ``datasets/s-and-p-500-companies`` file. It is a
maintained list of US large-cap names, not an official S&P Global feed,
not every US listing, and not a world universe. Importing it writes
security metadata and memberships only. It does not write prices, users,
portfolios, or transactions.

A name that leaves the file is marked inactive. Its security row and
stored prices stay. Daily bars are fetched later by the existing provider
adapters. Yahoo's chart endpoint is unofficial: the bars are delayed
daily closes, not real-time quotes, and Yahoo does not grant a license to
republish that data as a feed.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from io import StringIO
from uuid import UUID

import httpx
from sqlalchemy import func, nulls_first, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.db.models import JobRun, JobStatus, Price, Security, UniverseMembership
from app.market_data.errors import ProviderError
from app.repositories.job_run_repository import JOB_NAME_MARKET_DATA
from app.repositories.security_repository import SecurityRepository

UNIVERSE_SOURCE_NAME = "datasets/s-and-p-500-companies"
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")


@dataclass(frozen=True)
class UniverseListing:
    ticker: str
    name: str
    sector: str
    exchange: str


@dataclass
class UniverseRefreshReport:
    universe: str
    parsed: int
    securities_inserted: int = 0
    memberships_upserted: int = 0
    memberships_deactivated: int = 0
    skipped_tickers: list[str] = field(default_factory=list)


def parse_sp500_constituents(text: str) -> list[UniverseListing]:
    """Read the constituent CSV. Rows without a ticker or name are skipped.

    The published file has no exchange column. ``exchange`` is empty when
    this source does not provide one. Duplicate tickers keep the first row.
    """
    reader = csv.DictReader(StringIO(text))
    listings: list[UniverseListing] = []
    seen: set[str] = set()
    for row in reader:
        if not isinstance(row, dict):
            continue
        raw = row.get("Symbol") or row.get("symbol") or ""
        ticker = str(raw).strip().upper()
        name = " ".join(str(row.get("Security") or row.get("name") or "").split())
        if not ticker or not name or not _TICKER.match(ticker) or ticker in seen:
            continue
        seen.add(ticker)
        sector = str(row.get("GICS Sector") or row.get("sector") or "").strip()
        exchange = str(row.get("Exchange") or row.get("exchange") or "").strip()
        listings.append(
            UniverseListing(
                ticker=ticker,
                name=name[:200],
                sector=sector[:64],
                exchange=exchange[:32],
            )
        )
    return listings


def download_constituents(
    url: str,
    client: httpx.Client | None = None,
) -> str:
    """Download the constituent file. The URL is not included in errors."""
    owns_client = client is None
    http = client or httpx.Client(timeout=60.0, follow_redirects=True)
    try:
        try:
            response = http.get(url, headers={"User-Agent": "Portfolytix/1.0"})
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"universe source request failed: {type(exc).__name__}"
            ) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderError(
                f"universe source returned HTTP {response.status_code}"
            )
        if response.status_code != 200:
            raise ProviderError(
                f"universe source returned HTTP {response.status_code}",
                retryable=False,
            )
        if not response.text.strip():
            raise ProviderError("universe source was empty", retryable=False)
        return response.text
    finally:
        if owns_client:
            http.close()


def apply_universe(
    session: Session,
    listings: list[UniverseListing],
    *,
    universe: str,
    source: str = UNIVERSE_SOURCE_NAME,
) -> UniverseRefreshReport:
    """Upsert memberships. An empty file changes nothing.

    Existing securities are reused by ticker. A ticker that already maps
    to more than one security is skipped. Prices are not written or deleted.
    """
    if not listings:
        raise ValueError("universe listing is empty; no memberships were changed")
    report = UniverseRefreshReport(universe=universe, parsed=len(listings))
    now = datetime.now(UTC)
    seen: set[UUID] = set()
    securities = SecurityRepository(session)
    for listing in listings:
        try:
            existing = securities.get_by_ticker(listing.ticker)
        except ConflictError:
            report.skipped_tickers.append(listing.ticker)
            continue
        if existing is None:
            existing = Security(
                ticker=listing.ticker,
                name=listing.name,
                exchange=listing.exchange or "unspecified",
                sector=listing.sector,
                country="US",
                currency="USD",
                asset_type="equity",
                provider="sp500",
                provider_symbol=listing.ticker,
                is_active=True,
            )
            session.add(existing)
            session.flush()
            report.securities_inserted += 1
        _upsert_membership(
            session,
            universe=universe,
            security_id=existing.id,
            source=source[:200],
            refreshed_at=now,
        )
        seen.add(existing.id)
        report.memberships_upserted += 1
    if not seen:
        return report
    result = session.execute(
        update(UniverseMembership)
        .where(
            UniverseMembership.universe_code == universe,
            UniverseMembership.active.is_(True),
            UniverseMembership.security_id.not_in(seen),
        )
        .values(active=False, refreshed_at=now)
    )
    report.memberships_deactivated = int(result.rowcount or 0)
    session.flush()
    return report


def tickers_for_ingest(session: Session, universe: str, limit: int) -> list[str]:
    """Active members with the oldest stored bar first. Never-priced names lead.

    ``limit`` is the whole batch. Holdings are not consulted.
    """
    if limit < 1:
        raise ValueError("universe ingest limit must be >= 1")
    latest = (
        select(
            Price.security_id.label("security_id"),
            func.max(Price.timestamp).label("last_bar"),
        )
        .group_by(Price.security_id)
        .subquery()
    )
    statement = (
        select(Security.ticker)
        .join(
            UniverseMembership,
            UniverseMembership.security_id == Security.id,
        )
        .outerjoin(latest, latest.c.security_id == Security.id)
        .where(
            UniverseMembership.universe_code == universe,
            UniverseMembership.active.is_(True),
            Security.is_active.is_(True),
        )
        .order_by(nulls_first(latest.c.last_bar.asc()), Security.ticker.asc())
        .limit(limit)
    )
    return list(session.scalars(statement))


@dataclass(frozen=True)
class MarketMemberRecord:
    ticker: str
    name: str
    exchange: str
    sector: str
    source: str
    active: bool
    refreshed_at: datetime
    latest_bar_date: date | None


@dataclass(frozen=True)
class MarketStatusRecord:
    universe: str
    active_members: int
    inactive_members: int
    last_refresh: datetime | None
    last_success_at: datetime | None
    last_bar_date: date | None


@dataclass(frozen=True)
class MarketMoverRecord:
    ticker: str
    name: str
    latest_close: object
    previous_close: object
    change: object
    change_percent: object
    latest_bar_date: date
    source: str | None


@dataclass(frozen=True)
class MarketOverviewRecord:
    universe: str
    latest_bar_date: date | None
    covered_members: int
    active_members: int
    advancing: int
    declining: int
    unchanged: int
    gainers: list[MarketMoverRecord]
    losers: list[MarketMoverRecord]


def list_members(
    session: Session,
    universe: str,
    *,
    limit: int,
    offset: int,
    active_only: bool,
) -> tuple[list[MarketMemberRecord], int]:
    filters = [UniverseMembership.universe_code == universe]
    if active_only:
        filters.append(UniverseMembership.active.is_(True))
    total = int(
        session.scalar(
            select(func.count())
            .select_from(UniverseMembership)
            .where(*filters)
        )
        or 0
    )
    latest = _latest_bars()
    rows = session.execute(
        select(Security, UniverseMembership, latest.c.last_bar)
        .join(
            UniverseMembership,
            UniverseMembership.security_id == Security.id,
        )
        .outerjoin(latest, latest.c.security_id == Security.id)
        .where(*filters)
        .order_by(Security.ticker.asc())
        .limit(limit)
        .offset(offset)
    )
    members = [
        MarketMemberRecord(
            ticker=security.ticker,
            name=security.name,
            exchange=security.exchange,
            sector=security.sector,
            source=membership.source,
            active=membership.active,
            refreshed_at=membership.refreshed_at,
            latest_bar_date=_as_date(last_bar),
        )
        for security, membership, last_bar in rows
    ]
    return members, total


def list_prices(
    session: Session,
    ticker: str,
    *,
    universe: str,
    limit: int,
    offset: int,
) -> tuple[list[Price], int] | None:
    """Stored bars only. ``None`` means that ticker is not an active member."""
    security_id = session.scalar(
        select(Security.id)
        .join(
            UniverseMembership,
            UniverseMembership.security_id == Security.id,
        )
        .where(
            Security.ticker == ticker.strip().upper(),
            UniverseMembership.universe_code == universe,
            UniverseMembership.active.is_(True),
        )
    )
    if security_id is None:
        return None
    total = int(
        session.scalar(
            select(func.count())
            .select_from(Price)
            .where(Price.security_id == security_id)
        )
        or 0
    )
    rows = list(
        session.scalars(
            select(Price)
            .where(Price.security_id == security_id)
            .order_by(Price.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, total


def market_status(session: Session, universe: str) -> MarketStatusRecord:
    active = _member_count(session, universe, active=True)
    inactive = _member_count(session, universe, active=False)
    last_refresh = session.scalar(
        select(func.max(UniverseMembership.refreshed_at)).where(
            UniverseMembership.universe_code == universe
        )
    )
    latest = _latest_bars()
    last_bar = session.scalar(
        select(func.max(latest.c.last_bar))
        .select_from(UniverseMembership)
        .outerjoin(latest, latest.c.security_id == UniverseMembership.security_id)
        .where(UniverseMembership.universe_code == universe)
    )
    last_success = session.scalar(
        select(func.max(JobRun.finished_at)).where(
            JobRun.job_name == JOB_NAME_MARKET_DATA,
            JobRun.status == JobStatus.SUCCESS,
        )
    )
    return MarketStatusRecord(
        universe=universe,
        active_members=active,
        inactive_members=inactive,
        last_refresh=last_refresh if isinstance(last_refresh, datetime) else None,
        last_success_at=last_success if isinstance(last_success, datetime) else None,
        last_bar_date=_as_date(last_bar),
    )


def market_overview(
    session: Session,
    universe: str,
    *,
    mover_limit: int = 5,
) -> MarketOverviewRecord:
    """Summarize the two latest stored closes per active universe member."""
    ranked = (
        select(
            Price.security_id.label("security_id"),
            Price.timestamp.label("timestamp"),
            Price.adjusted_close.label("close"),
            Price.source.label("source"),
            func.row_number()
            .over(
                partition_by=Price.security_id,
                order_by=Price.timestamp.desc(),
            )
            .label("position"),
        )
        .subquery()
    )
    rows = session.execute(
        select(
            Security.ticker,
            Security.name,
            ranked.c.timestamp,
            ranked.c.close,
            ranked.c.source,
            ranked.c.position,
        )
        .join(
            UniverseMembership,
            UniverseMembership.security_id == Security.id,
        )
        .join(ranked, ranked.c.security_id == Security.id)
        .where(
            UniverseMembership.universe_code == universe,
            UniverseMembership.active.is_(True),
            Security.is_active.is_(True),
            ranked.c.position <= 2,
        )
        .order_by(Security.ticker, ranked.c.position)
    )
    by_ticker: dict[str, list[tuple]] = {}
    names: dict[str, str] = {}
    for ticker, name, timestamp, close, source, position in rows:
        names[ticker] = name
        by_ticker.setdefault(ticker, []).append(
            (timestamp, close, source, position)
        )
    movers: list[MarketMoverRecord] = []
    latest_date: date | None = None
    advancing = declining = unchanged = 0
    for ticker, bars in by_ticker.items():
        ordered = sorted(bars, key=lambda row: row[3])
        if ordered:
            day = _as_date(ordered[0][0])
            if day is not None and (latest_date is None or day > latest_date):
                latest_date = day
        if len(ordered) < 2:
            continue
        latest, previous = ordered[0], ordered[1]
        if previous[1] is None or previous[1] <= 0:
            continue
        change = latest[1] - previous[1]
        change_percent = change / previous[1]
        if change > 0:
            advancing += 1
        elif change < 0:
            declining += 1
        else:
            unchanged += 1
        day = _as_date(latest[0])
        if day is None:
            continue
        movers.append(
            MarketMoverRecord(
                ticker=ticker,
                name=names[ticker],
                latest_close=latest[1],
                previous_close=previous[1],
                change=change,
                change_percent=change_percent,
                latest_bar_date=day,
                source=latest[2],
            )
        )
    movers.sort(key=lambda row: (row.change_percent, row.ticker))
    active = _member_count(session, universe, active=True)
    return MarketOverviewRecord(
        universe=universe,
        latest_bar_date=latest_date,
        covered_members=len(by_ticker),
        active_members=active,
        advancing=advancing,
        declining=declining,
        unchanged=unchanged,
        gainers=list(reversed(movers[-mover_limit:])),
        losers=movers[:mover_limit],
    )


def _latest_bars():
    return (
        select(
            Price.security_id.label("security_id"),
            func.max(Price.timestamp).label("last_bar"),
        )
        .group_by(Price.security_id)
        .subquery()
    )


def _member_count(session: Session, universe: str, *, active: bool) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(UniverseMembership)
            .where(
                UniverseMembership.universe_code == universe,
                UniverseMembership.active.is_(active),
            )
        )
        or 0
    )


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _upsert_membership(
    session: Session,
    *,
    universe: str,
    security_id,
    source: str,
    refreshed_at: datetime,
) -> None:
    row = session.scalar(
        select(UniverseMembership).where(
            UniverseMembership.universe_code == universe,
            UniverseMembership.security_id == security_id,
        )
    )
    if row is None:
        session.add(
            UniverseMembership(
                universe_code=universe,
                security_id=security_id,
                source=source,
                active=True,
                refreshed_at=refreshed_at,
            )
        )
        session.flush()
        return
    row.active = True
    row.source = source
    row.refreshed_at = refreshed_at
    session.flush()
