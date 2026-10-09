"""Factories: one dataset and Redis pool per process, one DB session per request."""

from functools import lru_cache

import redis
from fastapi import Depends
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy.orm import Session

from app.cache.interface import CacheInterface
from app.cache.redis_cache import RedisCache
from app.core.config import settings
from app.dependencies.database import get_db
from app.repositories.stock_repository import StockDataRepository
from app.repositories.user_repository import UserRepository
from app.services.access_service import AccessService
from app.services.indicator_service import IndicatorService
from app.services.rate_limiter import RateLimiter
from app.services.screening_service import ScreeningService


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.DEPENDENCY_TIMEOUT_SECONDS,
        socket_timeout=settings.DEPENDENCY_TIMEOUT_SECONDS,
        health_check_interval=30,
        max_connections=30,
        # Retrying a timed-out quota write could count the same attempt twice.
        retry=Retry(NoBackoff(), 0),
    )


@lru_cache
def get_stock_repository() -> StockDataRepository:
    return StockDataRepository()


def get_cache(redis_client: redis.Redis = Depends(get_redis)) -> CacheInterface:
    return RedisCache(redis_client)


def get_rate_limiter(redis_client: redis.Redis = Depends(get_redis)) -> RateLimiter:
    return RateLimiter(redis_client)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_access_service(
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    stock_repo: StockDataRepository = Depends(get_stock_repository),
) -> AccessService:
    return AccessService(rate_limiter, stock_repo.end_date)


def get_indicator_service(
    stock_repo: StockDataRepository = Depends(get_stock_repository),
    cache: CacheInterface = Depends(get_cache),
) -> IndicatorService:
    return IndicatorService(stock_repo, cache)


def get_screening_service(
    stock_repo: StockDataRepository = Depends(get_stock_repository),
    cache: CacheInterface = Depends(get_cache),
    access_service: AccessService = Depends(get_access_service),
) -> ScreeningService:
    return ScreeningService(stock_repo, cache, access_service)
