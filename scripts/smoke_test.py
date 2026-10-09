"""Exercise a running deployment without printing API keys or response data."""

import argparse
import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    args = parser.parse_args()
    key = os.environ.get("SMOKE_API_KEY")
    if not key:
        parser.error("Set SMOKE_API_KEY to a premium account's API key")
    base_url = args.base_url.rstrip("/")

    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base_url + path,
            data=data,
            headers={"api-key": key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                if response.status != 200:
                    raise SystemExit(f"FAIL {path}: HTTP {response.status}")
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"FAIL {path}: HTTP {exc.code}") from None
        except urllib.error.URLError:
            raise SystemExit(f"FAIL {path}: connection unavailable") from None
        print(f"PASS {path.split('?')[0]}")
        return result

    request("/health")
    request("/ready")
    dataset = request("/dataset")
    end = dataset["end_date"]
    symbols = request("/symbols")
    symbol = "INFY" if "INFY" in symbols else symbols[0]
    start = (datetime.date.fromisoformat(end) - datetime.timedelta(days=30)).isoformat()
    query = urllib.parse.urlencode({"symbol": symbol, "start": start, "end": end})
    for indicator in ("sma", "ema", "rsi", "macd", "bollinger"):
        data = request(f"/{indicator}?{query}")
        if not data:
            raise SystemExit(f"FAIL /{indicator}: no indicator rows returned")
    cold = request(f"/sma?{query}")
    warm = request(f"/sma?{query}")
    if cold != warm:
        raise SystemExit("FAIL /sma: cached response differs")
    result = request(
        "/screen",
        {
            "conditions": [
                {
                    "indicator": "PRICE",
                    "operator": ">",
                    "reference": {"indicator": "SMA", "period": 20},
                }
            ]
        },
    )
    if result["count"] != len(result["matched_symbols"]):
        raise SystemExit("FAIL /screen: inconsistent match count")
    request("/status")
    request("/metrics")
    print("Smoke test completed")


if __name__ == "__main__":
    main()
