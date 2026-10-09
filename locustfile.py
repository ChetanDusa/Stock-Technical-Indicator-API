"""Successful analytics workload; supply the API key through the environment."""

import os

from locust import HttpUser, between, task


class StockAPIUser(HttpUser):
    wait_time = between(0.2, 0.8)

    def on_start(self):
        key = os.environ.get("LOCUST_API_KEY")
        if not key:
            raise RuntimeError("Set LOCUST_API_KEY to a premium account's API key")
        self.headers = {"api-key": key}
        self.params = {"symbol": "INFY", "start": "2025-04-01", "end": "2025-06-30"}

    @task(3)
    def sma(self):
        self.client.get("/sma", params=self.params, headers=self.headers, name="/sma")

    @task(2)
    def ema(self):
        self.client.get("/ema", params=self.params, headers=self.headers, name="/ema")

    @task(1)
    def macd(self):
        self.client.get("/macd", params=self.params, headers=self.headers, name="/macd")

    @task(1)
    def screen(self):
        self.client.post(
            "/screen",
            headers=self.headers,
            json={
                "conditions": [
                    {
                        "indicator": "PRICE",
                        "operator": ">",
                        "reference": {"indicator": "SMA", "period": 20},
                    }
                ]
            },
            name="/screen",
        )
