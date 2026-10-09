import threading

import fakeredis
import pytest

from app.cache.redis_cache import RedisCache
from app.core.exceptions import RateLimitExceededException
from app.services.rate_limiter import RateLimiter, quota_key
from models import User


@pytest.fixture
def fake_redis_client():
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_redis_cache(fake_redis_client):
    cache = RedisCache(fake_redis_client)

    # Miss
    assert cache.get("key1") is None

    # Set
    data = [{"date": "2023-01-01", "val": 1.23}]
    cache.set("key1", data, ttl=10)

    # Hit
    assert cache.get("key1") == data

    # TTL
    ttl = fake_redis_client.ttl("key1")
    assert ttl > 0 and ttl <= 10


def test_rate_limiter_concurrency(fake_redis_client):
    """
    Simulate concurrent requests to test atomic INCR enforcement.
    Free tier limit is 50 (TIER_LIMITS["free"]["max_requests"]).
    Launch 60 threads — exactly 50 should succeed, 10 should be rejected.
    """
    limiter = RateLimiter(fake_redis_client)

    user = User(
        id=1,
        username="testuser",
        api_key_hash="test-hash",
        subscription="free",
    )

    successes = 0
    exceptions = 0
    lock = threading.Lock()

    def worker():
        nonlocal successes, exceptions
        try:
            limiter.enforce_rate_limit(user)
            with lock:
                successes += 1
        except RateLimitExceededException:
            with lock:
                exceptions += 1

    threads = []
    # Launch 60 concurrent requests against a quota of 50
    for _ in range(60):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Exactly 50 should succeed; 10 should be rejected
    assert successes == 50
    assert exceptions == 10

    # Verify TTL is set on the rate-limit key
    key = quota_key(1)
    assert fake_redis_client.ttl(key) > 0
