from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_ledger_service
from app.schemas.ledger import CashCreate, CashOut, SplitCreate, SplitOut
from app.services.ledger_service import LedgerService

router = APIRouter(prefix="/portfolios/{portfolio_id}", tags=["ledger"])


@router.get("/cash", response_model=list[CashOut])
def list_cash(
    portfolio_id: UUID,
    service: LedgerService = Depends(get_ledger_service),
) -> list[CashOut]:
    return service.list_cash(portfolio_id)


@router.post("/cash", response_model=CashOut, status_code=status.HTTP_201_CREATED)
def add_cash(
    portfolio_id: UUID,
    payload: CashCreate,
    service: LedgerService = Depends(get_ledger_service),
) -> CashOut:
    return service.add_cash(portfolio_id, payload)


@router.delete("/cash/{movement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cash(
    portfolio_id: UUID,
    movement_id: UUID,
    service: LedgerService = Depends(get_ledger_service),
) -> Response:
    service.delete_cash(portfolio_id, movement_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/splits", response_model=list[SplitOut])
def list_splits(
    portfolio_id: UUID,
    service: LedgerService = Depends(get_ledger_service),
) -> list[SplitOut]:
    return service.list_splits(portfolio_id)


@router.post("/splits", response_model=SplitOut, status_code=status.HTTP_201_CREATED)
def add_split(
    portfolio_id: UUID,
    payload: SplitCreate,
    service: LedgerService = Depends(get_ledger_service),
) -> SplitOut:
    return service.add_split(portfolio_id, payload)


@router.delete("/splits/{split_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_split(
    portfolio_id: UUID,
    split_id: UUID,
    service: LedgerService = Depends(get_ledger_service),
) -> Response:
    service.delete_split(portfolio_id, split_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
