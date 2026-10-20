# Stock Technical Indicator API.

[![CI](https://github.com/ChetanDusa/Stock-Technical-Indicator-API/actions/workflows/ci.yml/badge.svg)](https://github.com/ChetanDusa/Stock-Technical-Indicator-API/actions/workflows/ci.yml)

A FastAPI service for historical stock indicators and multi-condition stock screening.
It uses Polars for calculations, PostgreSQL for accounts, and Redis for response caching
and daily quotas.

The bundled Parquet snapshot contains **830,955 rows and 1,168 symbols**, from
**1 July 2022 through 30 June 2025**. It is a fixed historical dataset.
The API exposes its coverage at `/dataset` and supported tickers at `/symbols`.

## Live API

**[Interactive API documentation](https://stock-indicator-api.onrender.com/docs)** ·
[Readiness](https://stock-indicator-api.onrender.com/ready) ·
[Dataset coverage](https://stock-indicator-api.onrender.com/dataset)

The hosted service uses Render, Neon PostgreSQL and Upstash Redis. In Swagger UI,
select **Authorize** and enter a provisioned API key to use authenticated endpoints.
Render's [free instances](https://render.com/docs/free) sleep after 15 minutes of
inactivity; the first request can take about a minute to resume the service.

## Architecture

This is a modular monolith deployed as one API service.

| Layer | Responsibility |
| --- | --- |
| `app/routers/` | HTTP endpoints and request/response handling |
| `app/schemas/` | Typed query models and screening validation |
| `app/dependencies/` | API-key authentication, quota enforcement and dependency factories |
| `app/services/` | Tier authorization, indicator computation and screening |
| `app/repositories/` | Account lookups and an immutable, per-symbol stock index |
| `app/cache/` | Redis response cache behind a small interface |
| `app/core/` | Configuration, exceptions, logging, metrics and key hashing |
| `database.py`, `models.py` | SQLAlchemy engine and account schema |
| `indicators.py` | Shared numerical indicator functions |
| `migrations/` | Versioned database schema changes |
| `scripts/` | Startup, account administration and service verification |

The stock snapshot stays in Parquet. PostgreSQL stores accounts, while Redis owns quota
state and cached responses. One immutable snapshot and one Redis connection pool are
created per API process.

## Run locally with Docker

Install Docker with Compose, then run from the repository root:

```bash
docker compose up --build -d
docker compose exec api python -m scripts.manage_users create --username demo --tier premium
```

Save the generated API key. Open **http://localhost:8000/docs**, click **Authorize**, and
paste the key. No accounts are created automatically.

Account commands also include `list`, `rotate --username NAME`,
`set-tier --username NAME --tier TIER` and `revoke --username NAME`.
Keys contain 256 bits of randomness; only their SHA-256 lookup hashes are stored.

## Run with Python

Use **Python 3.12**. Start local PostgreSQL and Redis using Compose, or configure managed
services in a private `.env` file:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d postgres redis
python -m alembic upgrade head
python -m scripts.manage_users create --username demo --tier premium
python -m scripts.start
```

The start command applies pending migrations and binds Uvicorn to `0.0.0.0:$PORT`
(default `8000`). Use `uvicorn app.main:app --reload` during development after migrating.

## API

All analytical endpoints require an `api-key` header.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/sma`, `/ema`, `/rsi`, `/macd`, `/bollinger` | Indicator rows for a symbol and inclusive date range |
| POST | `/screen` | AND/OR conditions on the latest available bar per symbol |
| GET | `/status` | Authenticated account usage from the enforced Redis quota |
| GET | `/metrics` | Authenticated per-process JSON or Prometheus metrics |
| GET | `/health` | Process liveness |
| GET | `/ready` | Dataset, account schema/database and Redis readiness |
| GET | `/dataset`, `/symbols` | Public snapshot metadata and ticker discovery |
| GET | `/docs` | Swagger UI with API-key authorization |

Indicator queries accept `symbol`, `start` and `end`, plus their indicator parameters.
Symbols are normalized to uppercase. Response dates are ISO calendar dates.

Example screening body:

```json
{
  "logic": "AND",
  "conditions": [
    {
      "indicator": "PRICE",
      "operator": ">",
      "reference": {"indicator": "SMA", "period": 20}
    },
    {"indicator": "RSI", "period": 14, "operator": "<", "value": 70}
  ]
}
```

Operators: `<`, `<=`, `>`, `>=`, `==`, `!=`.
A condition has exactly one scalar `value` or indicator `reference`.
Up to ten conditions are accepted. Indicator periods are bounded at 1,095 observations.

## Tiers and calculation conventions

| Tier | Indicators | Returned history | Daily quota | Screening |
| --- | --- | --- | --- | --- |
| Free | SMA, EMA | 90 calendar days | 50 | No |
| Pro | SMA, EMA, RSI, MACD | 365 calendar days | 500 | Yes, excluding Bollinger |
| Premium | All five | 1,095 calendar days | Unlimited | All supported indicators |

History permissions are measured from the actual snapshot end date, rather than today's
date. They restrict returned rows. Earlier snapshot rows may be used internally for
indicator warm-up, including screening. Calculations therefore do not change when a
client changes only its requested output start date.

- SMA uses a complete rolling observation window.
- EMA and MACD use normalized exponential means (`adjust=True`).
- RSI uses **Cutler RSI**, with simple rolling means of N price changes. The first N
  rows are unavailable; an unchanged price window returns 50, only gains return 100,
  and only losses return 0. This convention differs from Wilder smoothing.
- Bollinger Bands use sample standard deviation (`ddof=1`) and a period of at least two.
- Screening evaluates each symbol's own latest bar. A missing indicator value makes
  that condition false.

## Operational behavior

Daily quotas reset at **00:00 UTC**. Authenticated analytical attempts reaching quota
enforcement consume one request, including cache hits and requests that later fail
authorization or computation. Requests rejected at the quota limit do not increase it.
Status and metrics reads do not consume analytical quota.

A Redis Lua operation checks the quota, increments it and sets its midnight expiry
atomically. Redis quota failures return `503`; exhausted quotas return `429` with
`Retry-After`. Cache failures allow recomputation.

Response cache keys include the snapshot content fingerprint and computation version.
Authorization runs before cache access. Credentials and usernames are absent from cache
keys. Dates and numerical values have the same JSON representation on cache hits and misses.

One worker and two Polars threads are the runtime defaults. Concurrent cold screening
calculations are bounded; overload returns `503` with `Retry-After`.
Metrics reset when the process restarts and are not aggregated across replicas.
Request IDs and structured JSON logs provide request correlation.

## Development

```bash
pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

Local tests use a temporary SQLite database and fake Redis. The GitHub Actions workflow
runs the suite against dedicated PostgreSQL and Redis services, checks schema drift,
and builds the production Docker image. Set `TEST_DATABASE_URL` and `TEST_REDIS_URL`
only for databases reserved for tests.

Load testing uses `locustfile.py`. Set `LOCUST_API_KEY` to a premium account key before
running Locust. Service verification is available through `python -m scripts.smoke_test`
with `SMOKE_API_KEY` set to a premium account key.
