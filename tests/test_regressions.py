"""Regression coverage for calculation boundaries, input validation and deployment behavior."""

import datetime
import statistics
import sys
from unittest.mock import patch

import polars as pl
import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.exceptions import AccessDeniedException
from app.core.metrics import metrics
from app.dependencies.core import get_redis
from app.main import app
from app.schemas.screening import ScreeningCondition
from app.services.rate_limiter import RateLimiter, quota_key
from app.services.screening_engine import ScreeningEngine
from database import SessionLocal, build_engine
from indicators import bollinger_bands, ema, macd, rsi
from models import User

client = TestClient(app)
HEADERS = {"api-key": "premium-key-789"}
PARAMS = {"symbol": "INFY", "start": "2025-04-01", "end": "2025-06-30"}


@pytest.mark.parametrize("name", ["sma", "ema", "rsi", "macd", "bollinger"])
def test_indicator_values_do_not_depend_on_output_start(name):
    full = client.get(f"/{name}", params={**PARAMS, "start": "2025-01-01"}, headers=HEADERS)
    narrow = client.get(f"/{name}", params={**PARAMS, "start": "2025-06-15"}, headers=HEADERS)
    assert full.status_code == narrow.status_code == 200
    expected = [row for row in full.json() if row["date"] >= "2025-06-15"]
    assert expected
    assert narrow.json() == expected


def test_cached_and_uncached_dates_are_identical():
    cold = client.get("/sma", params=PARAMS, headers=HEADERS)
    warm = client.get("/sma", params=PARAMS, headers=HEADERS)
    assert cold.status_code == warm.status_code == 200
    assert cold.json() == warm.json()
    for row in cold.json():
        datetime.date.fromisoformat(row["date"])


def test_status_uses_the_enforced_redis_count():
    headers = {"api-key": "free-key-123"}
    assert client.get("/sma", params=PARAMS, headers=headers).status_code == 200
    assert client.get("/sma", params=PARAMS, headers=headers).status_code == 200
    for _ in range(2):
        status = client.get("/status", headers=headers).json()
        assert status["requests_today"] == 2
        assert status["requests_remaining"] == "48"


@pytest.mark.parametrize(
    "path,extra",
    [
        ("/macd", {"fast": 26, "slow": 12}),
        ("/bollinger", {"period": 1}),
        ("/sma", {"window": 0}),
        ("/ema", {"span": 1000000}),
        ("/bollinger", {"std_multiplier": "inf"}),
    ],
)
def test_invalid_indicator_parameters_return_422(path, extra):
    assert client.get(path, params={**PARAMS, **extra}, headers=HEADERS).status_code == 422


@pytest.mark.parametrize(
    "condition",
    [
        {"indicator": "SMA", "period": [], "operator": ">", "value": 0},
        {"indicator": "SMA", "period": "abc", "operator": ">", "value": 0},
        {"indicator": "MACD", "component": "unknown", "operator": ">", "value": 0},
        {"indicator": "BOLLINGER", "period": 20, "band": "unknown", "operator": ">", "value": 0},
        {"indicator": "PRICE", "operator": ">", "value": 0, "unexpected": True},
        {"indicator": "PRICE", "operator": ">", "reference": {"indicator": "SMA", "period": []}},
    ],
)
def test_malformed_screening_is_rejected_before_computation(condition):
    assert (
        client.post("/screen", json={"conditions": [condition]}, headers=HEADERS).status_code == 422
    )


def test_screening_condition_limit():
    condition = {"indicator": "PRICE", "operator": ">", "value": 0}
    assert (
        client.post("/screen", json={"conditions": [condition] * 11}, headers=HEADERS).status_code
        == 422
    )


def test_quota_backend_failure_is_503_for_premium_too():
    with patch.object(get_redis(), "eval", side_effect=redis.ConnectionError("unavailable")):
        response = client.get("/sma", params=PARAMS, headers=HEADERS)
    assert response.status_code == 503
    assert response.json() == {"detail": "Quota service unavailable"}


def test_account_backend_failure_is_503():
    with patch(
        "sqlalchemy.orm.Session.scalar",
        side_effect=OperationalError("SELECT", {}, Exception("database")),
    ):
        response = client.get("/sma", params=PARAMS, headers=HEADERS)
    assert response.status_code == 503
    assert response.json() == {"detail": "Account service unavailable"}


def test_unknown_tier_never_bypasses_quota():
    with pytest.raises(AccessDeniedException):
        RateLimiter(get_redis()).enforce_rate_limit(User(id=999, subscription="unknown"))


def test_quota_expiry_is_utc_midnight():
    now = datetime.datetime.now(datetime.timezone.utc)
    reset = datetime.datetime.combine(
        now.date() + datetime.timedelta(days=1), datetime.time.min, tzinfo=datetime.timezone.utc
    )
    RateLimiter(get_redis()).enforce_rate_limit(User(id=998, subscription="free"))
    ttl = get_redis().ttl(quota_key(998))
    assert abs(ttl - int((reset - now).total_seconds())) <= 2


def test_metrics_requires_authentication():
    assert client.get("/metrics").status_code == 401


def test_metric_paths_are_bounded_for_unknown_routes():
    for index in range(10):
        assert client.get(f"/unknown-{index}").status_code == 404
    paths = {item["path"] for item in metrics.get_summary()["requests_by_endpoint"]}
    assert not any(path.startswith("/unknown-") for path in paths)
    assert "__unmatched__" in paths


