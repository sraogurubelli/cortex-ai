"""Unit tests for ModelRouter."""

from unittest.mock import AsyncMock, patch

import pytest

from cortex.orchestration.models.health import HealthCheckResult, HealthStatus
from cortex.orchestration.models.provider_registry import ProviderConfig, ProviderRegistry
from cortex.orchestration.models.router import ModelRouter


@pytest.fixture
def fresh_registry():
    return ProviderRegistry()


@pytest.mark.unit
class TestModelRouterRoute:
    def test_routes_by_capability_vision_skips_non_vision_model(self, fresh_registry):
        fresh_registry.register(
            ProviderConfig(
                name="low",
                provider_type="custom",
                priority=0,
                models=["no-vision-model"],
            )
        )
        fresh_registry.register(
            ProviderConfig(
                name="high",
                provider_type="openai",
                priority=1,
                models=["gpt-4o"],
            )
        )
        router = ModelRouter(registry=fresh_registry)
        result = router.route(model="no-vision-model", require_vision=True)
        assert result is None

        result2 = router.route(model="gpt-4o", require_vision=True)
        assert result2 is not None
        assert result2.model == "gpt-4o"
        assert result2.capabilities.supports_vision is True

    def test_fallback_chain_skips_unhealthy_provider(self, fresh_registry):
        fresh_registry.register(
            ProviderConfig(name="first", provider_type="openai", priority=0, models=["gpt-4o"]),
        )
        fresh_registry.register(
            ProviderConfig(name="second", provider_type="openai", priority=1, models=["gpt-4o-mini"]),
        )
        router = ModelRouter(registry=fresh_registry)
        router._health_cache["first"] = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            provider="openai",
            error="down",
        )
        result = router.route(model="gpt-4o-mini")
        assert result is not None
        assert result.provider.name == "second"
        assert "first (unhealthy)" in result.fallback_chain

    def test_gateway_url_sets_use_gateway_and_effective_base_url(self, fresh_registry):
        fresh_registry.register(
            ProviderConfig(
                name="gw_prov",
                provider_type="openai",
                priority=0,
                models=["gpt-4o"],
                base_url="https://api.openai.com/v1",
                gateway_url="https://gateway.internal/litellm",
            ),
        )
        router = ModelRouter(registry=fresh_registry)
        result = router.route(model="gpt-4o")
        assert result is not None
        assert result.use_gateway is True
        assert result.effective_base_url == "https://gateway.internal/litellm"

    def test_healthy_primary_selected_before_fallback(self, fresh_registry):
        fresh_registry.register(
            ProviderConfig(name="primary", provider_type="openai", priority=0, models=["gpt-4o"]),
        )
        fresh_registry.register(
            ProviderConfig(name="backup", provider_type="openai", priority=1, models=["gpt-4o-mini"]),
        )
        router = ModelRouter(registry=fresh_registry)
        router._health_cache["primary"] = HealthCheckResult(status=HealthStatus.HEALTHY, provider="openai")
        result = router.route(model="gpt-4o")
        assert result.provider.name == "primary"
        assert result.fallback_chain == []


@pytest.mark.unit
class TestModelRouterRouteWithHealth:
    @pytest.mark.asyncio
    async def test_route_with_health_refreshes_cache(self, fresh_registry):
        fresh_registry.register(
            ProviderConfig(name="only", provider_type="openai", priority=0, models=["gpt-4o"]),
        )
        router = ModelRouter(registry=fresh_registry)

        healthy = HealthCheckResult(status=HealthStatus.HEALTHY, provider="openai")
        with patch(
            "cortex.orchestration.models.router.check_provider_health",
            new_callable=AsyncMock,
            return_value=healthy,
        ):
            result = await router.route_with_health(model="gpt-4o")

        assert result is not None
        assert "only" in router._health_cache
        assert router._health_cache["only"].status == HealthStatus.HEALTHY
