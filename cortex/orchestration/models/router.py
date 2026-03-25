"""
Model Router — intelligent routing with fallback chains and gateway support.

Selects the best provider/model combination based on capabilities,
health, and priority, with automatic fallback. Supports gateway-aware
routing (ported from ml-infra's ``_resolve_provider_model`` pattern).
"""

import logging
import os
from dataclasses import dataclass, field
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
    fallback_chain: list[str] = field(default_factory=list)
    use_gateway: bool = False
    effective_base_url: str = ""
    gateway_model_name: str = ""


class ModelRouter:
    """Routes model requests to the best available provider.

    Supports fallback chains so if the primary provider is down the next
    priority provider is selected automatically.

    Gateway-aware routing (ported from ml-infra):
      When a gateway URL is configured on a provider, the router
      automatically prefixes the model name with ``online/{provider}/``
      (matching ml-infra's LLM Gateway convention) and sets the
      effective base URL to the gateway endpoint. On gateway failure,
      falls back to the next provider in the chain.
    """

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        gateway_enabled: Optional[bool] = None,
    ) -> None:
        """
        Args:
            registry: Provider registry to use.
            gateway_enabled: Override gateway routing. If None, reads
                from ``CORTEX_ENABLE_LLM_GATEWAY`` env var.
        """
        self._registry = registry or provider_registry
        self._health_cache: dict[str, HealthCheckResult] = {}
        if gateway_enabled is not None:
            self._gateway_enabled = gateway_enabled
        else:
            self._gateway_enabled = os.environ.get(
                "CORTEX_ENABLE_LLM_GATEWAY", ""
            ).lower() in ("true", "1", "yes")

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

    @staticmethod
    def _build_gateway_model_name(provider_type: str, model: str) -> str:
        """Build gateway-prefixed model name (``online/{provider}/{model}``).

        This matches ml-infra's LLM Gateway convention.
        """
        if model.startswith("online/"):
            return model
        return f"online/{provider_type}/{model}"

    def route(
        self,
        model: Optional[str] = None,
        require_tools: bool = False,
        require_vision: bool = False,
        require_streaming: bool = False,
        prefer_gateway: Optional[bool] = None,
    ) -> Optional[RouteResult]:
        """Select the best provider for the given requirements.

        Args:
            model: Preferred model name (if None, picks best available).
            require_tools: Only consider models with tool support.
            require_vision: Only consider models with vision support.
            require_streaming: Only consider models with streaming.
            prefer_gateway: Override instance-level gateway preference.

        Returns:
            RouteResult or None if no provider matches.
        """
        use_gateway_routing = prefer_gateway if prefer_gateway is not None else self._gateway_enabled
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

            # Gateway-aware routing
            use_gw = bool(p.gateway_url) and use_gateway_routing
            effective_url = p.gateway_url if use_gw else p.base_url
            gw_model = ""
            if use_gw:
                gw_model = self._build_gateway_model_name(p.provider_type, selected_model)

            return RouteResult(
                provider=p,
                model=selected_model,
                capabilities=caps,
                fallback_chain=fallback_chain,
                use_gateway=use_gw,
                effective_base_url=effective_url,
                gateway_model_name=gw_model,
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
