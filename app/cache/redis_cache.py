"""JSON response cache. Cache failures allow recomputation; quota failures do not."""

import json
import logging
from typing import Any

import redis

from app.cache.interface import CacheInterface

logger = logging.getLogger(__name__)


class RedisCache(CacheInterface):
    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def get(self, key: str) -> Any | None:
        try:
            value = self.redis.get(key)
            return json.loads(value) if value is not None else None
        except (redis.RedisError, json.JSONDecodeError) as exc:
            logger.warning("Cache read unavailable: %s", type(exc).__name__)
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        try:
            self.redis.setex(key, ttl, json.dumps(value, allow_nan=False))
        except (redis.RedisError, TypeError, ValueError) as exc:
            logger.warning("Cache write unavailable: %s", type(exc).__name__)
