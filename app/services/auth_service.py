from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, AuthenticationError, ConflictError
from app.core.login_limit import clear_attempts, record_failure, too_many_attempts
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import CashMovement, Goal, JournalEntry, Portfolio, Transaction, User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.services.analytics_service import AnalyticsService
from app.services.pdf_report import render_account_pdf
from app.services.position_service import PositionService
from app.services.records import BookRecords


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register(self, payload: RegisterRequest) -> UserOut:
        if self.users.get_by_email(str(payload.email)) is not None:
            raise ConflictError("An account with that email already exists")
        user = User(
            email=str(payload.email),
            # turn password to an Argon2 hash for database store
            password_hash=hash_password(payload.password),
        )
        try:
            # repo add the user to database session and flush it
            saved = self.users.add(user)
        except IntegrityError as exc:
            # The unique email constraint resolves concurrent registrations
            # like if two insert same email at the same time
            self.session.rollback()
            raise ConflictError(
                "An account with that email already exists"
            ) from exc
        return UserOut.model_validate(saved)

    def login(self, payload: LoginRequest) -> TokenOut:
        email = str(payload.email)
        if too_many_attempts(email):
            raise AppError(
                "Too many sign-in attempts. Try again later.",
                status_code=429,
            )
        user = self.users.get_by_email(email) #database lookup by email
        if user is None or not verify_password(
            payload.password,
            user.password_hash,
        ):
            record_failure(email)
            # Use one response for unknown email and wrong password.
            raise AuthenticationError("Invalid email or password")
        clear_attempts(email)
        return TokenOut(
            access_token=create_access_token(user.id), #create the access token
            # token expire time in seconds
            expires_in=settings.jwt_access_token_minutes * 60,
        )

    def export_account(self, user: User) -> dict[str, object]:
        portfolios = self.session.scalars(
            select(Portfolio).where(Portfolio.user_id == user.id)
        ).all()
        books: list[dict[str, object]] = []
        for portfolio in portfolios:
            fills = self.session.scalars(
                select(Transaction).where(
                    Transaction.portfolio_id == portfolio.id,
                    Transaction.voided_at.is_(None),
                )
            ).all()
            cash = self.session.scalars(
                select(CashMovement).where(
                    CashMovement.portfolio_id == portfolio.id
                )
            ).all()
            goals = self.session.scalars(
                select(Goal).where(Goal.portfolio_id == portfolio.id)
            ).all()
            notes = self.session.scalars(
                select(JournalEntry).where(
                    JournalEntry.portfolio_id == portfolio.id
                )
            ).all()
            books.append(
                {
                    "name": portfolio.name,
                    "description": portfolio.description,
                    "is_paper": portfolio.is_paper,
                    "transactions": [
                        {
                            "type": row.transaction_type,
                            "quantity": format(row.quantity, "f"),
                            "price": format(row.price, "f"),
                            "timestamp": row.timestamp.isoformat(),
                        }
                        for row in fills
                    ],
                    "cash": [
                        {
                            "kind": row.kind,
                            "amount": format(row.amount, "f"),
                            "currency": row.currency,
                            "timestamp": row.timestamp.isoformat(),
                        }
                        for row in cash
                    ],
                    "goals": [
                        {
                            "name": row.name,
                            "target_amount": format(row.target_amount, "f"),
                            "target_date": row.target_date.isoformat(),
                        }
                        for row in goals
                    ],
                    "journal": [
                        {"ticker": row.ticker, "note": row.note}
                        for row in notes
                    ],
                }
            )
        return {"email": user.email, "portfolios": books}

    def export_account_pdf(
        self,
        user: User,
        *,
        positions: PositionService,
        analytics: AnalyticsService,
    ) -> bytes:
        portfolios = self.session.scalars(
            select(Portfolio)
            .where(Portfolio.user_id == user.id)
            .order_by(Portfolio.created_at, Portfolio.name)
        ).all()
        records = BookRecords(self.session, user.id, positions.quotes)
        books: list[dict[str, object]] = []
        for portfolio in portfolios:
            book: dict[str, object] = {
                "name": portfolio.name,
                "description": portfolio.description,
                "is_paper": portfolio.is_paper,
                "positions": positions.list_positions(portfolio.id),
                "goals": records.list_goals(portfolio.id),
                "analytics": None,
                "analytics_note": None,
            }
            try:
                book["analytics"] = analytics.get_analytics(portfolio.id)
            except AppError as exc:
                book["analytics_note"] = exc.message
            books.append(book)
        return render_account_pdf(email=user.email, books=books)

    def delete_account(self, user: User) -> None:
        self.session.delete(user)
        self.session.flush()
