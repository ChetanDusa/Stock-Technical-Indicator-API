"""Process health, dependency readiness, dataset metadata and authenticated usage."""

import datetime
from typing import Any, Literal

import redis
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.metrics import metrics
from app.core.tiers import TIER_LIMITS
from app.dependencies.auth import get_current_user
from app.dependencies.core import get_rate_limiter, get_redis, get_stock_repository
from app.dependencies.database import get_db
from app.repositories.stock_repository import StockDataRepository
from app.schemas.responses import StatusResponse
from app.services.rate_limiter import RateLimiter
from models import User

logger = get_logger("app.health")
router = APIRouter(tags=["System"])


@router.get("/")
def home() -> dict[str, str]:
    return {"message": "Welcome to the Stock Technical Indicator API"}


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness: does not call backing services."""
    return {"status": "ok"}


@router.get("/ready")
def readiness_check(
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
    stock_repo: StockDataRepository = Depends(get_stock_repository),
) -> Response:
    """Bounded DB/Redis checks; the dataset is validated during startup."""
    dependencies = {"dataset": "ok" if not stock_repo.get_all_data().is_empty() else "unhealthy"}
    try:
        db.execute(select(User).limit(1))
        dependencies["database"] = "ok"
    except Exception as exc:
        logger.warning("Database readiness failed: %s", type(exc).__name__)
        dependencies["database"] = "unhealthy"
    try:
        dependencies["redis"] = "ok" if redis_client.ping() else "unhealthy"
    except Exception as exc:
        logger.warning("Redis readiness failed: %s", type(exc).__name__)
        dependencies["redis"] = "unhealthy"
    ready = all(value == "ok" for value in dependencies.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "unhealthy", "dependencies": dependencies},
    )


@router.get("/dataset")
def dataset_metadata(
    stock_repo: StockDataRepository = Depends(get_stock_repository),
) -> dict[str, Any]:
    """Public snapshot metadata makes the historical data boundary explicit."""
    return {
        "mode": "historical",
        "start_date": stock_repo.start_date.isoformat(),
        "end_date": stock_repo.end_date.isoformat(),
        "rows": stock_repo.get_all_data().height,
        "symbol_count": len(stock_repo.get_symbols()),
        "dataset_version": stock_repo.cache_version,
    }


@router.get("/symbols")
def symbols(stock_repo: StockDataRepository = Depends(get_stock_repository)) -> list[str]:
    return stock_repo.get_symbols()


@router.get("/metrics")
def get_application_metrics(
    format: Literal["json", "prometheus"] = "json",
    user: User = Depends(get_current_user),
) -> Response:
    """Per-process metrics; authentication does not consume analytical quota."""
    if format == "prometheus":
        return PlainTextResponse(
            metrics.to_prometheus_text(), media_type="text/plain; version=0.0.4"
        )
    return JSONResponse(metrics.get_summary())


@router.get("/status", response_model=StatusResponse)
def get_status(
    user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> dict[str, Any]:
    """Report the same Redis counter used by quota enforcement."""
    count = rate_limiter.get_usage(user)
    maximum = TIER_LIMITS[user.subscription]["max_requests"]
    unlimited = maximum == float("inf")
    return {
        "username": user.username,
        "subscription": user.subscription,
        "requests_today": count,
        "max_requests_per_day": "unlimited" if unlimited else str(int(maximum)),
        "requests_remaining": "unlimited" if unlimited else str(max(0, int(maximum) - count)),
        "last_request_date": (
            datetime.datetime.now(datetime.timezone.utc).date().isoformat() if count else ""
        ),
    }
