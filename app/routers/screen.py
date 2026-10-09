"""Stock screening router."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies.auth import get_authorized_user
from app.dependencies.core import get_screening_service
from app.schemas.screening import ScreeningRequest, ScreeningResponse
from app.services.screening_service import ScreeningService
from models import User

router = APIRouter(tags=["Screening"])


@router.post("/screen", response_model=ScreeningResponse)
def screen_stocks(
    request: ScreeningRequest,
    user: User = Depends(get_authorized_user),
    screening_service: ScreeningService = Depends(get_screening_service),
) -> ScreeningResponse:
    """Evaluate technical conditions across all symbols and return matching stocks."""
    return screening_service.screen(
        conditions=request.conditions,
        logic=request.logic,
        user=user,
    )
