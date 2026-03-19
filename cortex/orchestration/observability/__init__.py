"""
Cortex Orchestration Observability Module.

Provides utilities for debugging and monitoring:
- Model usage tracking
- HTTP request/response logging for LLM provider calls
- OpenTelemetry distributed tracing for multi-agent workflows
"""

# Usage tracking (from sibling module)
from cortex.orchestration.usage_tracking import (
    ModelUsageTracker,
    ModelUsage,
    resolve_model_name,
)

# TODO: http_logging module not yet implemented
# from .http_logging import (
#     enable_http_logging,
#     disable_http_logging,
#     is_http_logging_enabled,
#     http_logging_context,
# )

from cortex.orchestration.observability.telemetry import (
    initialize_telemetry,
    get_tracer,
    is_telemetry_enabled,
    shutdown_telemetry,
)

__all__ = [
    # Model Usage Tracking
    "ModelUsageTracker",
    "ModelUsage",
    "resolve_model_name",
    # HTTP Logging (not yet implemented)
    # "enable_http_logging",
    # "disable_http_logging",
    # "is_http_logging_enabled",
    # "http_logging_context",
    # OpenTelemetry
    "initialize_telemetry",
    "get_tracer",
    "is_telemetry_enabled",
    "shutdown_telemetry",
]
