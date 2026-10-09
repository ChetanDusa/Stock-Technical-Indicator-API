"""Indicator endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import get_authorized_user
from app.dependencies.core import get_access_service, get_indicator_service
from app.schemas.requests import (
    BollingerParams,
    EmaParams,
    MacdParams,
    RsiParams,
    SmaParams,
)
from app.services.access_service import AccessService
from app.services.indicator_service import IndicatorService
from models import User

router = APIRouter(tags=["Indicators"])


@router.get("/sma")
def get_sma(
    params: Annotated[SmaParams, Query()],
    user: User = Depends(get_authorized_user),
    access_service: AccessService = Depends(get_access_service),
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> List[Dict[str, Any]]:
    access_service.check_access(user, "sma", params.start, params.end)
    return indicator_service.compute_indicator(
        "sma",
        params.symbol,
        params.start,
        params.end,
        {"window": params.window},
    )


@router.get("/ema")
def get_ema(
    params: Annotated[EmaParams, Query()],
    user: User = Depends(get_authorized_user),
    access_service: AccessService = Depends(get_access_service),
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> List[Dict[str, Any]]:
    access_service.check_access(user, "ema", params.start, params.end)
    return indicator_service.compute_indicator(
        "ema",
        params.symbol,
        params.start,
        params.end,
        {"span": params.span},
    )


@router.get("/rsi")
def get_rsi(
    params: Annotated[RsiParams, Query()],
    user: User = Depends(get_authorized_user),
    access_service: AccessService = Depends(get_access_service),
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> List[Dict[str, Any]]:
    access_service.check_access(user, "rsi", params.start, params.end)
    return indicator_service.compute_indicator(
        "rsi",
        params.symbol,
        params.start,
        params.end,
        {"period": params.period},
    )


@router.get("/macd")
def get_macd(
    params: Annotated[MacdParams, Query()],
    user: User = Depends(get_authorized_user),
    access_service: AccessService = Depends(get_access_service),
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> List[Dict[str, Any]]:
    access_service.check_access(user, "macd", params.start, params.end)
    return indicator_service.compute_indicator(
        "macd",
        params.symbol,
        params.start,
        params.end,
        {"fast": params.fast, "slow": params.slow, "signal": params.signal},
    )


@router.get("/bollinger")
def get_bollinger(
    params: Annotated[BollingerParams, Query()],
    user: User = Depends(get_authorized_user),
    access_service: AccessService = Depends(get_access_service),
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> List[Dict[str, Any]]:
    access_service.check_access(user, "bollinger", params.start, params.end)
    return indicator_service.compute_indicator(
        "bollinger",
        params.symbol,
        params.start,
        params.end,
        {"period": params.period, "std_multiplier": params.std_multiplier},
    )
