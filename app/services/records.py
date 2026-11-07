"""Goals, notes, look-through, and a read-only share link for one book."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import (
    AuditEvent,
    CashMovement,
    EtfHolding,
    Goal,
    JournalEntry,
    Portfolio,
    ShareLink,
    Transaction,
)
from app.db.models.transaction import TransactionType
from app.quotes.store import MemoryQuoteStore, QuoteStore
from app.schemas.planning import (
    BehaviorOut,
    ContributionOut,
    GoalCreate,
    GoalOut,
    JournalCreate,
    JournalOut,
    LookThroughOut,
    LookThroughRow,
    ScenarioOut,
    SharedBookOut,
    SharedPosition,
    ShareLinkOut,
)
from app.services.analytics_service import AnalyticsService
from app.services.lookthrough import Constituent, look_through
from app.services.planning import (
    buy_after_runup,
    contributed,
    equal_weight_amounts,
    months_between,
    required_monthly,
    scenarios,
    shares_at_price,
)
from app.services.position_service import PositionService

_GOAL_NOTE = (
    "Each rate is an assumption used to compound the current value and "
    "the monthly amount. It is not a forecast."
)
_DCA_NOTE = (
    "The contributed amount is the monthly figure times the number of "
    "months. Shares use the latest stored or quoted price. The equal-weight "
    "split uses only the holdings already in the book."
)
_BEHAVIOR_NOTE = (
    "Trade count and holding days come from stored fills and open lots. "
    "A buy after a run-up means the fill was at least 10% above a stored "
    "close about 20 sessions earlier. Missing history is left out."
)
_SHARE_NOTE = (
    "Read-only view of stored positions. Not investment advice. "
    "Figures can be delayed."
)


def record_audit(session: Session, user_id: UUID, action: str, subject: str) -> None:
    session.add(
        AuditEvent(
            user_id=user_id,
            action=action[:64],
            subject=subject[:200],
        )
    )


class BookRecords:
    def __init__(
        self,
        session: Session,
        user_id: UUID,
        quotes: QuoteStore | None = None,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.quotes = quotes

    def list_goals(self, portfolio_id: UUID) -> list[GoalOut]:
        self._owned(portfolio_id)
        present = self._market_value(portfolio_id)
        today = date.today()
        rows = self.session.scalars(
            select(Goal)
            .where(Goal.portfolio_id == portfolio_id)
            .order_by(Goal.target_date, Goal.created_at)
        )
        return [self._goal_out(row, present, today) for row in rows]

    def add_goal(self, portfolio_id: UUID, payload: GoalCreate) -> GoalOut:
        self._owned(portfolio_id)
        if payload.monthly_contribution < 0:
            raise ConflictError("Monthly contribution cannot be negative.")
        row = Goal(
            portfolio_id=portfolio_id,
            name=payload.name.strip(),
            target_amount=payload.target_amount,
            target_date=payload.target_date,
            monthly_contribution=payload.monthly_contribution,
        )
        self.session.add(row)
        self.session.flush()
        record_audit(self.session, self.user_id, "goal.create", row.name)
        return self._goal_out(row, self._market_value(portfolio_id), date.today())

    def delete_goal(self, portfolio_id: UUID, goal_id: UUID) -> None:
        self._owned(portfolio_id)
        row = self.session.scalar(
            select(Goal).where(Goal.id == goal_id, Goal.portfolio_id == portfolio_id)
        )
        if row is None:
            raise NotFoundError("Goal not found")
        record_audit(self.session, self.user_id, "goal.delete", row.name)
        self.session.delete(row)
        self.session.flush()

    def contribution(
        self,
        portfolio_id: UUID,
        monthly: Decimal,
        months: int,
    ) -> ContributionOut:
        self._owned(portfolio_id)
        if monthly < 0 or months < 1 or months > 600:
            raise ConflictError("Use a positive monthly amount and 1 to 600 months.")
        positions = self._positions(portfolio_id)
        price = None
        if len(positions.positions) == 1:
            price = positions.positions[0].current_price
        weights = [
            (row.ticker, row.weight)
            for row in positions.positions
            if row.weight is not None
        ]
        split = equal_weight_amounts(weights, monthly)
        return ContributionOut(
            monthly=monthly,
            months=months,
            contributed=contributed(monthly, months),
            shares=shares_at_price(contributed(monthly, months), price),
            price=price,
            equal_weight=[
                {"ticker": ticker, "amount": format(amount, "f")}
                for ticker, amount in split
            ],
            note=_DCA_NOTE,
        )

    def look_through(self, portfolio_id: UUID) -> LookThroughOut:
        self._owned(portfolio_id)
        positions = self._positions(portfolio_id)
        holdings = [
            (row.ticker, row.weight)
            for row in positions.positions
            if row.weight is not None
        ]
        constituents = self._constituents(
            [row.security_id for row in positions.positions]
        )
        by_ticker = {
            row.ticker: constituents.get(row.security_id, [])
            for row in positions.positions
        }
        lines, notes = look_through(holdings, by_ticker)
        return LookThroughOut(
            rows=[
                LookThroughRow(
                    ticker=line.ticker,
                    direct_weight=line.direct_weight,
                    look_through_weight=line.look_through_weight,
                )
                for line in lines
            ],
            notes=notes,
        )

    def refresh_constituents(self, portfolio_id: UUID) -> LookThroughOut:
        self._owned(portfolio_id)
        from app.market_data.yahoo_holdings import fetch_top_holdings

        positions = self._positions(portfolio_id)
        today = date.today()
        for row in positions.positions:
            try:
                fetched = fetch_top_holdings(row.ticker)
            except Exception:
                continue
            if not fetched:
                continue
            existing = self.session.scalars(
                select(EtfHolding).where(EtfHolding.etf_security_id == row.security_id)
            )
            for old in existing:
                self.session.delete(old)
            for ticker, weight in fetched:
                self.session.add(
                    EtfHolding(
                        etf_security_id=row.security_id,
                        constituent_ticker=ticker,
                        weight=weight,
                        as_of=today,
                        source="yahoo",
                    )
                )
        self.session.flush()
        record_audit(self.session, self.user_id, "etf.refresh", str(portfolio_id))
        return self.look_through(portfolio_id)

    def behavior(self, portfolio_id: UUID) -> BehaviorOut:
        self._owned(portfolio_id)
        fills = self.session.scalars(
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.voided_at.is_(None),
            )
            .order_by(Transaction.timestamp)
        ).all()
        positions = self._positions(portfolio_id)
        open_days = [
            lot.held_days for lot in positions.lots if lot.status == "open"
        ]
        average = (
            sum(open_days, Decimal(0)) / Decimal(len(open_days))
            if open_days
            else None
        )
        runup = 0
        comparable = 0
        for fill in fills:
            if fill.transaction_type != TransactionType.BUY:
                continue
            earlier = self._close_before(fill.security_id, fill.timestamp, 20)
            flag = buy_after_runup(fill.price, earlier)
            if flag is None:
                continue
            comparable += 1
            if flag:
                runup += 1
        entries = self.session.scalars(
            select(JournalEntry)
            .where(JournalEntry.portfolio_id == portfolio_id)
            .order_by(JournalEntry.created_at.desc())
        )
        return BehaviorOut(
            trade_count=len(fills),
            average_holding_days=average,
            buys_after_runup=runup if comparable else None,
            buys_with_history=comparable,
            note=_BEHAVIOR_NOTE,
            entries=[
                JournalOut(
                    id=row.id,
                    ticker=row.ticker,
                    note=row.note,
                    created_at=row.created_at,
                )
                for row in entries
            ],
        )

    def add_note(self, portfolio_id: UUID, payload: JournalCreate) -> JournalOut:
        self._owned(portfolio_id)
        ticker = payload.ticker.strip().upper() if payload.ticker else None
        row = JournalEntry(
            portfolio_id=portfolio_id,
            ticker=ticker or None,
            note=payload.note.strip(),
        )
        self.session.add(row)
        self.session.flush()
        record_audit(self.session, self.user_id, "journal.create", ticker or "note")
        return JournalOut(
            id=row.id,
            ticker=row.ticker,
            note=row.note,
            created_at=row.created_at,
        )

    def create_share(self, portfolio_id: UUID) -> ShareLinkOut:
        self._owned(portfolio_id)
        token = secrets.token_urlsafe(32)
        self.session.add(
            ShareLink(
                portfolio_id=portfolio_id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
            )
        )
        self.session.flush()
        record_audit(self.session, self.user_id, "share.create", str(portfolio_id))
        return ShareLinkOut(token=token, path=f"/shared/{token}")

    def shared_book(self, token: str) -> SharedBookOut:
        digest = hashlib.sha256(token.encode()).hexdigest()
        link = self.session.scalar(
            select(ShareLink).where(ShareLink.token_hash == digest)
        )
        if link is None:
            raise NotFoundError("Shared portfolio not found")
        portfolio = self.session.get(Portfolio, link.portfolio_id)
        if portfolio is None:
            raise NotFoundError("Shared portfolio not found")
        positions = PositionService(
            self.session,
            portfolio.user_id,
            self.quotes or MemoryQuoteStore(),
        ).list_positions(portfolio.id)
        total_return = None
        try:
            analytics = AnalyticsService(
                self.session,
                portfolio.user_id,
            ).get_analytics(portfolio.id)
            total_return = analytics.total_return
        except Exception:
            total_return = None
        return SharedBookOut(
            name=portfolio.name,
            is_paper=portfolio.is_paper,
            market_value=positions.market_value,
            total_return=total_return,
            positions=[
                SharedPosition(
                    ticker=row.ticker,
                    quantity=row.quantity,
                    weight=row.weight,
                    market_value=row.market_value,
                )
                for row in positions.positions
            ],
            disclaimer=_SHARE_NOTE,
        )

    def income_events(self, portfolio_id: UUID) -> list[dict[str, object]]:
        self._owned(portfolio_id)
        rows = self.session.scalars(
            select(CashMovement)
            .where(
                CashMovement.portfolio_id == portfolio_id,
                CashMovement.kind == "dividend",
            )
            .order_by(CashMovement.timestamp)
        )
        events: list[dict[str, object]] = []
        for row in rows:
            ticker = row.security.ticker if row.security is not None else None
            events.append(
                {
                    "timestamp": row.timestamp.isoformat(),
                    "ticker": ticker,
                    "amount": format(row.amount, "f"),
                    "currency": row.currency,
                    "kind": "dividend",
                }
            )
        return events

    def _owned(self, portfolio_id: UUID) -> Portfolio:
        portfolio = self.session.scalar(
            select(Portfolio).where(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == self.user_id,
            )
        )
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        return portfolio

    def _positions(self, portfolio_id: UUID):
        return PositionService(
            self.session,
            self.user_id,
            self.quotes or MemoryQuoteStore(),
        ).list_positions(portfolio_id)

    def _market_value(self, portfolio_id: UUID) -> Decimal:
        try:
            positions = self._positions(portfolio_id)
        except Exception:
            return Decimal("0")
        return positions.market_value or Decimal("0")

    def _goal_out(self, row: Goal, present: Decimal, today: date) -> GoalOut:
        months = months_between(
            today.year * 12 + today.month,
            row.target_date.year * 12 + row.target_date.month,
        )
        progress = present / row.target_amount if row.target_amount else None
        built = scenarios(present, row.monthly_contribution, months)
        return GoalOut(
            id=row.id,
            name=row.name,
            target_amount=row.target_amount,
            target_date=row.target_date,
            monthly_contribution=row.monthly_contribution,
            months_remaining=months,
            progress=progress,
            required_monthly_at_zero=required_monthly(
                present, row.target_amount, months, Decimal("0")
            ),
            required_monthly_at_four_percent=required_monthly(
                present, row.target_amount, months, Decimal("0.04")
            ),
            scenarios=[
                ScenarioOut(
                    annual_rate=item.annual_rate,
                    future_value=item.future_value,
                    monthly_contribution=item.monthly_contribution,
                    label=(
                        f"{(item.annual_rate * 100).quantize(Decimal('1'))}"
                        "% assumption"
                    ),
                )
                for item in built
            ],
            note=_GOAL_NOTE,
        )

    def _constituents(
        self,
        security_ids: list[UUID],
    ) -> dict[UUID, list[Constituent]]:
        if not security_ids:
            return {}
        rows = self.session.scalars(
            select(EtfHolding).where(EtfHolding.etf_security_id.in_(security_ids))
        )
        grouped: dict[UUID, list[Constituent]] = {}
        for row in rows:
            grouped.setdefault(row.etf_security_id, []).append(
                Constituent(ticker=row.constituent_ticker, weight=row.weight)
            )
        return grouped

    def _close_before(
        self,
        security_id: UUID,
        moment: datetime,
        sessions: int,
    ) -> Decimal | None:
        from app.db.models import Price

        rows = self.session.scalars(
            select(Price.adjusted_close)
            .where(Price.security_id == security_id, Price.timestamp <= moment)
            .order_by(Price.timestamp.desc())
            .limit(sessions + 1)
        ).all()
        if len(rows) <= sessions:
            return None
        return rows[sessions]

