"""Observability middleware for correlation IDs, request timing, structured logging, and metrics."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger, request_id_ctx
from app.core.metrics import metrics

logger = get_logger("app.request")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Correlation IDs, request metrics and structured access logs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Correlation / Request ID: propagate incoming or generate new UUID4
        incoming_req_id = request.headers.get("X-Request-ID")
        if incoming_req_id and incoming_req_id.strip():
            # Sanitize to alphanumeric, dashes, underscores, max length 64
            clean_id = "".join(
                c for c in incoming_req_id if c.isascii() and (c.isalnum() or c in "-_")
            )[:64]
            request_id = clean_id if clean_id else str(uuid.uuid4())
        else:
            request_id = str(uuid.uuid4())

        # Bind to contextvar and request state
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            # Attach correlation ID to response headers
            response.headers["X-Request-ID"] = request_id

            # Route templates keep metric cardinality bounded for arbitrary 404 paths.
            metric_path = getattr(request.scope.get("route"), "path", "__unmatched__")
            logger.info(
                f"{request.method} {request.url.path} {response.status_code} - {latency_ms:.2f}ms",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                },
            )

            # Record metrics
            metrics.record_request(
                method=request.method,
                path=metric_path,
                status_code=response.status_code,
                duration_ms=latency_ms,
            )

            return response

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            logger.error(
                f"Unhandled exception processing {request.method} {request.url.path}: {type(exc).__name__}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "latency_ms": latency_ms,
                    "error_type": type(exc).__name__,
                },
            )
            metrics.record_request(
                method=request.method,
                path=getattr(request.scope.get("route"), "path", "__unmatched__"),
                status_code=500,
                duration_ms=latency_ms,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers={"X-Request-ID": request_id},
            )

        finally:
            request_id_ctx.reset(token)
