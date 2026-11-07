from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_portfolio_service
from app.schemas.transaction import (
    TransactionCreate,
    TransactionImport,
    TransactionOut,
    TransactionUpdate,
)
from app.services.portfolio_service import PortfolioService

router = APIRouter(
    prefix="/portfolios/{portfolio_id}/transactions",
    tags=["transactions"],
)


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(
    portfolio_id: UUID,
    payload: TransactionCreate,
    service: PortfolioService = Depends(get_portfolio_service),
) -> TransactionOut:
    return service.add_transaction(portfolio_id, payload)


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    portfolio_id: UUID,
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[TransactionOut]:
    return service.list_transactions(portfolio_id)


@router.post("/import", response_model=list[TransactionOut], status_code=201)
def import_transactions(
    portfolio_id: UUID,
    payload: TransactionImport,
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[TransactionOut]:
    return service.import_transactions(portfolio_id, payload)


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    payload: TransactionUpdate,
    service: PortfolioService = Depends(get_portfolio_service),
) -> TransactionOut:
    return service.update_transaction(portfolio_id, transaction_id, payload)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    service: PortfolioService = Depends(get_portfolio_service),
) -> Response:
    service.delete_transaction(portfolio_id, transaction_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
