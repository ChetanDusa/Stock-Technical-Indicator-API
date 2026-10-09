import polars as pl
import pytest

from indicators import bollinger_bands, ema, macd, rsi, sma


@pytest.fixture
def sample_df():
    # Simple increasing prices to make it easy to assert
    return pl.DataFrame(
        {
            "date": [
                "2023-01-01",
                "2023-01-02",
                "2023-01-03",
                "2023-01-04",
                "2023-01-05",
                "2023-01-06",
                "2023-01-07",
                "2023-01-08",
                "2023-01-09",
                "2023-01-10",
                "2023-01-11",
                "2023-01-12",
                "2023-01-13",
                "2023-01-14",
                "2023-01-15",
            ],
            "symbol": ["TEST"] * 15,
            "close": [
                10.0,
                11.0,
                12.0,
                13.0,
                14.0,
                15.0,
                16.0,
                17.0,
                18.0,
                19.0,
                20.0,
                21.0,
                22.0,
                23.0,
                24.0,
            ],
        }
    )


def test_sma(sample_df):
    result = sma(sample_df, window=5)
    assert "SMA_5" in result.columns
    # Row index 4 (5th element) should be (10+11+12+13+14)/5 = 12.0
    assert result["SMA_5"][4] == 12.0


def test_ema(sample_df):
    result = ema(sample_df, span=5)
    assert "EMA_5" in result.columns
    # EWMA is slightly more complex, but we can just check it's not null at the end
    assert result["EMA_5"][14] is not None


def test_rsi(sample_df):
    result = rsi(sample_df, period=14)
    assert "RSI_14" in result.columns
    # Since prices only go up, RSI should be 100 after 14 days
    assert round(result["RSI_14"][14], 1) == 100.0


def test_macd(sample_df):
    result = macd(sample_df, fast=3, slow=5, signal=2)
    assert "MACD" in result.columns
    assert "MACD_Signal" in result.columns
    assert "MACD_Hist" in result.columns
    assert result["MACD"][14] is not None


def test_bollinger_bands(sample_df):
    result = bollinger_bands(sample_df, period=5, std_multiplier=2.0)
    assert "BB_Mid_5" in result.columns
    assert "BB_Upper_5" in result.columns
    assert "BB_Lower_5" in result.columns

    mid = result["BB_Mid_5"][4]
    assert mid == 12.0  # SMA 5
    assert result["BB_Upper_5"][4] > mid
    assert result["BB_Lower_5"][4] < mid
