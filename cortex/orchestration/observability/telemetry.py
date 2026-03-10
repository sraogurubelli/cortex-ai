"""
OpenTelemetry Distributed Tracing for Cortex-AI.

Provides distributed tracing capabilities for multi-agent workflows:
- TracerProvider setup with resource attributes
- BaggageSpanProcessor for context propagation
- OTLP exporter for sending traces to collectors (Jaeger, Tempo, etc.)
- Health checks and graceful fallback when collector is unavailable

Usage:
    # Initialize once at application startup
    from cortex.orchestration.observability import initialize_telemetry
    initialize_telemetry(service_name="my-app", service_version="1.0.0")

    # Get tracer and create spans
    from cortex.orchestration.observability import get_tracer
    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("my-operation") as span:
        span.set_attribute("custom.key", "value")
        # Your code here

Environment Variables:
    OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint (default: http://localhost:4318)
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: Specific traces endpoint (overrides above)
    OTEL_SERVICE_NAME: Service name (default: cortex-ai)
    OTEL_SERVICE_VERSION: Service version (default: 0.1.0)
    OTEL_DEPLOYMENT_ENV: Deployment environment (default: development)
    DISABLE_OTEL: Set to "true" to disable exporting (still creates spans internally)
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Track global state
_tracer_provider: Optional["TracerProvider"] = None
_telemetry_enabled = False


def initialize_telemetry(
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
    deployment_env: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
) -> bool:
    """
    Initialize OpenTelemetry with TracerProvider and OTLP exporter.

    Args:
        service_name: Name of the service (default: OTEL_SERVICE_NAME env or "cortex-ai")
        service_version: Version of the service (default: OTEL_SERVICE_VERSION env or "0.1.0")
        deployment_env: Deployment environment (default: OTEL_DEPLOYMENT_ENV env or "development")
        otlp_endpoint: OTLP collector endpoint (default: OTEL_EXPORTER_OTLP_ENDPOINT env)

    Returns:
        bool: True if successfully initialized, False if OpenTelemetry packages not available

    Example:
        from cortex.orchestration.observability import initialize_telemetry

        # Simple initialization with defaults
        initialize_telemetry()

        # Custom configuration
        initialize_telemetry(
            service_name="my-agent-app",
            service_version="1.2.3",
            deployment_env="production",
            otlp_endpoint="https://tempo.example.com:4318",
        )
    """
    global _tracer_provider, _telemetry_enabled

    # Check if already initialized
    if _telemetry_enabled:
        logger.info("OpenTelemetry already initialized")
        return True

    # Try to import OpenTelemetry packages
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError as e:
        logger.warning(
            f"OpenTelemetry packages not installed: {e}. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp"
        )
        return False

    # Get configuration from parameters or environment variables
    service_name = service_name or os.environ.get("OTEL_SERVICE_NAME", "cortex-ai")
    service_version = service_version or os.environ.get(
        "OTEL_SERVICE_VERSION", "0.1.0"
    )
    deployment_env = deployment_env or os.environ.get(
        "OTEL_DEPLOYMENT_ENV", "development"
    )

    logger.info(
        f"Initializing OpenTelemetry for {service_name} v{service_version} "
        f"(env: {deployment_env})"
    )

    # Create resource with service metadata
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": deployment_env,
        }
    )

    # Create TracerProvider
    _tracer_provider = TracerProvider(resource=resource)

    # Add BaggageSpanProcessor for context propagation
    _add_baggage_processor(_tracer_provider)

    # Configure OTLP exporter unless explicitly disabled
    disable_otel = os.environ.get("DISABLE_OTEL", "").lower() in ("true", "1", "yes")
    if not disable_otel:
        _configure_otlp_exporter(_tracer_provider, otlp_endpoint)
    else:
        logger.info("OTLP export DISABLED via DISABLE_OTEL environment variable")
        logger.info("Traces will be generated internally but not exported")

    # Set as global provider
    trace.set_tracer_provider(_tracer_provider)
    _telemetry_enabled = True

    logger.info(f"OpenTelemetry initialized successfully for {service_name}")
    return True


def _add_baggage_processor(tracer_provider: "TracerProvider") -> None:
    """
    Add BaggageSpanProcessor to automatically copy baggage to span attributes.

    This allows context propagation across service boundaries. Any baggage items
    (user_id, session_id, custom metadata) will be copied to span attributes.

    Args:
        tracer_provider: TracerProvider to add the processor to
    """
    try:
        from opentelemetry.processor.baggage import (
            BaggageSpanProcessor,
            ALLOW_ALL_BAGGAGE_KEYS,
        )

        baggage_processor = BaggageSpanProcessor(
            baggage_key_predicate=ALLOW_ALL_BAGGAGE_KEYS
        )
        tracer_provider.add_span_processor(baggage_processor)
        logger.info("BaggageSpanProcessor added - baggage will propagate to spans")
    except ImportError:
        logger.warning(
            "BaggageSpanProcessor not available. "
            "Install with: pip install opentelemetry-processor-baggage"
        )


def _configure_otlp_exporter(
    tracer_provider: "TracerProvider", otlp_endpoint: Optional[str] = None
) -> None:
    """
    Configure OTLP exporter to send traces to a collector (Jaeger, Tempo, etc.).

    This function:
    1. Reads OTLP endpoint from parameters or environment variables
    2. Performs health check on the collector
    3. Creates OTLP exporter with appropriate settings
    4. Adds BatchSpanProcessor with optimized batch settings

    Args:
        tracer_provider: TracerProvider to add the exporter to
        otlp_endpoint: OTLP collector endpoint (overrides environment variable)
    """
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    logger.info("Configuring OTLP exporter...")

    try:
        # Get OTLP endpoint from parameters or environment
        if otlp_endpoint is None:
            otlp_endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
            )

        # Construct traces endpoint
        otel_traces_endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", f"{otlp_endpoint}/v1/traces"
        )

        logger.info(f"OTLP traces endpoint: {otel_traces_endpoint}")

        # Set environment variables for OTLP exporter
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", otel_traces_endpoint
        )
        os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_endpoint)

        # Check if collector is available
        collector_available = _check_collector_health(otlp_endpoint)

        # Create OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=otel_traces_endpoint,
            timeout=10,  # 10 second timeout for exports
        )

        # Configure batch processor with settings based on collector health
        if collector_available:
            # Optimized settings for healthy collector
            span_processor = BatchSpanProcessor(
                otlp_exporter,
                schedule_delay_millis=2000,  # Export every 2 seconds
                max_export_batch_size=100,  # Larger batches for efficiency
                export_timeout_millis=30000,  # 30 second export timeout
            )
            logger.info("OTLP exporter configured with optimized settings")
        else:
            # Conservative settings for potentially unavailable collector
            span_processor = BatchSpanProcessor(
                otlp_exporter,
                schedule_delay_millis=5000,  # Longer delay
                max_export_batch_size=50,  # Smaller batches
                export_timeout_millis=30000,
            )
            logger.warning(
                "OTLP collector may be unavailable - configured with conservative settings"
            )
            logger.info("Spans will be buffered and exported when collector is available")

        tracer_provider.add_span_processor(span_processor)
        logger.info("OTLP exporter successfully configured")

    except Exception as e:
        logger.error(f"Failed to configure OTLP exporter: {e}")
        logger.error("Traces will be generated internally but not exported")


def _check_collector_health(endpoint: str) -> bool:
    """
    Check if OTLP collector is available and responding.

    Args:
        endpoint: Base URL of the OTLP collector

    Returns:
        bool: True if collector is available, False otherwise
    """
    try:
        import requests

        health_check_url = endpoint.rstrip("/")
        response = requests.get(health_check_url, timeout=2)
        logger.info(
            f"OTLP collector is available at {health_check_url} "
            f"(Status: {response.status_code})"
        )
        return True
    except ImportError:
        logger.warning("requests package not available for health check")
        return False
    except Exception as e:
        logger.warning(f"OTLP collector not responding at {endpoint}: {e}")
        return False


def get_tracer(name: str) -> "Tracer":
    """
    Get a tracer instance for creating spans.

    Args:
        name: Name of the tracer (typically __name__ of the module)

    Returns:
        Tracer: Tracer instance for creating spans

    Example:
        from cortex.orchestration.observability import get_tracer

        tracer = get_tracer(__name__)

        with tracer.start_as_current_span("my-operation") as span:
            span.set_attribute("user.id", "123")
            span.add_event("Processing started")
            # Your code here
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        # Return no-op tracer if OpenTelemetry not installed
        logger.warning(
            "OpenTelemetry not installed. Install with: "
            "pip install opentelemetry-api opentelemetry-sdk"
        )
        return _NoOpTracer()


