# Stock Technical Indicator API

This project is a FastAPI-based backend service to compute technical stock indicators like SMA, EMA, RSI, MACD, and Bollinger Bands based on historical OHLC data.

##  Our project is live!

- **Live API Base URL**: ` https://stock-technical-indicator-api.onrender.com/`
- **Interactive Swagger Docs**: `https://stock-technical-indicator-api.onrender.com/docs#/default/home__get`


## Try it Yourself

Here are three sample API keys you can use to test:

- **Free Tier:** `free-key-123`
- **Pro Tier:** `pro-key-456`
- **Premium Tier:** `premium-key-789`

### Example

To test the `/sma` endpoint for `INFY` stock between `2024-05-01` and `2024-06-30`:

##  Features

- Tier-based API access (Free, Pro, Premium)  
  - Free: SMA, EMA | 3 months data | 50 requests/day  
  - Pro: + RSI, MACD | 1 year data | 500 requests/day  
  - Premium: + Bollinger | 3 years data | Unlimited usage  
- API key authentication system  
- Daily request limit with auto-reset  
- In-memory caching to avoid redundant computation  
- Fast date-range-based filtering of stock data  
- Usage tracking and access validation per user  
- Supports 5+ endpoints:
  - `/sma`
  - `/ema`
  - `/rsi`
  - `/macd`
  - `/bollinger`
  - `/status`

##  Technologies Used

- **FastAPI** – API development  
- **Polars** – Efficient DataFrame handling  
- **SQLAlchemy** – ORM for PostgreSQL  
- **NeonDB (PostgreSQL)** – Cloud database  
- **SimpleCache (RAM)** – Custom in-memory caching  
- **Render** – Cloud deployment

##  Deployed API & Docs

- **Live API Base URL**: ` https://stock-technical-indicator-api.onrender.com/`
- **Interactive Swagger Docs**: `https://stock-technical-indicator-api.onrender.com/docs#/default/home__get`


