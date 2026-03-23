"""
Model Router — intelligent routing with fallback chains.

Selects the best provider/model combination based on capabilities,
health, and priority, with automatic fallback.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .capabilities import ModelCapabilities, detect_capabilities
from .health import HealthCheckResult, HealthStatus, check_provider_health
from .provider_registry import ProviderConfig, ProviderRegistry, provider_registry

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    """Result of a model routing decision."""

    provider: ProviderConfig
    model: str
    capabilities: ModelCapabilities
    fallback_chain: list[str]
    use_gateway: bool = False
    effective_base_url: str = ""


class ModelRouter:
    """Routes model requests to the best available provider.

    Supports fallback chains so if the primary provider is down the next
    priority provider is selected automatically.
    """

    def __init__(self, registry: Optional[ProviderRegistry] = None) -> None:
        self._registry = registry or provider_registry
        self._health_cache: dict[str, HealthCheckResult] = {}

    async def refresh_health(self) -> dict[str, HealthCheckResult]:
        """Probe all enabled providers and cache results."""
        results: dict[str, HealthCheckResult] = {}
        for p in self._registry.list_enabled():
            result = await check_provider_health(
                provider=p.provider_type,
                api_key=p.api_key,
                base_url=p.base_url,
            )
            results[p.name] = result
        self._health_cache = results
        return results

    def route(
        self,
        model: Optional[str] = None,
        require_tools: bool = False,
        require_vision: bool = False,
        require_streaming: bool = False,
    ) -> Optional[RouteResult]:
        """Select the best provider for the given requirements.

        Args:
            model: Preferred model name (if None, picks best available).
            require_tools: Only consider models with tool support.
            require_vision: Only consider models with vision support.
            require_streaming: Only consider models with streaming.

        Returns:
            RouteResult or None if no provider matches.
        """
        providers = self._registry.list_enabled()
        fallback_chain: list[str] = []

        for p in providers:
            if model:
                caps = detect_capabilities(model)
            else:
                if p.models:
                    caps = detect_capabilities(p.models[0])
                else:
                    caps = detect_capabilities("gpt-4o")

            if require_tools and not caps.supports_tools:
                continue
            if require_vision and not caps.supports_vision:
                continue
            if require_streaming and not caps.supports_streaming:
                continue

            health = self._health_cache.get(p.name)
            if health and health.status == HealthStatus.UNHEALTHY:
                fallback_chain.append(f"{p.name} (unhealthy)")
                continue

            selected_model = model or (p.models[0] if p.models else "gpt-4o")
            use_gw = bool(p.gateway_url)
            effective_url = p.gateway_url if use_gw else p.base_url
            return RouteResult(
                provider=p,
                model=selected_model,
                capabilities=caps,
                fallback_chain=fallback_chain,
                use_gateway=use_gw,
                effective_base_url=effective_url,
            )

        logger.warning("No healthy provider found for model=%s", model)
        return None

    async def route_with_health(
        self,
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[RouteResult]:
        """Route after refreshing health status."""
        await self.refresh_health()
        return self.route(model=model, **kwargs)
