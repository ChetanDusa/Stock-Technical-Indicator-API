import datetime

import polars as pl
import pytest

from app.cache.interface import CacheInterface
from app.core.exceptions import SymbolNotFoundException
from app.services.indicator_service import IndicatorService


class FakeCache(CacheInterface):
    def __init__(self):
        self.store = {}
        self.hits = 0

    def get(self, key: str):
        if key in self.store:
            self.hits += 1
            return self.store[key]
        return None

    def set(self, key: str, value: any, ttl: int = 300) -> None:
        self.store[key] = value


class FakeStockRepo:
    def __init__(self, data: pl.DataFrame):
        self._df = data
        self.calls = 0
        self.cache_version = "test-snapshot"

    def get_stock_data(
        self, symbol: str, start_date: datetime.date, end_date: datetime.date
    ) -> pl.DataFrame:
        self.calls += 1
        return self._df


@pytest.fixture
def fake_stock_repo():
    df = pl.DataFrame(
        {
            "date": [datetime.date(2023, 1, 1), datetime.date(2023, 1, 2)],
            "symbol": ["TEST", "TEST"],
            "close": [10.0, 11.0],
        }
    )
    return FakeStockRepo(df)


@pytest.fixture
def fake_cache():
    return FakeCache()


def test_indicator_service_cache_hit_and_miss(fake_stock_repo, fake_cache):
    service = IndicatorService(stock_repo=fake_stock_repo, cache=fake_cache)
    start = datetime.date(2023, 1, 1)
    end = datetime.date(2023, 1, 2)

    # First call - cache miss
    result = service.compute_indicator("sma", "TEST", start, end, {"window": 2})
    assert len(result) > 0
    assert "SMA_2" in result[0]
    assert fake_stock_repo.calls == 1
    assert fake_cache.hits == 0

    # Second call - cache hit
    result2 = service.compute_indicator("sma", "TEST", start, end, {"window": 2})
    assert result2 == result
    assert fake_stock_repo.calls == 1  # Repo not called again
    assert fake_cache.hits == 1  # Hit incremented


def test_indicator_service_no_data(fake_cache):
    empty_repo = FakeStockRepo(pl.DataFrame({"date": [], "symbol": [], "close": []}))
    service = IndicatorService(stock_repo=empty_repo, cache=fake_cache)

    with pytest.raises(SymbolNotFoundException):
        service.compute_indicator(
            "sma", "NOTFOUND", datetime.date(2023, 1, 1), datetime.date(2023, 1, 2), {"window": 2}
        )
