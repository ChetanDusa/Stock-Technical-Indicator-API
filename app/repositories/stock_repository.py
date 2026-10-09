"""Immutable Parquet snapshot, sorted once and indexed by symbol at startup."""

import datetime
import hashlib
import time
from pathlib import Path

import polars as pl

from app.core.config import settings
from app.core.exceptions import SymbolNotFoundException
from app.core.logging import get_logger

logger = get_logger("app.dataset")


class StockDataRepository:
    def __init__(self, parquet_path: str | Path | None = None) -> None:
        path = Path(parquet_path) if parquet_path else settings.DATASET_PATH
        started = time.perf_counter()
        self._df = pl.read_parquet(path)
        required = {"date", "symbol", "open", "high", "low", "close", "volume"}
        if required - set(self._df.columns) or self._df.is_empty():
            raise ValueError("Dataset must contain nonempty OHLCV data")
        self._df = self._df.with_columns(pl.col("date").cast(pl.Date)).sort(["symbol", "date"])
        if self._df.null_count().select(pl.sum_horizontal(pl.all())).item() != 0:
            raise ValueError("Dataset contains null values")
        # Sorted bars can be checked for duplicates without a full-row hash set.
        duplicate_bar = (pl.col("symbol") == pl.col("symbol").shift(1)) & (
            pl.col("date") == pl.col("date").shift(1)
        )
        if self._df.select(duplicate_bar.any()).item():
            raise ValueError("Dataset contains duplicate symbol/date rows")
        if self._df.filter(~pl.col("close").is_finite()).height:
            raise ValueError("Dataset contains nonfinite close prices")

        # Sorted symbols occupy contiguous rows. Slices share the original buffers.
        self._by_symbol = {}
        offset = 0
        for symbol, length in self._df.group_by("symbol", maintain_order=True).len().iter_rows():
            self._by_symbol[symbol] = self._df.slice(offset, length)
            offset += length
        self.start_date = self._df["date"].min()
        self.end_date = self._df["date"].max()
        with path.open("rb") as handle:
            self.cache_version = hashlib.file_digest(handle, "sha256").hexdigest()[:16]
        logger.info(
            "Dataset loaded: rows=%s symbols=%s end=%s duration_ms=%.1f",
            self._df.height,
            len(self._by_symbol),
            self.end_date,
            (time.perf_counter() - started) * 1000,
        )

    def get_stock_data(
        self, symbol: str, start_date: datetime.date, end_date: datetime.date
    ) -> pl.DataFrame:
        frame = self._by_symbol.get(symbol)
        if frame is None:
            raise SymbolNotFoundException(f"Unknown symbol: {symbol}")
        return frame.filter(pl.col("date").is_between(start_date, end_date, closed="both"))

    def get_all_data(self) -> pl.DataFrame:
        """The repository owns this frame; callers must use immutable Polars operations."""
        return self._df

    def get_symbols(self) -> list[str]:
        return sorted(self._by_symbol)
