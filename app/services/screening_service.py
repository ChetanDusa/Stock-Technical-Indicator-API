"""Authorized screening with shared, snapshot-versioned caching and bounded cold computations."""

import hashlib
import json
import threading

from app.cache.interface import CacheInterface
from app.core.config import settings
from app.core.exceptions import ServiceBusyException
from app.core.metrics import metrics
from app.repositories.stock_repository import StockDataRepository
from app.schemas.screening import ScreeningCondition, ScreeningResponse
from app.services.access_service import AccessService
from app.services.screening_engine import ScreeningEngine
from models import User

_screening_slots = threading.BoundedSemaphore(settings.SCREENING_MAX_CONCURRENCY)


class ScreeningService:
    def __init__(
        self,
        stock_repo: StockDataRepository,
        cache: CacheInterface,
        access_service: AccessService,
        engine: ScreeningEngine | None = None,
    ) -> None:
        self.stock_repo = stock_repo
        self.cache = cache
        self.access_service = access_service
        self.engine = engine or ScreeningEngine()

    @staticmethod
    def generate_cache_key(conditions: list[ScreeningCondition], logic: str) -> str:
        payload = {
            "logic": logic.upper(),
            "conditions": [condition.model_dump(mode="json") for condition in conditions],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return f"screen:v3:{digest}"

    def screen(
        self, conditions: list[ScreeningCondition], logic: str, user: User
    ) -> ScreeningResponse:
        # Authorization must precede shared cache lookup.
        self.access_service.check_screening_access(user, conditions)
        key = (
            f"{settings.REDIS_KEY_PREFIX}:{self.stock_repo.cache_version}:"
            + self.generate_cache_key(conditions, logic)
        )
        cached = self.cache.get(key)
        if cached is not None:
            metrics.record_cache_hit()
            return ScreeningResponse(**cached)
        metrics.record_cache_miss()

        if not _screening_slots.acquire(blocking=False):
            raise ServiceBusyException("Screening is busy; retry shortly")
        try:
            frame = self.stock_repo.get_all_data().select("symbol", "date", "close")
            matches = self.engine.evaluate(frame, conditions, logic)
        finally:
            _screening_slots.release()

        response = ScreeningResponse(
            matched_symbols=matches, count=len(matches), conditions_evaluated=len(conditions)
        )
        self.cache.set(key, response.model_dump(), ttl=settings.CACHE_DEFAULT_TTL)
        return response
