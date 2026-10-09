"""Lightweight, thread-safe, zero-dependency application metrics."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Tuple


class MetricsCollector:
    """Collects application performance, throughput, error, and cache metrics in-memory."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_counts: Dict[Tuple[str, str, int], int] = {}
        self._total_requests: int = 0
        self._total_errors: int = 0
        self._total_latency_ms: float = 0.0
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        """Record an HTTP request outcome and latency."""
        with self._lock:
            key = (method, path, status_code)
            self._request_counts[key] = self._request_counts.get(key, 0) + 1
            self._total_requests += 1
            self._total_latency_ms += duration_ms
            if status_code >= 400:
                self._total_errors += 1

    def record_cache_hit(self) -> None:
        """Increment cache hit counter."""
        with self._lock:
            self._cache_hits += 1

    def record_cache_miss(self) -> None:
        """Increment cache miss counter."""
        with self._lock:
            self._cache_misses += 1

    def get_summary(self) -> Dict[str, Any]:
        """Return a structured JSON dictionary of all current metrics."""
        with self._lock:
            avg_latency = (
                round(self._total_latency_ms / self._total_requests, 2)
                if self._total_requests > 0
                else 0.0
            )
            total_cache_ops = self._cache_hits + self._cache_misses
            cache_hit_ratio = (
                round(self._cache_hits / total_cache_ops, 4) if total_cache_ops > 0 else 0.0
            )
            return {
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "avg_latency_ms": avg_latency,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_ratio": cache_hit_ratio,
                "requests_by_endpoint": [
                    {"method": k[0], "path": k[1], "status_code": k[2], "count": v}
                    for k, v in self._request_counts.items()
                ],
            }

    def to_prometheus_text(self) -> str:
        """Export metrics in standard Prometheus exposition text format."""
        with self._lock:
            lines: List[str] = [
                "# HELP http_requests_total Total number of HTTP requests processed",
                "# TYPE http_requests_total counter",
            ]
            for (method, path, status_code), count in sorted(self._request_counts.items()):
                lines.append(
                    f'http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}'
                )

            lines.extend(
                [
                    "# HELP http_requests_latency_ms_total Cumulative latency of HTTP requests in milliseconds",
                    "# TYPE http_requests_latency_ms_total counter",
                    f"http_requests_latency_ms_total {self._total_latency_ms:.2f}",
                    "# HELP http_requests_errors_total Total number of HTTP requests with status >= 400",
                    "# TYPE http_requests_errors_total counter",
                    f"http_requests_errors_total {self._total_errors}",
                    "# HELP cache_hits_total Total Redis cache hits",
                    "# TYPE cache_hits_total counter",
                    f"cache_hits_total {self._cache_hits}",
                    "# HELP cache_misses_total Total Redis cache misses",
                    "# TYPE cache_misses_total counter",
                    f"cache_misses_total {self._cache_misses}",
                ]
            )

            return "\n".join(lines) + "\n"


# Global singleton instance
metrics = MetricsCollector()
