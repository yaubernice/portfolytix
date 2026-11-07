from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, get_quote_store
from app.db.models import User
from app.quotes.store import QuoteStore
from app.schemas.planning import (
    BehaviorOut,
    ContributionOut,
    GoalCreate,
    GoalOut,
    JournalCreate,
    JournalOut,
    LookThroughOut,
    SharedBookOut,
    ShareLinkOut,
)
from app.services.records import BookRecords

router = APIRouter(tags=["planning"])


def _records(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    quotes: QuoteStore = Depends(get_quote_store),
) -> BookRecords:
    return BookRecords(db, current_user.id, quotes)


@router.get("/portfolios/{portfolio_id}/goals", response_model=list[GoalOut])
def list_goals(
    portfolio_id: UUID,
    service: BookRecords = Depends(_records),
) -> list[GoalOut]:
    return service.list_goals(portfolio_id)


@router.post(
    "/portfolios/{portfolio_id}/goals",
    response_model=GoalOut,
    status_code=status.HTTP_201_CREATED,
)
def add_goal(
    portfolio_id: UUID,
    payload: GoalCreate,
    service: BookRecords = Depends(_records),
) -> GoalOut:
    return service.add_goal(portfolio_id, payload)


@router.delete(
    "/portfolios/{portfolio_id}/goals/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_goal(
    portfolio_id: UUID,
    goal_id: UUID,
    service: BookRecords = Depends(_records),
) -> Response:
    service.delete_goal(portfolio_id, goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/portfolios/{portfolio_id}/contribution",
    response_model=ContributionOut,
)
def contribution(
    portfolio_id: UUID,
    monthly: Decimal = Query(gt=0),
    months: int = Query(ge=1, le=600),
    service: BookRecords = Depends(_records),
) -> ContributionOut:
    return service.contribution(portfolio_id, monthly, months)


@router.get(
    "/portfolios/{portfolio_id}/look-through",
    response_model=LookThroughOut,
)
def look_through(
    portfolio_id: UUID,
    service: BookRecords = Depends(_records),
) -> LookThroughOut:
    return service.look_through(portfolio_id)


@router.post(
    "/portfolios/{portfolio_id}/look-through/refresh",
    response_model=LookThroughOut,
)
def refresh_look_through(
    portfolio_id: UUID,
    service: BookRecords = Depends(_records),
) -> LookThroughOut:
    return service.refresh_constituents(portfolio_id)


@router.get(
    "/portfolios/{portfolio_id}/behavior",
    response_model=BehaviorOut,
)
def behavior(
    portfolio_id: UUID,
    service: BookRecords = Depends(_records),
) -> BehaviorOut:
    return service.behavior(portfolio_id)


@router.post(
    "/portfolios/{portfolio_id}/journal",
    response_model=JournalOut,
    status_code=status.HTTP_201_CREATED,
)
def add_journal(
    portfolio_id: UUID,
    payload: JournalCreate,
    service: BookRecords = Depends(_records),
) -> JournalOut:
    return service.add_note(portfolio_id, payload)


@router.get("/portfolios/{portfolio_id}/income-events")
def income_events(
    portfolio_id: UUID,
    service: BookRecords = Depends(_records),
) -> list[dict[str, object]]:
    return service.income_events(portfolio_id)


@router.post(
    "/portfolios/{portfolio_id}/share",
    response_model=ShareLinkOut,
    status_code=status.HTTP_201_CREATED,
)
def create_share(
    portfolio_id: UUID,
    service: BookRecords = Depends(_records),
) -> ShareLinkOut:
    return service.create_share(portfolio_id)


@router.get("/shared/{token}", response_model=SharedBookOut)
def shared_book(
    token: str,
    db: Session = Depends(get_db),
    quotes: QuoteStore = Depends(get_quote_store),
) -> SharedBookOut:
    return BookRecords(db, UUID(int=0), quotes).shared_book(token)
