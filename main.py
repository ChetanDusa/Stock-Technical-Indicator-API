# main.py

from fastapi import FastAPI, Query, HTTPException, Depends
from datetime import datetime, timedelta, date

from data_loader import get_stock_data
from indicators import sma, ema, rsi, macd, bollinger_bands
from auth import get_current_user, TIER_LIMITS
from models import User
from cache import SimpleCache

# basic in-memory cache — keeps things fast
cache = SimpleCache()

# setting up FastAPI app with title and version info
app = FastAPI(
    title="Stock Technical Indicator API",
    description="API to fetch SMA, EMA, RSI, MACD, Bollinger Bands using Polars",
    version="2.0.0"
)

# just a welcome route to check if server is running
@app.get("/")
def home():
    return {"message": "Welcome to the Stock Technical Indicator API"}

# this function checks if the user is allowed to fetch the requested data
def check_user_access(user: User, indicator: str, start: str, end: str):
    tier_info = TIER_LIMITS[user.subscription]

    if indicator not in tier_info["allowed_indicators"]:
        raise HTTPException(
            status_code=403,
            detail=f"{indicator.upper()} not allowed for {user.subscription} tier"
        )

    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)

    if (e - s).days < 0:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    # make sure user isn’t going too far back in history
    today = date.today()
    allowed_start = today - timedelta(days=tier_info["history_days"])
    if s.date() < allowed_start:
        raise HTTPException(
            status_code=403,
            detail=f"{user.subscription.title()} tier only allows data from {allowed_start.isoformat()} onwards"
        )

# ------------------ INDICATOR ROUTES BELOW -------------------

# fetch SMA values
@app.get("/sma")
def get_sma(
    symbol: str,
    start: str,
    end: str,
    window: int = Query(14, gt=0),
    user: User = Depends(get_current_user)
):
    check_user_access(user, "sma", start, end)
    cache_key = f"sma:{symbol}:{start}:{end}:{window}:{user.username}"
    if (cached := cache.get(cache_key)):
        return cached

    df = get_stock_data(symbol, start, end)
    if df.is_empty():
        raise HTTPException(status_code=404, detail="No data found")

    result = sma(df, window)
    data = result.select(["date", "symbol", f"SMA_{window}"]).drop_nulls().to_dicts()
    cache.set(cache_key, data, ttl=300)
    return data

# fetch EMA values
@app.get("/ema")
def get_ema(
    symbol: str,
    start: str,
    end: str,
    span: int = Query(14, gt=0),
    user: User = Depends(get_current_user)
):
    check_user_access(user, "ema", start, end)
    cache_key = f"ema:{symbol}:{start}:{end}:{span}:{user.username}"
    if (cached := cache.get(cache_key)):
        return cached

    df = get_stock_data(symbol, start, end)
    if df.is_empty():
        raise HTTPException(status_code=404, detail="No data found")

    result = ema(df, span)
    data = result.select(["date", "symbol", f"EMA_{span}"]).drop_nulls().to_dicts()
    cache.set(cache_key, data, ttl=300)
    return data

# fetch RSI values
@app.get("/rsi")
def get_rsi(
    symbol: str,
    start: str,
    end: str,
    period: int = Query(14, gt=1),
    user: User = Depends(get_current_user)
):
    check_user_access(user, "rsi", start, end)
    cache_key = f"rsi:{symbol}:{start}:{end}:{period}:{user.username}"
    if (cached := cache.get(cache_key)):
        return cached

    df = get_stock_data(symbol, start, end)
    if df.is_empty():
        raise HTTPException(status_code=404, detail="No data found")

    result = rsi(df, period)
    data = result.select(["date", "symbol", f"RSI_{period}"]).drop_nulls().to_dicts()
    cache.set(cache_key, data, ttl=300)
    return data

# fetch MACD values
@app.get("/macd")
def get_macd(
    symbol: str,
    start: str,
    end: str,
    fast: int = Query(12, gt=0),
    slow: int = Query(26, gt=0),
    signal: int = Query(9, gt=0),
    user: User = Depends(get_current_user)
):
    check_user_access(user, "macd", start, end)
    cache_key = f"macd:{symbol}:{start}:{end}:{fast}:{slow}:{signal}:{user.username}"
    if (cached := cache.get(cache_key)):
        return cached

    df = get_stock_data(symbol, start, end)
    if df.is_empty():
        raise HTTPException(status_code=404, detail="No data found")

    result = macd(df, fast, slow, signal)
    data = result.select(["date", "symbol", "MACD", "MACD_Signal", "MACD_Hist"]).drop_nulls().to_dicts()
    cache.set(cache_key, data, ttl=300)
    return data

# fetch Bollinger Bands
@app.get("/bollinger")
def get_bollinger(
    symbol: str,
    start: str,
    end: str,
    period: int = Query(20, gt=0),
    std_multiplier: float = Query(2.0, gt=0),
    user: User = Depends(get_current_user)
):
    check_user_access(user, "bollinger", start, end)
    cache_key = f"bollinger:{symbol}:{start}:{end}:{period}:{std_multiplier}:{user.username}"
    if (cached := cache.get(cache_key)):
        return cached

    df = get_stock_data(symbol, start, end)
    if df.is_empty():
        raise HTTPException(status_code=404, detail="No data found")

    result = bollinger_bands(df, period, std_multiplier)
    data = result.select(
        ["date", "symbol", f"BB_Mid_{period}", f"BB_Upper_{period}", f"BB_Lower_{period}"]
    ).drop_nulls().to_dicts()
    cache.set(cache_key, data, ttl=300)
    return data

# show current user's usage stats like requests left today, etc
@app.get("/status")
def get_status(user: User = Depends(get_current_user)):
    tier_info = TIER_LIMITS[user.subscription]
    max_requests = tier_info["max_requests"]

    return {
        "username": user.username,
        "subscription": user.subscription,
        "requests_today": user.request_count,
        "max_requests_per_day": (
            int(max_requests) if max_requests != float("inf") else "unlimited"
        ),
        "requests_remaining": (
            int(max_requests - user.request_count)
            if max_requests != float("inf") else "unlimited"
        ),
        "last_request_date": user.last_request_date.isoformat()
    }
