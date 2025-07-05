import polars as pl
from data_loader import get_stock_data
from indicators import sma

# Load filtered data
symbol = "INFY"
start = "2023-01-01"
end = "2023-06-30"
df = get_stock_data(symbol, start, end)

# Apply SMA
window = 14
sma_df = sma(df, window)

# Print results
print(sma_df.select(["date", "symbol", "close", f"SMA_{window}"]).drop_nulls().head())
