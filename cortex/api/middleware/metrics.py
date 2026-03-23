"""
Optional Prometheus metrics middleware for FastAPI.

Tracks:
- Active HTTP requests (gauge)
- Request latency (histogram)
- Request count by method/path/status (counter)

Enable by setting PROMETHEUS_ENABLED=true in environment.
Metrics are exposed at GET /metrics.
"""

import os
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def is_prometheus_enabled() -> bool:
    return os.getenv("PROMETHEUS_ENABLED", "").lower() in ("true", "1", "yes")


def _sanitize_path(path: str) -> str:
    """Collapse path parameters to reduce cardinality."""
    parts = path.strip("/").split("/")
    sanitized = []
    for i, part in enumerate(parts):
        if i > 0 and parts[i - 1] in (
            "projects", "agents", "skills", "conversations",
            "documents", "traces", "providers",
        ):
            sanitized.append("{id}")
        else:
            sanitized.append(part)
    return "/" + "/".join(sanitized)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Collects HTTP metrics and exposes them at /metrics."""

    def __init__(self, app):
        super().__init__(app)
        try:
            from prometheus_client import Counter, Gauge, Histogram
            self._request_count = Counter(
                "cortex_http_requests_total",
                "Total HTTP requests",
                ["method", "path", "status"],
            )
            self._request_latency = Histogram(
                "cortex_http_request_duration_seconds",
                "HTTP request latency in seconds",
                ["method", "path"],
                buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            )
            self._active_requests = Gauge(
                "cortex_http_active_requests",
                "Currently active HTTP requests",
                ["method"],
            )
            self._available = True
        except ImportError:
            self._available = False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._available:
            return await call_next(request)

        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = _sanitize_path(request.url.path)

        self._active_requests.labels(method=method).inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
            elapsed = time.perf_counter() - start
            self._request_count.labels(method=method, path=path, status=response.status_code).inc()
            self._request_latency.labels(method=method, path=path).observe(elapsed)
            return response
        except Exception:
            elapsed = time.perf_counter() - start
            self._request_count.labels(method=method, path=path, status=500).inc()
            self._request_latency.labels(method=method, path=path).observe(elapsed)
            raise
        finally:
            self._active_requests.labels(method=method).dec()


def add_metrics_endpoint(app):
    """Add GET /metrics endpoint that returns Prometheus text format."""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from starlette.responses import Response as StarletteResponse

        @app.get("/metrics", tags=["observability"], include_in_schema=False)
        async def metrics():
            return StarletteResponse(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )
    except ImportError:
        pass
