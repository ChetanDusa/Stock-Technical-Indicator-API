# auth.py

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import date

from database import SessionLocal
from models import User

# Tier definitions with rate limits and access restrictions
# max50
TIER_LIMITS = {
    "free": {
        "max_requests": 50,  # max 50 requests per day
        "allowed_indicators": {"sma", "ema"},  # only these indicators allowed
        "history_days": 90,  # can access last 3 months of data
    },
    "pro": {
        "max_requests": 500,
        "allowed_indicators": {"sma", "ema", "rsi", "macd"},
        "history_days": 365,  # can access last 1 year
    },
    "premium": {
        "max_requests": float("inf"),  # no limit for premium
        "allowed_indicators": {"sma", "ema", "rsi", "macd", "bollinger"},
        "history_days": 3 * 365,  # full 3 years
    },
}

#  Creates a new DB session — used in every request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#  Checks and returns the current user based on their API key
def get_current_user(api_key: str = Header(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.api_key == api_key).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid API Key 😬")

    #  Reset request count daily
    today = date.today()
    if user.last_request_date != today:
        user.request_count = 0
        user.last_request_date = today

    # Check if user exceeded daily request limit
    tier = user.subscription
    limit = TIER_LIMITS[tier]["max_requests"]
    if user.request_count >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for your tier 🚫")

    #  All good — update request count and return user
    user.request_count += 1
    db.commit()
    db.refresh(user)

    return user
