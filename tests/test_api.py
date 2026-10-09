"""API authentication, authorization, validation and quota contracts."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_api_key
from app.dependencies.core import get_redis
from app.main import app
from app.services.rate_limiter import quota_key
from database import SessionLocal
from models import User

client = TestClient(app)
PARAMS = {"symbol": "INFY", "start": "2025-04-01", "end": "2025-04-30"}
PREMIUM = {"api-key": "premium-key-789"}


def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Stock Technical Indicator API"}


def test_no_api_key():
    assert client.get("/sma", params=PARAMS).status_code == 401


def test_invalid_api_key():
    response = client.get("/sma", params=PARAMS, headers={"api-key": "invalid"})
    assert response.status_code == 401
    assert "Invalid API Key" in response.json()["detail"]


def test_valid_sma_request():
    response = client.get("/sma", params={**PARAMS, "window": 14}, headers=PREMIUM)
    assert response.status_code == 200
    assert response.json()
    assert {"date", "symbol", "SMA_14"} == set(response.json()[0])


def test_invalid_date_range():
    response = client.get("/sma", params={**PARAMS, "start": "2025-05-01"}, headers=PREMIUM)
    assert response.status_code == 400
    assert "End date must be after start date" in response.json()["detail"]


def test_unauthorized_indicator_for_tier():
    response = client.get("/rsi", params=PARAMS, headers={"api-key": "free-key-123"})
    assert response.status_code == 403
    assert "RSI not allowed for free tier" in response.json()["detail"]


def test_data_not_found():
    response = client.get("/sma", params={**PARAMS, "symbol": "FAKE_SYMBOL"}, headers=PREMIUM)
    assert response.status_code == 404
    assert response.json()["detail"] == "No data found"


def test_rate_limiting():
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.api_key_hash == hash_api_key("free-key-123")))
        user_id = user.id
    get_redis().set(quota_key(user_id), 50, ex=86400)
    response = client.get("/sma", params=PARAMS, headers={"api-key": "free-key-123"})
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]
    assert int(response.headers["Retry-After"]) > 0
    assert int(get_redis().get(quota_key(user_id))) == 50
