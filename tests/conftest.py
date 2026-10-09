"""Tests own their databases and Redis namespace; application credentials are ignored."""

import os
import secrets
import tempfile
from unittest.mock import patch

import fakeredis
import pytest

_test_directory = tempfile.TemporaryDirectory(prefix="stockapi-tests-")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{_test_directory.name}/accounts.sqlite"
)
os.environ["DATABASE_MIGRATION_URL"] = os.environ["DATABASE_URL"]
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
os.environ["REDIS_KEY_PREFIX"] = "stockapi-test-" + secrets.token_hex(4)
os.environ.setdefault("POLARS_MAX_THREADS", "2")


@pytest.fixture(scope="session", autouse=True)
def test_backing_services():
    from alembic import command
    from alembic.config import Config

    from app.core.config import PROJECT_ROOT
    from app.core.security import hash_api_key
    from app.dependencies.core import get_redis
    from database import SessionLocal
    from models import User

    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    with SessionLocal() as session, session.begin():
        session.add_all(
            [
                User(
                    username="test-free",
                    api_key_hash=hash_api_key("free-key-123"),
                    subscription="free",
                ),
                User(
                    username="test-pro",
                    api_key_hash=hash_api_key("pro-key-456"),
                    subscription="pro",
                ),
                User(
                    username="test-premium",
                    api_key_hash=hash_api_key("premium-key-789"),
                    subscription="premium",
                ),
            ]
        )
    if "TEST_REDIS_URL" in os.environ:
        yield
    else:
        fake = fakeredis.FakeRedis(decode_responses=True)
        with patch("redis.Redis.from_url", return_value=fake):
            get_redis.cache_clear()
            yield
        get_redis.cache_clear()
    _test_directory.cleanup()


@pytest.fixture(autouse=True)
def isolate_redis(test_backing_services):
    from app.core.config import settings
    from app.dependencies.core import get_redis

    client = get_redis()

    def clear():
        keys = list(client.scan_iter(match=f"{settings.REDIS_KEY_PREFIX}:*"))
        if keys:
            client.delete(*keys)

    clear()
    yield
    clear()
