# test_rsi.py
from data_loader import get_stock_data
from indicators import rsi

symbol = "INFY"
start = "2023-01-01"
end = "2023-06-30"

df = get_stock_data(symbol, start, end)
print("✅ Loaded data:", df.shape)

df_rsi = rsi(df, period=14)
print("📊 Columns:", df_rsi.columns)
print("🔢 Sample:")
print(df_rsi.select(["date", "symbol", "close", "RSI_14"]).tail(5))
