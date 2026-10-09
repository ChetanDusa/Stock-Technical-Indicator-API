"""Cache-aside indicator computation with full-history warm-up before output filtering."""

import datetime
import hashlib
import json

import polars as pl

from app.cache.interface import CacheInterface
from app.core.config import settings
from app.core.exceptions import SymbolNotFoundException
from app.core.metrics import metrics
from app.repositories.stock_repository import StockDataRepository
from indicators import bollinger_bands, ema, macd, rsi, sma

_INDICATOR_REGISTRY = {
    "sma": (sma, lambda p: [f"SMA_{p['window']}"]),
    "ema": (ema, lambda p: [f"EMA_{p['span']}"]),
    "rsi": (rsi, lambda p: [f"RSI_{p['period']}"]),
    "macd": (macd, lambda p: ["MACD", "MACD_Signal", "MACD_Hist"]),
    "bollinger": (
        bollinger_bands,
        lambda p: [f"BB_Mid_{p['period']}", f"BB_Upper_{p['period']}", f"BB_Lower_{p['period']}"],
    ),
}


class IndicatorService:
    def __init__(self, stock_repo: StockDataRepository, cache: CacheInterface) -> None:
        self.stock_repo = stock_repo
        self.cache = cache

    def compute_indicator(
        self,
        indicator_name: str,
        symbol: str,
        start_date: datetime.date,
        end_date: datetime.date,
        params: dict,
    ) -> list[dict]:
        payload = {
            "indicator": indicator_name,
            "symbol": symbol,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "params": params,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        key = f"{settings.REDIS_KEY_PREFIX}:indicator:v3:{self.stock_repo.cache_version}:{digest}"
        cached = self.cache.get(key)
        if cached is not None:
            metrics.record_cache_hit()
            return cached
        metrics.record_cache_miss()

        # Start dates restrict output, not the rolling/recursive calculation history.
        frame = self.stock_repo.get_stock_data(symbol, datetime.date.min, end_date)
        requested = frame.filter(pl.col("date").is_between(start_date, end_date))
        if requested.is_empty():
            raise SymbolNotFoundException()

        calculate, output_columns = _INDICATOR_REGISTRY[indicator_name]
        result = calculate(frame, **params).filter(pl.col("date").is_between(start_date, end_date))
        data = (
            result.select(
                pl.col("date").cast(pl.Date).dt.to_string("%Y-%m-%d"),
                "symbol",
                *output_columns(params),
            )
            .drop_nulls()
            .to_dicts()
        )
        self.cache.set(key, data, ttl=settings.CACHE_DEFAULT_TTL)
        return data
