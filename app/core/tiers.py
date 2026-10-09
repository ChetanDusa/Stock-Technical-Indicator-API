"""Tier definitions for subscription-based access control."""

from __future__ import annotations

from typing import Any, Dict

TIER_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "max_requests": 50,
        "allowed_indicators": {"sma", "ema"},
        "history_days": 90,
        "screening_allowed": False,
        "allowed_screening_indicators": set(),
    },
    "pro": {
        "max_requests": 500,
        "allowed_indicators": {"sma", "ema", "rsi", "macd"},
        "history_days": 365,
        "screening_allowed": True,
        "allowed_screening_indicators": {"PRICE", "SMA", "EMA", "RSI", "MACD"},
    },
    "premium": {
        "max_requests": float("inf"),
        "allowed_indicators": {"sma", "ema", "rsi", "macd", "bollinger"},
        "history_days": 3 * 365,
        "screening_allowed": True,
        "allowed_screening_indicators": {"PRICE", "SMA", "EMA", "RSI", "MACD", "BOLLINGER"},
    },
}
