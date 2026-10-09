"""Comprehensive tests for the Stock Screening Engine."""

import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.screening import IndicatorRef, ScreeningCondition
from app.services.screening_engine import ScreeningEngine
from app.services.screening_service import ScreeningService

client = TestClient(app)


# =====================================================================
# 1. Schema Validation Tests
# =====================================================================


def test_validation_unknown_indicator():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "UNKNOWN_IND", "operator": ">", "value": 100}],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_unknown_operator():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "SMA", "period": 20, "operator": "~=", "value": 100}],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_missing_period_for_sma():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "SMA", "operator": ">", "value": 100}],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_invalid_period_for_rsi():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "RSI", "period": 1, "operator": "<", "value": 30}],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_invalid_macd_parameters():
    # fast >= slow must be rejected
    response = client.post(
        "/screen",
        json={
            "conditions": [
                {
                    "indicator": "MACD",
                    "fast": 30,
                    "slow": 10,
                    "signal_period": 9,
                    "operator": ">",
                    "value": 0,
                }
            ],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_invalid_bollinger_std():
    response = client.post(
        "/screen",
        json={
            "conditions": [
                {
                    "indicator": "BOLLINGER",
                    "period": 20,
                    "std_multiplier": -1.0,
                    "operator": ">",
                    "value": 100,
                }
            ],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_both_value_and_reference():
    response = client.post(
        "/screen",
        json={
            "conditions": [
                {
                    "indicator": "PRICE",
                    "operator": ">",
                    "value": 100,
                    "reference": {"indicator": "SMA", "period": 50},
                }
            ],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_neither_value_nor_reference():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "PRICE", "operator": ">"}],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


def test_validation_price_with_period():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "PRICE", "period": 14, "operator": ">", "value": 100}],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 422


# =====================================================================
# 2. Authorization / Tier Tests
# =====================================================================


def test_auth_free_tier_denied_screening():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "SMA", "period": 14, "operator": ">", "value": 100}],
            "logic": "AND",
        },
        headers={"api-key": "free-key-123"},
    )
    assert response.status_code == 403
    assert "not allowed for free tier" in response.json()["detail"]


def test_auth_pro_tier_denied_bollinger():
    response = client.post(
        "/screen",
        json={
            "conditions": [{"indicator": "BOLLINGER", "period": 20, "operator": ">", "value": 100}],
            "logic": "AND",
        },
        headers={"api-key": "pro-key-456"},
    )
    assert response.status_code == 403
    assert "BOLLINGER not allowed for pro tier" in response.json()["detail"]


