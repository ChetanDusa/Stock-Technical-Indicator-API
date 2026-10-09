"""UTC daily quotas: check, increment and expiry in one Redis Lua operation."""

import datetime

import redis

from app.core.config import settings
from app.core.exceptions import (
    AccessDeniedException,
    DependencyUnavailableException,
    RateLimitExceededException,
)
from app.core.tiers import TIER_LIMITS
from models import User

_CONSUME_QUOTA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current > 0 then redis.call('EXPIREAT', KEYS[1], ARGV[2]) end
local limit = tonumber(ARGV[1])
if limit > 0 and current >= limit then return -1 end
local count = redis.call('INCR', KEYS[1])
redis.call('EXPIREAT', KEYS[1], ARGV[2])
return count
"""


def quota_key(user_id: int, day: datetime.date | None = None) -> str:
    day = day or datetime.datetime.now(datetime.timezone.utc).date()
    return f"{settings.REDIS_KEY_PREFIX}:quota:{user_id}:{day.isoformat()}"


class RateLimiter:
    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def enforce_rate_limit(self, user: User) -> None:
        tier_info = TIER_LIMITS.get(user.subscription)
        if tier_info is None:
            raise AccessDeniedException("Invalid subscription tier")
        now = datetime.datetime.now(datetime.timezone.utc)
        midnight = datetime.datetime.combine(
            now.date() + datetime.timedelta(days=1), datetime.time.min, tzinfo=datetime.timezone.utc
        )
        limit = tier_info["max_requests"]
        try:
            count = self.redis.eval(
                _CONSUME_QUOTA,
                1,
                quota_key(user.id, now.date()),
                0 if limit == float("inf") else limit,
                int(midnight.timestamp()),
            )
        except redis.RedisError as exc:
            raise DependencyUnavailableException("Quota service unavailable") from exc
        if count == -1:
            raise RateLimitExceededException(
                retry_after=max(1, int((midnight - now).total_seconds()))
            )

    def get_usage(self, user: User) -> int:
        try:
            return int(self.redis.get(quota_key(user.id)) or 0)
        except redis.RedisError as exc:
            raise DependencyUnavailableException("Quota service unavailable") from exc
