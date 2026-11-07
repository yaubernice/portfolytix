from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import queue_version_bump
from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.db.models import Portfolio, ShareSplit, Transaction
from app.db.models.transaction import TransactionType
from app.quotes.provider_marks import provider_quotes
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.security_repository import SecurityRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.holding import HoldingOut
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioDetail,
    PortfolioSummary,
    PortfolioUpdate,
)
from app.schemas.transaction import (
    TransactionCreate,
    TransactionImport,
    TransactionOut,
    TransactionUpdate,
)
from app.services.holdings import PositionLeg, aggregate_positions, quantity_held
from app.services.lots import SplitEvent, TimedFill, average_cost_with_splits
from app.services.records import record_audit


class PortfolioService:
    def __init__(self, session: Session, user_id: UUID) -> None:
        self.user_id = user_id
        self.portfolios = PortfolioRepository(session)
        self.securities = SecurityRepository(session)
        self.transactions = TransactionRepository(session)

    def create_portfolio(self, payload: PortfolioCreate) -> PortfolioSummary: 
        portfolio = Portfolio(
            user_id=self.user_id,
            name=payload.name,
            description=payload.description,
            is_paper=payload.is_paper,
        )
        return PortfolioSummary.model_validate(self.portfolios.add(portfolio))

#The authenticated user can only list their own portfolios.
    def list_portfolios(self) -> list[PortfolioSummary]:
        return [
            PortfolioSummary.model_validate(row)
            for row in self.portfolios.list_for_user(self.user_id)
        ]

    def get_portfolio(self, portfolio_id: UUID) -> PortfolioDetail:
        portfolio = self._require_portfolio(portfolio_id)
        return self._detail(portfolio)

    def update_portfolio(
        self, portfolio_id: UUID, payload: PortfolioUpdate
    ) -> PortfolioDetail:
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise AppError("PATCH requires at least one field", status_code=422)
        portfolio = self._require_portfolio(portfolio_id)
        if "name" in data:
            portfolio.name = data["name"]
        if "description" in data:
            portfolio.description = data["description"]
        if "is_paper" in data and data["is_paper"] is not None:
            portfolio.is_paper = data["is_paper"]
        self.portfolios.session.flush()
        self.portfolios.session.refresh(portfolio)
        return self._detail(portfolio)

    def delete_portfolio(self, portfolio_id: UUID) -> None:
        portfolio = self._require_portfolio(portfolio_id)
        self.portfolios.delete(portfolio)
        queue_version_bump(
            self.portfolios.session,
            f"portfolio:{portfolio_id}",
        )

    def list_holdings(self, portfolio_id: UUID) -> list[HoldingOut]:
        self._require_portfolio(portfolio_id)
        return self._holdings(portfolio_id)

    def list_transactions(self, portfolio_id: UUID) -> list[TransactionOut]:
        self._require_portfolio(portfolio_id)
        rows = self.transactions.list_for_portfolio(portfolio_id)
        return [self._transaction_out(row) for row in rows]

    def add_transaction(  #check ownership and lock the portfolio row for update
        self, portfolio_id: UUID, payload: TransactionCreate
    ) -> TransactionOut:
        portfolio = self.portfolios.get_owned_for_update(
            portfolio_id,
            self.user_id,
        )
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")

        ticker = payload.ticker.upper()
        security = self.securities.get_by_ticker(ticker)
        if security is None:
            raise NotFoundError(f"Security {ticker} not found")

        if payload.quantity != payload.quantity.to_integral_value():
            raise ConflictError("Buy and sell a whole number of shares.")
        if payload.quantity < 1:
            raise ConflictError("The smallest order is 1 share.")

        held = self._open_quantity(portfolio_id, security.id)
        if payload.transaction_type is TransactionType.SELL and payload.quantity > held:
            raise ConflictError(
                f"Cannot SELL {payload.quantity} {ticker}; "
                f"current position is {held}"
            )

        price = self._fill_price(ticker, payload.price, payload.price_basis)

        row = Transaction(
            portfolio_id=portfolio.id,
            security_id=security.id,
            transaction_type=payload.transaction_type.value,
            quantity=payload.quantity,
            price=price,
            timestamp=payload.timestamp or datetime.now(UTC),
        )
        saved = self.transactions.add(row)
        saved.security = security #add security object to the transaction object
        queue_version_bump(
            self.portfolios.session,
            f"portfolio:{portfolio_id}",
        )
        return self._transaction_out(saved)

    def update_transaction(
        self,
        portfolio_id: UUID,
        transaction_id: UUID,
        payload: TransactionUpdate,
    ) -> TransactionOut:
        portfolio = self.portfolios.get_owned_for_update(portfolio_id, self.user_id)
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        row = self.transactions.get_for_portfolio(portfolio_id, transaction_id)
        if row is None:
            raise NotFoundError("Transaction not found")
        side = payload.transaction_type or TransactionType(row.transaction_type)
        quantity = payload.quantity if payload.quantity is not None else row.quantity
        if quantity != quantity.to_integral_value() or quantity < 1:
            raise ConflictError("Buy and sell a whole number of shares.")
        held = self._open_quantity(portfolio_id, row.security_id, ignore_id=row.id)
        if side is TransactionType.SELL and quantity > held:
            raise ConflictError(
                f"Cannot SELL {quantity} {row.security.ticker}; "
                f"current position is {held}"
            )
        price = row.price
        if payload.price is not None or payload.price_basis == "quote":
            price = self._fill_price(
                row.security.ticker,
                payload.price if payload.price is not None else row.price,
                payload.price_basis,
            )
        row.voided_at = datetime.now(UTC)
        replacement = Transaction(
            portfolio_id=row.portfolio_id,
            security_id=row.security_id,
            transaction_type=side.value,
            quantity=quantity,
            price=price,
            timestamp=payload.timestamp or row.timestamp,
            corrects_id=row.id,
        )
        saved = self.transactions.add(replacement)
        saved.security = row.security
        record_audit(
            self.portfolios.session,
            self.user_id,
            "transaction.replace",
            str(row.id),
        )
        queue_version_bump(self.portfolios.session, f"portfolio:{portfolio_id}")
        return self._transaction_out(saved)

    def delete_transaction(self, portfolio_id: UUID, transaction_id: UUID) -> None:
        portfolio = self.portfolios.get_owned_for_update(portfolio_id, self.user_id)
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        row = self.transactions.get_for_portfolio(portfolio_id, transaction_id)
        if row is None:
            raise NotFoundError("Transaction not found")
        row.voided_at = datetime.now(UTC)
        record_audit(
            self.portfolios.session,
            self.user_id,
            "transaction.void",
            str(row.id),
        )
        self.portfolios.session.flush()
        queue_version_bump(self.portfolios.session, f"portfolio:{portfolio_id}")

    def import_transactions(
        self,
        portfolio_id: UUID,
        payload: TransactionImport,
    ) -> list[TransactionOut]:
        saved: list[TransactionOut] = []
        for row in payload.rows:
            saved.append(
                self.add_transaction(
                    portfolio_id,
                    row.model_copy(update={"price_basis": "entered"}),
                )
            )
        return saved

    def _fill_price(self, ticker: str, entered: Decimal, basis: str) -> Decimal:
        if basis == "entered" or not settings.provider_marks:
            return entered
        quote = provider_quotes([ticker]).get(ticker)
        if quote is None:
            raise ConflictError(f"No latest provider price is available for {ticker}.")
        return quote.price

    def _open_quantity(
        self,
        portfolio_id: UUID,
        security_id: UUID,
        ignore_id: UUID | None = None,
    ) -> Decimal:
        rows = [
            row
            for row in self.transactions.list_for_portfolio(portfolio_id)
            if row.id != ignore_id
        ]
        splits = list(
            self.portfolios.session.scalars(
                select(ShareSplit).where(ShareSplit.portfolio_id == portfolio_id)
            )
        )
        if splits:
            costs = average_cost_with_splits(
                [
                    TimedFill(
                        security_id=row.security_id,
                        ticker=row.security.ticker,
                        transaction_type=row.transaction_type,
                        quantity=row.quantity,
                        price=row.price,
                        timestamp=row.timestamp,
                    )
                    for row in rows
                ],
                [
                    SplitEvent(
                        security_id=row.security_id,
                        ratio=Decimal(row.numerator) / Decimal(row.denominator),
                        timestamp=row.timestamp,
                    )
                    for row in splits
                ],
            )
            for cost in costs:
                if cost.security_id == security_id and cost.quantity > 0:
                    return cost.quantity
            return Decimal("0")
        legs = [
            PositionLeg(
                security_id=row.security_id,
                ticker=row.security.ticker,
                transaction_type=row.transaction_type,
                quantity=row.quantity,
            )
            for row in rows
        ]
        return quantity_held(aggregate_positions(legs), security_id)

    def _require_portfolio(self, portfolio_id: UUID) -> Portfolio:
        portfolio = self.portfolios.get_owned(portfolio_id, self.user_id)
        if portfolio is None:
            raise NotFoundError(f"Portfolio {portfolio_id} not found")
        return portfolio

    def _holdings(self, portfolio_id: UUID) -> list[HoldingOut]: 
        legs = [
            PositionLeg(
                security_id=row.security_id,
                ticker=row.security.ticker,
                transaction_type=row.transaction_type,
                quantity=row.quantity,
            )
            for row in self.transactions.list_for_portfolio(portfolio_id)
        ]
        return aggregate_positions(legs)

    def _detail(self, portfolio: Portfolio) -> PortfolioDetail: 
        summary = PortfolioSummary.model_validate(portfolio)
        return PortfolioDetail(
            **summary.model_dump(),
            holdings=self._holdings(portfolio.id),
        )

    def _transaction_out(self, row: Transaction) -> TransactionOut:
        return TransactionOut(
            id=row.id,
            portfolio_id=row.portfolio_id,
            security_id=row.security_id,
            ticker=row.security.ticker,
            transaction_type=TransactionType(row.transaction_type),
            quantity=row.quantity,
            price=row.price,
            timestamp=row.timestamp,
            created_at=row.created_at,
        )