def test_auth_pro_tier_allowed_rsi_sma():
    response = client.post(
        "/screen",
        json={
            "conditions": [
                {"indicator": "RSI", "period": 14, "operator": "<", "value": 30},
                {"indicator": "SMA", "period": 50, "operator": ">", "value": 100},
            ],
            "logic": "AND",
        },
        headers={"api-key": "pro-key-456"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "matched_symbols" in data
    assert "count" in data
    assert data["conditions_evaluated"] == 2


def test_auth_premium_tier_allowed_bollinger():
    response = client.post(
        "/screen",
        json={
            "conditions": [
                {
                    "indicator": "PRICE",
                    "operator": "<",
                    "reference": {"indicator": "BOLLINGER", "period": 20, "band": "lower"},
                }
            ],
            "logic": "AND",
        },
        headers={"api-key": "premium-key-789"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "matched_symbols" in data
    assert isinstance(data["matched_symbols"], list)


# =====================================================================
# 3. Correctness & Unit Tests on Synthetic Data
# =====================================================================


@pytest.fixture
def synthetic_stock_df():
    """Synthetic multi-symbol dataset with known prices and different latest dates."""
    return pl.DataFrame(
        {
            "symbol": (
                ["AAA"] * 5  # AAA: prices 10 to 50
                + ["BBB"] * 5  # BBB: prices 50 to 10
                + ["CCC"] * 2  # CCC: short history (only 2 rows)
            ),
            "date": (
                ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]
                + ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]
                + ["2022-06-01", "2022-06-02"]  # different latest date
            ),
            "close": [
                10.0,
                20.0,
                30.0,
                40.0,
                50.0,  # AAA latest close = 50.0, SMA_3 = (30+40+50)/3 = 40.0
                50.0,
                40.0,
                30.0,
                20.0,
                10.0,  # BBB latest close = 10.0, SMA_3 = (30+20+10)/3 = 20.0
                100.0,
                105.0,  # CCC latest close = 105.0, SMA_3 = None (insufficient rows)
            ],
        }
    )


def test_engine_scalar_comparison(synthetic_stock_df):
    engine = ScreeningEngine()
    cond = ScreeningCondition(indicator="PRICE", operator=">", value=40.0)
    matched = engine.evaluate(synthetic_stock_df, [cond], logic="AND")
    # AAA latest close is 50.0 (> 40.0), CCC latest close is 105.0 (> 40.0), BBB is 10.0
    assert matched == ["AAA", "CCC"]


def test_engine_reference_comparison(synthetic_stock_df):
    engine = ScreeningEngine()
    # Condition: PRICE > SMA(3)
    # AAA: latest PRICE=50.0 > SMA_3=40.0 -> True
    # BBB: latest PRICE=10.0 > SMA_3=20.0 -> False
    # CCC: SMA_3 is null -> False (null safety)
    cond = ScreeningCondition(
        indicator="PRICE",
        operator=">",
        reference=IndicatorRef(indicator="SMA", period=3),
    )
    matched = engine.evaluate(synthetic_stock_df, [cond], logic="AND")
    assert matched == ["AAA"]


def test_engine_null_safety_insufficient_history(synthetic_stock_df):
    engine = ScreeningEngine()
    # CCC only has 2 rows, so SMA(3) is null.
    # Verify that SMA(3) != 100 or SMA(3) < 100 does NOT match CCC because null condition = False.
    cond_neq = ScreeningCondition(indicator="SMA", period=3, operator="!=", value=100.0)
    matched_neq = engine.evaluate(synthetic_stock_df, [cond_neq], logic="AND")
    assert "CCC" not in matched_neq

    cond_lt = ScreeningCondition(indicator="SMA", period=3, operator="<", value=1000.0)
    matched_lt = engine.evaluate(synthetic_stock_df, [cond_lt], logic="AND")
    assert "CCC" not in matched_lt


def test_engine_and_or_logic(synthetic_stock_df):
    engine = ScreeningEngine()
    # Cond 1: PRICE > 20 (AAA: 50 > 20 True, BBB: 10 > 20 False, CCC: 105 > 20 True)
    # Cond 2: SMA(3) < 30 (AAA: 40 < 30 False, BBB: 20 < 30 True, CCC: null False)
    cond1 = ScreeningCondition(indicator="PRICE", operator=">", value=20.0)
    cond2 = ScreeningCondition(indicator="SMA", period=3, operator="<", value=30.0)

    # AND: No symbol satisfies both
    matched_and = engine.evaluate(synthetic_stock_df, [cond1, cond2], logic="AND")
    assert matched_and == []

    # OR: AAA satisfies cond1, BBB satisfies cond2, CCC satisfies cond1
    matched_or = engine.evaluate(synthetic_stock_df, [cond1, cond2], logic="OR")
    assert matched_or == ["AAA", "BBB", "CCC"]


def test_engine_symbol_isolation_no_bleeding():
    """Verify rolling indicators for symbol A do not bleed into symbol B."""
    engine = ScreeningEngine()
    df = pl.DataFrame(
        {
            "symbol": ["SYM_A"] * 5 + ["SYM_B"] * 5,
            "date": [f"2023-01-0{i}" for i in range(1, 6)] * 2,
            "close": [10.0, 10.0, 10.0, 10.0, 1000.0] + [10.0, 10.0, 10.0, 10.0, 10.0],
        }
    )
    # SYM_A has a huge spike at the end, SYM_B is constant 10.0.
    # SMA_5 for SYM_B should be exactly 10.0.
    cond = ScreeningCondition(indicator="SMA", period=5, operator="==", value=10.0)
    matched = engine.evaluate(df, [cond], logic="AND")
    assert matched == ["SYM_B"]


# =====================================================================
# 4. Reference Comparisons (MACD, Bollinger, SMA vs SMA)
# =====================================================================


def test_reference_sma_vs_sma(synthetic_stock_df):
    engine = ScreeningEngine()
    # SMA(2) vs SMA(3)
    # AAA: prices [10, 20, 30, 40, 50] -> SMA(2)=(40+50)/2=45.0, SMA(3)=(30+40+50)/3=40.0 -> 45 > 40 (True)
    # BBB: prices [50, 40, 30, 20, 10] -> SMA(2)=(20+10)/2=15.0, SMA(3)=(30+20+10)/3=20.0 -> 15 > 20 (False)
    cond = ScreeningCondition(
        indicator="SMA",
        period=2,
        operator=">",
        reference=IndicatorRef(indicator="SMA", period=3),
    )
    matched = engine.evaluate(synthetic_stock_df, [cond], logic="AND")
    assert matched == ["AAA"]


def test_reference_macd_vs_signal():
    engine = ScreeningEngine()
    # Create trending series
    df = pl.DataFrame(
        {
            "symbol": ["UP"] * 20 + ["DOWN"] * 20,
            "date": [f"2023-01-{i:02d}" for i in range(1, 21)] * 2,
            "close": [float(i * 10) for i in range(1, 21)]
            + [float(200 - i * 10) for i in range(1, 21)],
        }
    )
    # Condition: MACD > MACD_Signal
    cond = ScreeningCondition(
        indicator="MACD",
        fast=3,
        slow=6,
        signal_period=3,
        component="macd",
        operator=">",
        reference=IndicatorRef(
            indicator="MACD", fast=3, slow=6, signal_period=3, component="signal"
        ),
    )
    matched = engine.evaluate(df, [cond], logic="AND")
    assert "UP" in matched
    assert "DOWN" not in matched


# =====================================================================
# 5. Deterministic Cache Tests
# =====================================================================


def test_cache_key_determinism():
    cond1 = ScreeningCondition(indicator="PRICE", operator=">", value=100.0)
    cond2 = ScreeningCondition(indicator="SMA", period=50, operator="<", value=200.0)

    key1 = ScreeningService.generate_cache_key([cond1, cond2], "AND")
    key2 = ScreeningService.generate_cache_key([cond1, cond2], "AND")
    assert key1 == key2
    assert key1.startswith("screen:v3:")

    # Different logic -> different key
    key_or = ScreeningService.generate_cache_key([cond1, cond2], "OR")
    assert key1 != key_or


def test_cache_hit_returns_identical_result():
    # Make initial request (cache miss)
    body = {
        "conditions": [{"indicator": "SMA", "period": 14, "operator": ">", "value": 500}],
        "logic": "AND",
    }
    resp1 = client.post("/screen", json=body, headers={"api-key": "premium-key-789"})
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Second identical request (cache hit)
    resp2 = client.post("/screen", json=body, headers={"api-key": "premium-key-789"})
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data1 == data2
    assert data1["count"] == len(data1["matched_symbols"])


def test_screen_no_match_returns_empty_list():
    body = {
        "conditions": [{"indicator": "PRICE", "operator": ">", "value": 1000000.0}],
        "logic": "AND",
    }
    resp = client.post("/screen", json=body, headers={"api-key": "premium-key-789"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched_symbols"] == []
    assert data["count"] == 0
    assert data["conditions_evaluated"] == 1
