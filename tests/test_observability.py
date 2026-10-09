"""Tests for observability and dependency failure handling."""

import io
import json
import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.logging import StructuredJSONFormatter, sanitize_sensitive_data
from app.main import app

client = TestClient(app)


# =====================================================================
# 1. Request ID / Correlation ID Tests
# =====================================================================


def test_request_id_generated_when_missing():
    """Verify an X-Request-ID is generated and returned when not supplied."""
    response = client.get("/health")
    assert response.status_code == 200
    req_id = response.headers.get("X-Request-ID")
    assert req_id is not None
    assert len(req_id) > 10  # valid uuid string


def test_incoming_request_id_propagated():
    """Verify an incoming X-Request-ID is propagated through the response."""
    custom_id = "trace-client-12345-abcdef"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


def test_request_id_present_on_errors():
    """Verify error responses also contain the X-Request-ID header."""
    custom_id = "trace-err-999"
    # Calling unauthorized endpoint
    response = client.get(
        "/sma?symbol=INFY&start=2025-04-01&end=2025-04-30", headers={"X-Request-ID": custom_id}
    )
    assert response.headers.get("X-Request-ID") == custom_id


# =====================================================================
# 2. Structured Logging & Secret Sanitization Tests
# =====================================================================


def test_sensitive_data_sanitizer():
    """Verify sensitive URLs and tokens are masked."""
    raw_redis = "redis://:supersecretpass@localhost:6379/0"
    sanitized_redis = sanitize_sensitive_data(raw_redis)
    assert "supersecretpass" not in sanitized_redis
    assert "***" in sanitized_redis

    raw_pg = "postgresql://user:mypassword@db.host.internal:5432/stocks"
    sanitized_pg = sanitize_sensitive_data(raw_pg)
    assert "mypassword" not in sanitized_pg
    assert "***" in sanitized_pg

    raw_api_key = "query failed with api_key=secret-key-12345"
    sanitized_api = sanitize_sensitive_data(raw_api_key)
    assert "secret-key-12345" not in sanitized_api


def test_structured_json_formatter():
    """Verify JSONFormatter produces valid JSON containing expected fields."""
    formatter = StructuredJSONFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test event for redis://:secret@localhost:6379",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-test-456"
    record.method = "GET"
    record.path = "/test"
    record.status_code = 200
    record.latency_ms = 12.5

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["logger"] == "app.test"
    assert parsed["level"] == "INFO"
    assert parsed["request_id"] == "req-test-456"
    assert parsed["method"] == "GET"
    assert parsed["path"] == "/test"
    assert parsed["status_code"] == 200
    assert parsed["latency_ms"] == 12.5
    assert "secret" not in parsed["message"]


def test_request_logging_does_not_expose_api_key():
    """Verify API request logging does not output raw user API keys."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(StructuredJSONFormatter())
    req_logger = logging.getLogger("app.request")
    req_logger.addHandler(handler)

    try:
        api_key = "premium-key-789"
        response = client.get(
            "/sma?symbol=INFY&start=2025-04-01&end=2025-04-10&window=5",
            headers={"api-key": api_key},
        )
        assert response.status_code == 200
        logs = log_capture.getvalue()
        assert api_key not in logs
    finally:
        req_logger.removeHandler(handler)


# =====================================================================
# 3. Health, Readiness, and Dependency Failure Tests
# =====================================================================


def test_health_endpoint():
    """Liveness probe must return 200 without checking external dependencies."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint_success():
    """Readiness probe returns 200 when backing DB and Redis are reachable."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["database"] == "ok"
    assert data["dependencies"]["redis"] == "ok"


def test_readiness_endpoint_database_failure():
    """Readiness probe returns 503 when DB dependency check fails."""
    with patch("sqlalchemy.orm.Session.execute", side_effect=Exception("DB connection refused")):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["dependencies"]["database"] == "unhealthy"


def test_readiness_endpoint_redis_failure():
    """Readiness probe returns 503 when Redis dependency check fails."""
    with patch("redis.Redis.ping", side_effect=Exception("Redis timeout")):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["dependencies"]["redis"] == "unhealthy"


# =====================================================================
# 4. Centralized Error Handling Tests
# =====================================================================


def test_unexpected_exception_returns_clean_500():
    """Verify unexpected 500 errors return a safe generic message without internal traces."""
    # Temporarily patch an underlying service method to trigger an unhandled Exception
    with patch(
        "app.services.indicator_service.IndicatorService.compute_indicator",
        side_effect=RuntimeError("Secret database crash details!"),
    ):
        response = client.get(
            "/sma?symbol=INFY&start=2025-04-01&end=2025-04-10&window=5",
            headers={"api-key": "premium-key-789"},
        )
        assert response.status_code == 500
        data = response.json()
        assert data == {"detail": "Internal server error"}
        assert "Secret" not in json.dumps(data)
        assert "database" not in json.dumps(data)
        assert "traceback" not in json.dumps(data)
        assert "X-Request-ID" in response.headers


# =====================================================================
# 5. Metrics Tests
# =====================================================================


def test_metrics_json_endpoint():
    """Verify GET /metrics returns JSON summary."""
    response = client.get("/metrics", headers={"api-key": "premium-key-789"})
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert "total_errors" in data
    assert "avg_latency_ms" in data
    assert "cache_hits" in data
    assert "cache_misses" in data


def test_metrics_prometheus_endpoint():
    """Verify GET /metrics?format=prometheus returns valid Prometheus text."""
    response = client.get("/metrics?format=prometheus", headers={"api-key": "premium-key-789"})
    assert response.status_code == 200
    text_data = response.text
    assert "# HELP http_requests_total" in text_data
    assert "# TYPE http_requests_total counter" in text_data
    assert "http_requests_latency_ms_total" in text_data