def test_openapi_exposes_api_key_authorization():
    schema = client.get("/openapi.json").json()
    scheme = schema["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "api-key"


def test_snapshot_metadata_and_symbol_catalog():
    dataset = client.get("/dataset").json()
    assert dataset["rows"] == 830955
    assert dataset["symbol_count"] == 1168
    assert dataset["end_date"] == "2025-06-30"
    assert "INFY" in client.get("/symbols").json()


def test_neon_url_preserves_tls_and_uses_bounded_pool():
    connection = build_engine(
        "postgresql://user:encoded%40password@ep-example-pooler.aws.neon.tech/db?channel_binding=require"
    )
    try:
        assert connection.url.drivername == "postgresql+psycopg2"
        assert connection.url.query["sslmode"] == "require"
        assert connection.url.password == "encoded@password"
        assert connection.url.query["channel_binding"] == "require"
        assert connection.pool.size() == 5
        assert connection.pool._max_overflow == 0
    finally:
        connection.dispose()


def _ewm(values, span):
    decay = 1 - 2 / (span + 1)
    return [
        sum(value * decay ** (end - index) for index, value in enumerate(values[: end + 1]))
        / sum(decay ** (end - index) for index in range(end + 1))
        for end in range(len(values))
    ]


def test_ema_and_macd_against_independent_arithmetic():
    values = [10.0, 14.0, 12.0, 15.0, 11.0, 18.0]
    frame = pl.DataFrame({"close": values})
    assert ema(frame, span=3)["EMA_3"].to_list() == pytest.approx(_ewm(values, 3))
    fast, slow = _ewm(values, 2), _ewm(values, 4)
    line = [a - b for a, b in zip(fast, slow)]
    signal = _ewm(line, 3)
    result = macd(frame, fast=2, slow=4, signal=3)
    assert result["MACD"].to_list() == pytest.approx(line)
    assert result["MACD_Signal"].to_list() == pytest.approx(signal)


@pytest.mark.parametrize(
    "values,expected",
    [
        ([10.0, 11.0, 12.0, 13.0], 100.0),
        ([13.0, 12.0, 11.0, 10.0], 0.0),
        ([10.0, 10.0, 10.0, 10.0], 50.0),
        ([10.0, 14.0, 12.0, 15.0], 100.0 * 7.0 / 9.0),
    ],
)
def test_cutler_rsi_warmup_and_zero_loss(values, expected):
    result = rsi(pl.DataFrame({"close": values}), period=3)["RSI_3"].to_list()
    assert result[:3] == [None, None, None]
    assert result[3] == pytest.approx(expected)


def test_rsi_is_consistent_between_screening_and_single_symbol():
    frame = pl.DataFrame(
        {
            "symbol": ["A"] * 4 + ["B"] * 4,
            "date": list(range(4)) * 2,
            "close": [10.0, 14.0, 12.0, 15.0, 15.0, 12.0, 14.0, 10.0],
        }
    )
    condition = ScreeningCondition(indicator="RSI", period=3, operator=">", value=70)
    assert ScreeningEngine().evaluate(frame, [condition]) == ["A"]


def test_bollinger_uses_sample_standard_deviation():
    values = [10.0, 14.0, 12.0]
    result = bollinger_bands(pl.DataFrame({"close": values}), period=3)
    assert result["BB_Mid_3"][-1] == statistics.mean(values)
    assert result["BB_Upper_3"][-1] == pytest.approx(
        statistics.mean(values) + 2 * statistics.stdev(values)
    )


def test_database_rejects_invalid_subscription():
    with SessionLocal() as session:
        session.add(User(username="invalid-tier", api_key_hash="x" * 64, subscription="unknown"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_account_creation_rotation_and_revocation(monkeypatch, capsys):
    from scripts.manage_users import main

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["manage_users", *args])
        main()
        return capsys.readouterr().out

    created = run("create", "--username", "lifecycle-test", "--tier", "premium")
    first_key = created.strip().split(": ")[-1]
    assert first_key.startswith("stk_")
    with SessionLocal() as session:
        stored = session.scalar(select(User).where(User.username == "lifecycle-test"))
        assert stored.api_key_hash != first_key
        assert len(stored.api_key_hash) == 64
    assert client.get("/status", headers={"api-key": first_key}).status_code == 200
    rotated = run("rotate", "--username", "lifecycle-test")
    next_key = rotated.strip().split(": ")[-1]
    assert client.get("/status", headers={"api-key": first_key}).status_code == 401
    assert client.get("/status", headers={"api-key": next_key}).status_code == 200
    run("revoke", "--username", "lifecycle-test")
    assert client.get("/status", headers={"api-key": next_key}).status_code == 401


def test_screening_reuses_macd_components_across_multiple_conditions():
    frame = pl.DataFrame(
        {
            "symbol": ["UP"] * 20 + ["DOWN"] * 20,
            "date": list(range(20)) * 2,
            "close": [float(i) for i in range(20)] + [float(20 - i) for i in range(20)],
        }
    )
    shared = {"indicator": "MACD", "fast": 3, "slow": 6, "signal_period": 3}
    conditions = [
        ScreeningCondition(**shared, operator=">", reference={**shared, "component": "signal"}),
        ScreeningCondition(**shared, component="hist", operator=">", value=0),
        ScreeningCondition(**shared, operator=">", value=0),
    ]
    assert ScreeningEngine().evaluate(frame, conditions) == ["UP"]
