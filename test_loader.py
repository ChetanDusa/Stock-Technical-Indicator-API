from data_loader import get_stock_data
import polars as pl

# Show available stock symbols and dates from the file
df_full = pl.read_parquet("stocks_ohlc_data.parquet")
print("✅ Available Symbols:", df_full["symbol"].unique())
print("📅 Available Dates:", df_full["date"].min(), "to", df_full["date"].max())

# Test with a real symbol and date range from the file
symbol = "INFY"  # Replace with one that exists in the symbol list printed above
start = "2023-01-01"
end = "2023-06-30"

# Call the function you want to test
df = get_stock_data(symbol, start, end)

# Show what it returned
print("📊 Columns:", df.columns)
print("🔢 Number of rows:", df.shape[0])
print("📅 Sample rows:")
print(df.head())
