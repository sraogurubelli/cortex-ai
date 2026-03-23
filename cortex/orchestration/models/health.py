"""
Provider health checks.

Lightweight async probes to verify LLM providers are reachable
and returning valid responses.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    status: HealthStatus
    latency_ms: float = 0.0
    error: str = ""
    provider: str = ""


_PROVIDER_HEALTH_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
}


async def check_provider_health(
    provider: str,
    api_key: str = "",
    base_url: str = "",
    timeout: float = 10.0,
) -> HealthCheckResult:
    """Probe a provider's API endpoint for reachability.

    Uses a lightweight HEAD/GET to the provider's model list endpoint.
    Does NOT make an inference call.
    """
    url = base_url or _PROVIDER_HEALTH_URLS.get(provider, "")
    if not url:
        return HealthCheckResult(
            status=HealthStatus.UNKNOWN,
            provider=provider,
            error=f"No health URL for provider: {provider}",
        )

    headers: dict[str, str] = {}
    if api_key:
        if provider == "anthropic":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            latency = (time.monotonic() - start) * 1000

            if resp.status_code < 500:
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency,
                    provider=provider,
                )
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                latency_ms=latency,
                provider=provider,
                error=f"HTTP {resp.status_code}",
            )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency,
            provider=provider,
            error=str(exc),
        )
