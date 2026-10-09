"""FastAPI assembly, resource lifecycle and centralized domain-error translation."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.exceptions import (
    AccessDeniedException,
    AuthenticationException,
    DependencyUnavailableException,
    InvalidDateRangeException,
    RateLimitExceededException,
    ServiceBusyException,
    SymbolNotFoundException,
)
from app.core.logging import get_logger, request_id_ctx, setup_logging
from app.dependencies.core import get_redis, get_stock_repository
from app.middleware.observability import ObservabilityMiddleware
from app.routers import health, indicators, screen
from database import engine
from models import User

setup_logging()
logger = get_logger("app.exceptions")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Load the snapshot before serving, verify dependencies and close pools on exit."""
    redis_client = get_redis()
    try:
        get_stock_repository()
        with engine.connect() as connection:
            connection.execute(select(User).limit(1))
        if not redis_client.ping():
            raise RuntimeError("Redis readiness check failed")
        yield
    finally:
        redis_client.close()
        engine.dispose()
        get_redis.cache_clear()
        get_stock_repository.cache_clear()


app = FastAPI(
    title="Stock Technical Indicator API",
    description=(
        "Historical OHLCV analytics: SMA, EMA, Cutler RSI, MACD, Bollinger Bands "
        "and stock screening. Inspect /dataset for snapshot coverage. "
        "Authenticate using the api-key header."
    ),
    version="3.0.0",
    lifespan=lifespan,
)
app.add_middleware(ObservabilityMiddleware)


def _request_headers(request: Request) -> dict[str, str]:
    request_id = getattr(request.state, "request_id", None) or request_id_ctx.get()
    return {"X-Request-ID": request_id} if request_id else {}


@app.exception_handler(SymbolNotFoundException)
async def symbol_not_found_handler(request: Request, exc: SymbolNotFoundException):
    return JSONResponse(
        status_code=404, content={"detail": "No data found"}, headers=_request_headers(request)
    )


@app.exception_handler(InvalidDateRangeException)
async def date_range_handler(request: Request, exc: InvalidDateRangeException):
    return JSONResponse(
        status_code=400, content={"detail": str(exc)}, headers=_request_headers(request)
    )


@app.exception_handler(AccessDeniedException)
async def access_denied_handler(request: Request, exc: AccessDeniedException):
    return JSONResponse(
        status_code=403, content={"detail": str(exc)}, headers=_request_headers(request)
    )


@app.exception_handler(RateLimitExceededException)
async def quota_handler(request: Request, exc: RateLimitExceededException):
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc)},
        headers={**_request_headers(request), "Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(AuthenticationException)
async def authentication_handler(request: Request, exc: AuthenticationException):
    return JSONResponse(
        status_code=401, content={"detail": str(exc)}, headers=_request_headers(request)
    )


@app.exception_handler(DependencyUnavailableException)
@app.exception_handler(ServiceBusyException)
async def unavailable_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={**_request_headers(request), "Retry-After": "5"},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.error("Unhandled application exception: %s", type(exc).__name__, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=_request_headers(request),
    )


app.include_router(health.router)
app.include_router(indicators.router)
app.include_router(screen.router)
