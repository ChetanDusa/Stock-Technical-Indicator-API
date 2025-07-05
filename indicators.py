import polars as pl

def sma(df: pl.DataFrame, window: int) -> pl.DataFrame:
    """
    Simple Moving Average (SMA) over 'close' prices.
    """
    return df.with_columns(
        pl.col("close").rolling_mean(window).alias(f"SMA_{window}")
    )


def ema(df: pl.DataFrame, span: int) -> pl.DataFrame:
    """
    Exponential Moving Average (EMA) over 'close' prices.
    """
    return df.with_columns(
        pl.col("close").ewm_mean(span=span).alias(f"EMA_{span}")
    )


def rsi(df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
    """
    Relative Strength Index (RSI) using Polars expressions.
    """
    df = df.with_columns([
        (pl.col("close").diff().alias("delta"))
    ])

    df = df.with_columns([
        pl.when(pl.col("delta") > 0).then(pl.col("delta")).otherwise(0.0).alias("gain"),
        pl.when(pl.col("delta") < 0).then(-pl.col("delta")).otherwise(0.0).alias("loss"),
    ])

    df = df.with_columns([
        pl.col("gain").rolling_mean(period).alias("avg_gain"),
        pl.col("loss").rolling_mean(period).alias("avg_loss"),
    ])

    df = df.with_columns([
        (100 - (100 / (1 + (pl.col("avg_gain") / (pl.col("avg_loss") + 1e-9))))).alias(f"RSI_{period}")
    ])

    return df



def macd(df: pl.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pl.DataFrame:
    """
    MACD = EMA(fast) - EMA(slow), plus Signal line and Histogram.
    """
    close = df["close"]
    ema_fast = close.ewm_mean(span=fast)
    ema_slow = close.ewm_mean(span=slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm_mean(span=signal)
    hist = macd_line - signal_line

    return df.with_columns([
        pl.Series("MACD", macd_line),
        pl.Series("MACD_Signal", signal_line),
        pl.Series("MACD_Hist", hist)
    ])


def bollinger_bands(df: pl.DataFrame, period: int = 20, std_multiplier: float = 2.0) -> pl.DataFrame:
    """
    Bollinger Bands using SMA and std deviation.
    """
    close = df["close"]
    sma_val = close.rolling_mean(period)
    std_val = close.rolling_std(period)

    upper_band = sma_val + std_multiplier * std_val
    lower_band = sma_val - std_multiplier * std_val

    return df.with_columns([
        pl.Series(name=f"BB_Mid_{period}", values=sma_val),
        pl.Series(name=f"BB_Upper_{period}", values=upper_band),
        pl.Series(name=f"BB_Lower_{period}", values=lower_band)
    ])