def is_telemetry_enabled() -> bool:
    """
    Check if OpenTelemetry telemetry is currently enabled.

    Returns:
        bool: True if telemetry is active, False otherwise
    """
    return _telemetry_enabled


def shutdown_telemetry() -> None:
    """
    Shutdown OpenTelemetry and flush any pending spans.

    Call this before application exit to ensure all spans are exported.

    Example:
        from cortex.orchestration.observability import shutdown_telemetry

        # At application shutdown
        shutdown_telemetry()
    """
    global _tracer_provider, _telemetry_enabled

    if not _telemetry_enabled or _tracer_provider is None:
        return

    try:
        logger.info("Shutting down OpenTelemetry...")
        _tracer_provider.shutdown()
        _telemetry_enabled = False
        logger.info("OpenTelemetry shutdown complete")
    except Exception as e:
        logger.error(f"Error during OpenTelemetry shutdown: {e}")


# No-op tracer for when OpenTelemetry is not installed
class _NoOpTracer:
    """No-op tracer that does nothing when OpenTelemetry is not installed."""

    def start_as_current_span(self, name: str, *args, **kwargs):
        """Return a no-op context manager."""
        return _NoOpSpan()


class _NoOpSpan:
    """No-op span that does nothing."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value: any) -> None:
        pass

    def add_event(self, name: str, attributes: dict = None) -> None:
        pass

    def set_status(self, status: any) -> None:
        pass


# Auto-initialize if environment variable is set
if os.environ.get("CORTEX_TELEMETRY_ENABLED", "").lower() in ("true", "1", "yes"):
    initialize_telemetry()
    logger.info(
        "OpenTelemetry auto-initialized via CORTEX_TELEMETRY_ENABLED environment variable"
    )
