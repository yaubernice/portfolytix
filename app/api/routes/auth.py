from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import (
    get_analytics_service,
    get_auth_service,
    get_current_user,
    get_position_service,
)
from app.db.models import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.position_service import PositionService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    return service.register(payload)


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    return service.login(payload)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get("/export")
def export_account(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
    positions: PositionService = Depends(get_position_service),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> Response:
    pdf = service.export_account_pdf(
        current_user,
        positions=positions,
        analytics=analytics,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="portfolytix-report.pdf"',
        },
    )


@router.get("/export.json")
def export_account_json(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, object]:
    return service.export_account(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.delete_account(current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
