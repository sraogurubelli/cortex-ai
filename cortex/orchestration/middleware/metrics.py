"""
Session-aware Prometheus metrics middleware.

Ported from ml-infra's MetricsMiddleware pattern. Tracks:
  - Active session count (gauge)
  - Session response time histogram (by route and model)
  - Session error counter

Skips SSE streaming endpoints to avoid inflating latency histograms.

Usage::

    from cortex.orchestration.middleware.metrics import SessionMetricsMiddleware

    app.add_middleware(SessionMetricsMiddleware)
"""

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram

    ACTIVE_SESSIONS = Gauge(
        "cortex_active_sessions",
        "Number of currently active agent sessions",
        ["model"],
    )
    SESSION_DURATION = Histogram(
        "cortex_session_duration_seconds",
        "Session response time in seconds",
        ["route", "model", "status"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
    )
    SESSION_ERRORS = Counter(
        "cortex_session_errors_total",
        "Total number of session errors",
        ["route", "error_type"],
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.debug("prometheus_client not installed; metrics middleware disabled")


class SessionMetricsMiddleware:
    """ASGI middleware that tracks session-level Prometheus metrics.

    Skips requests with ``Accept: text/event-stream`` (SSE) since those
    are long-lived streaming connections that would distort histograms.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not _PROMETHEUS_AVAILABLE:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        accept = headers.get(b"accept", b"").decode("utf-8", errors="ignore")
        if "text/event-stream" in accept:
            await self.app(scope, receive, send)
            return

        route = scope.get("path", "unknown")
        model = "unknown"

        ACTIVE_SESSIONS.labels(model=model).inc()
        start = time.monotonic()
        status = "ok"

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            status = "error"
            SESSION_ERRORS.labels(route=route, error_type=type(exc).__name__).inc()
            raise
        finally:
            elapsed = time.monotonic() - start
            ACTIVE_SESSIONS.labels(model=model).dec()
            SESSION_DURATION.labels(route=route, model=model, status=status).observe(elapsed)


class SessionMetricsHook:
    """SessionEventHook implementation that records Prometheus metrics.

    Attach as an event hook to ``SessionConfig.event_hooks`` to get
    per-session metrics with accurate model labels::

        from cortex.orchestration.middleware.metrics import SessionMetricsHook

        config = SessionConfig(
            ...,
            event_hooks=[SessionMetricsHook()],
        )
    """

    async def on_session_start(self, config, metadata: dict) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        ACTIVE_SESSIONS.labels(model=config.model).inc()

    async def on_session_complete(self, config, result, metadata: dict) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        ACTIVE_SESSIONS.labels(model=config.model).dec()
        SESSION_DURATION.labels(
            route=f"/chat/{config.mode}",
            model=config.model,
            status="ok",
        ).observe(result.duration_ms / 1000)

    async def on_session_error(self, config, error: Exception, metadata: dict) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        ACTIVE_SESSIONS.labels(model=config.model).dec()
        SESSION_ERRORS.labels(
            route=f"/chat/{config.mode}",
            error_type=type(error).__name__,
        ).inc()
