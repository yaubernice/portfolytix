from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.cache import queue_version_bump
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import CashMovement, ShareSplit
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.security_repository import SecurityRepository
from app.schemas.ledger import CashCreate, CashOut, SplitCreate, SplitOut


class LedgerService:
    """Cash, dividends, and splits for one owner's portfolio."""

    def __init__(self, session: Session, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.portfolios = PortfolioRepository(session)
        self.securities = SecurityRepository(session)

    def list_cash(self, portfolio_id: UUID) -> list[CashOut]:
        self._require(portfolio_id)
        rows = self.session.scalars(
            select(CashMovement)
            .options(joinedload(CashMovement.security))
            .where(CashMovement.portfolio_id == portfolio_id)
            .order_by(CashMovement.timestamp, CashMovement.created_at)
        ).unique()
        return [_cash_out(row) for row in rows]

    def add_cash(self, portfolio_id: UUID, payload: CashCreate) -> CashOut:
        self._require_locked(portfolio_id)
        if payload.kind == "withdrawal":
            rate = Decimal("1") if payload.fx_rate is None else payload.fx_rate
            if payload.currency == "USD":
                leaving = payload.amount
            else:
                leaving = payload.amount * rate
            available = self._usd_balance(portfolio_id)
            if leaving > available:
                raise ConflictError(
                    f"Cannot withdraw {leaving} USD; cash available is {available} USD"
                )
        security_id = None
        if payload.ticker:
            security = self.securities.get_by_ticker(payload.ticker)
            if security is None:
                raise NotFoundError(f"Security {payload.ticker} not found")
            security_id = security.id
        row = CashMovement(
            portfolio_id=portfolio_id,
            kind=payload.kind,
            amount=payload.amount,
            currency=payload.currency,
            fx_rate=payload.fx_rate if payload.currency != "USD" else None,
            security_id=security_id,
            timestamp=payload.timestamp or datetime.now(UTC),
            note=payload.note,
        )
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        queue_version_bump(self.session, f"portfolio:{portfolio_id}")
        return _cash_out(row)

    def delete_cash(self, portfolio_id: UUID, movement_id: UUID) -> None:
        self._require_locked(portfolio_id)
        row = self.session.scalar(
            select(CashMovement).where(
                CashMovement.portfolio_id == portfolio_id,
                CashMovement.id == movement_id,
            )
        )
        if row is None:
            raise NotFoundError("Cash movement not found")
        self.session.delete(row)
        self.session.flush()
        queue_version_bump(self.session, f"portfolio:{portfolio_id}")

    def list_splits(self, portfolio_id: UUID) -> list[SplitOut]:
        self._require(portfolio_id)
        rows = self.session.scalars(
            select(ShareSplit)
            .options(joinedload(ShareSplit.security))
            .where(ShareSplit.portfolio_id == portfolio_id)
            .order_by(ShareSplit.timestamp, ShareSplit.created_at)
        ).unique()
        return [_split_out(row) for row in rows]

    def add_split(self, portfolio_id: UUID, payload: SplitCreate) -> SplitOut:
        self._require_locked(portfolio_id)
        security = self.securities.get_by_ticker(payload.ticker)
        if security is None:
            raise NotFoundError(f"Security {payload.ticker} not found")
        row = ShareSplit(
            portfolio_id=portfolio_id,
            security_id=security.id,
            numerator=payload.numerator,
            denominator=payload.denominator,
            timestamp=payload.timestamp or datetime.now(UTC),
        )
        row.security = security
        self.session.add(row)
        self.session.flush()
        queue_version_bump(self.session, f"portfolio:{portfolio_id}")
        return _split_out(row)

    def delete_split(self, portfolio_id: UUID, split_id: UUID) -> None:
        self._require_locked(portfolio_id)
        row = self.session.scalar(
            select(ShareSplit).where(
                ShareSplit.portfolio_id == portfolio_id,
                ShareSplit.id == split_id,
            )
        )
        if row is None:
            raise NotFoundError("Split not found")
        self.session.delete(row)
        self.session.flush()
        queue_version_bump(self.session, f"portfolio:{portfolio_id}")

    def _usd_balance(self, portfolio_id: UUID) -> Decimal:
        total = Decimal("0")
        rows = self.session.scalars(
            select(CashMovement).where(CashMovement.portfolio_id == portfolio_id)
        )
        for row in rows:
            signed = usd_amount(row.amount, row.currency, row.fx_rate)
            if signed is None:
                continue
            if row.kind == "withdrawal":
                total -= signed
            else:
                total += signed
        return total

    def _require(self, portfolio_id: UUID):
        portfolio = self.portfolios.get_owned(portfolio_id, self.user_id)
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        return portfolio

    def _require_locked(self, portfolio_id: UUID):
        portfolio = self.portfolios.get_owned_for_update(portfolio_id, self.user_id)
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        return portfolio


def usd_amount(
    amount: Decimal,
    currency: str,
    fx_rate: Decimal | None,
) -> Decimal | None:
    """Convert with the stored rate. USD needs no rate. A missing rate stays unset."""
    if currency.upper() == "USD":
        return amount
    if fx_rate is None:
        return None
    return amount * fx_rate


def _cash_out(row: CashMovement) -> CashOut:
    ticker = row.security.ticker if row.security is not None else None
    return CashOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        kind=row.kind,  # type: ignore[arg-type]
        amount=row.amount,
        currency=row.currency,
        fx_rate=row.fx_rate,
        usd_amount=usd_amount(row.amount, row.currency, row.fx_rate),
        ticker=ticker,
        timestamp=row.timestamp,
        note=row.note,
        created_at=row.created_at,
    )


def _split_out(row: ShareSplit) -> SplitOut:
    return SplitOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        security_id=row.security_id,
        ticker=row.security.ticker,
        numerator=row.numerator,
        denominator=row.denominator,
        timestamp=row.timestamp,
        created_at=row.created_at,
    )

