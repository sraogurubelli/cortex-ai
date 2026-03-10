"""
Cortex Orchestration Observability Module.

Provides utilities for debugging and monitoring:
- HTTP request/response logging for LLM provider calls
- OpenTelemetry distributed tracing for multi-agent workflows
"""

from cortex.orchestration.observability.http_logging import (
    enable_http_logging,
    disable_http_logging,
    is_http_logging_enabled,
    http_logging_context,
)

from cortex.orchestration.observability.telemetry import (
    initialize_telemetry,
    get_tracer,
    is_telemetry_enabled,
    shutdown_telemetry,
)

__all__ = [
    # HTTP Logging
    "enable_http_logging",
    "disable_http_logging",
    "is_http_logging_enabled",
    "http_logging_context",
    # OpenTelemetry
    "initialize_telemetry",
    "get_tracer",
    "is_telemetry_enabled",
    "shutdown_telemetry",
]
