"""Polars indicator functions; input rows must be ordered chronologically."""

import polars as pl


def sma(df: pl.DataFrame, window: int) -> pl.DataFrame:
    return df.with_columns(pl.col("close").rolling_mean(window).alias(f"SMA_{window}"))


def ema(df: pl.DataFrame, span: int) -> pl.DataFrame:
    """Normalized exponential mean (adjust=True), initialized from available history."""
    return df.with_columns(pl.col("close").ewm_mean(span=span, adjust=True).alias(f"EMA_{span}"))


def rsi(df: pl.DataFrame, period: int = 14, *, group_by_symbol: bool = False) -> pl.DataFrame:
    """Cutler RSI: simple rolling means of N price changes; a flat window returns 50."""

    def grouped(expr: pl.Expr) -> pl.Expr:
        return expr.over("symbol") if group_by_symbol else expr

    df = df.with_columns(grouped(pl.col("close").diff()).alias("__rsi_delta"))
    delta = pl.col("__rsi_delta")
    df = df.with_columns(
        pl.when(delta.is_null())
        .then(None)
        .otherwise(delta.clip(lower_bound=0))
        .alias("__rsi_gain"),
        pl.when(delta.is_null())
        .then(None)
        .otherwise((-delta).clip(lower_bound=0))
        .alias("__rsi_loss"),
    ).with_columns(
        grouped(pl.col("__rsi_gain").rolling_mean(period)).alias("__rsi_avg_gain"),
        grouped(pl.col("__rsi_loss").rolling_mean(period)).alias("__rsi_avg_loss"),
    )
    gain, loss = pl.col("__rsi_avg_gain"), pl.col("__rsi_avg_loss")
    value = (
        pl.when(gain.is_null() | loss.is_null())
        .then(None)
        .when((gain == 0) & (loss == 0))
        .then(50.0)
        .when(loss == 0)
        .then(100.0)
        .otherwise(100.0 - 100.0 / (1.0 + gain / loss))
    )
    return df.with_columns(value.alias(f"RSI_{period}")).drop(
        "__rsi_delta", "__rsi_gain", "__rsi_loss", "__rsi_avg_gain", "__rsi_avg_loss"
    )


def macd(df: pl.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pl.DataFrame:
    """Difference of normalized exponential means, plus signal and histogram."""
    close = df["close"]
    line = close.ewm_mean(span=fast, adjust=True) - close.ewm_mean(span=slow, adjust=True)
    signal_line = line.ewm_mean(span=signal, adjust=True)
    return df.with_columns(
        line.alias("MACD"),
        signal_line.alias("MACD_Signal"),
        (line - signal_line).alias("MACD_Hist"),
    )


def bollinger_bands(
    df: pl.DataFrame, period: int = 20, std_multiplier: float = 2.0
) -> pl.DataFrame:
    """Rolling mean plus/minus a multiple of sample standard deviation (ddof=1)."""
    close = df["close"]
    middle = close.rolling_mean(period)
    std = close.rolling_std(period, ddof=1)
    return df.with_columns(
        middle.alias(f"BB_Mid_{period}"),
        (middle + std_multiplier * std).alias(f"BB_Upper_{period}"),
        (middle - std_multiplier * std).alias(f"BB_Lower_{period}"),
    )
