# data_loader.py

import polars as pl
from datetime import datetime

# we load the whole dataset once when the app starts
df = pl.read_parquet("stocks_ohlc_data.parquet")

def get_stock_data(symbol: str, start: str, end: str) -> pl.DataFrame:
    """
    Pulls stock data for a given symbol and date range (start to end inclusive).
    Assumes dates are in 'YYYY-MM-DD' format.
    """
    # convert the incoming date strings to date objects
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()

    # filter by symbol and date range — then sort by date
    filtered = (
        df.filter(
            (pl.col("symbol") == symbol) &
            (pl.col("date") >= start_date) &
            (pl.col("date") <= end_date)
        )
        .sort("date")
    )

    return filtered
