"""Indexed data retrieval must agree with a full scan of the bundled snapshot."""

import datetime

import polars as pl
import pytest

from app.core.config import settings
from app.core.exceptions import SymbolNotFoundException
from app.dependencies.core import get_stock_repository


@pytest.fixture(scope="module")
def optimized_repo():
    return get_stock_repository()


@pytest.fixture(scope="module")
def full_dataset():
    return pl.read_parquet(settings.DATASET_PATH).with_columns(pl.col("date").cast(pl.Date))


def test_index_contains_all_dataset_symbols(optimized_repo, full_dataset):
    assert set(optimized_repo._by_symbol) == set(full_dataset["symbol"].unique())
    assert len(optimized_repo._by_symbol) == 1168


@pytest.mark.parametrize("symbol", ["INFY", "RELIANCE", "TCS", "HDFCBANK"])
def test_get_stock_data_equivalence_with_scan(optimized_repo, full_dataset, symbol):
    start, end = datetime.date(2025, 4, 1), datetime.date(2025, 4, 30)
    indexed = optimized_repo.get_stock_data(symbol, start, end)
    scanned = full_dataset.filter(
        (pl.col("symbol") == symbol) & pl.col("date").is_between(start, end)
    ).sort("date")
    assert not indexed.is_empty()
    assert indexed.equals(scanned)


def test_get_stock_data_unknown_symbol_raises_domain_exception(optimized_repo):
    with pytest.raises(SymbolNotFoundException, match="Unknown symbol"):
        optimized_repo.get_stock_data(
            "TOTALLY_FAKE_SYMBOL", datetime.date(2025, 4, 1), datetime.date(2025, 4, 30)
        )


def test_get_stock_data_date_boundary_filtering(optimized_repo):
    start, end = datetime.date(2025, 4, 1), datetime.date(2025, 4, 10)
    dates = optimized_repo.get_stock_data("INFY", start, end)["date"].to_list()
    assert dates
    assert all(start <= day <= end for day in dates)
    assert dates == sorted(dates)


def test_get_stock_data_no_rows_in_date_range(optimized_repo):
    assert optimized_repo.get_stock_data(
        "INFY", datetime.date(1990, 1, 1), datetime.date(1990, 1, 10)
    ).is_empty()
