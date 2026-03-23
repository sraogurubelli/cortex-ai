"""Unit tests for ``cortex.api.routes.models``."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from cortex.orchestration.models.health import HealthCheckResult, HealthStatus


@pytest.mark.asyncio
async def test_list_models_requires_auth(client: AsyncClient):
    res = await client.get("/api/v1/models")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_models_returns_model_info_shape(authed_client: AsyncClient):
    res = await authed_client.get("/api/v1/models")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if data:
        m = data[0]
        for key in (
            "name",
            "provider",
            "supports_tools",
            "supports_vision",
            "supports_streaming",
            "context_window",
            "max_output_tokens",
            "tags",
        ):
            assert key in m


@pytest.mark.asyncio
async def test_list_providers_mocks_health(authed_client: AsyncClient):
    fake = HealthCheckResult(status=HealthStatus.UNKNOWN, latency_ms=12.5)

    with patch(
        "cortex.api.routes.models.check_provider_health",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        res = await authed_client.get("/api/v1/models/providers")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_create_provider_registers_and_response_shape(authed_client: AsyncClient):
    with (
        patch(
            "cortex.api.routes.models.provider_registry.register",
            MagicMock(),
        ) as mock_reg,
        patch(
            "cortex.api.routes.models.check_provider_health",
            new_callable=AsyncMock,
            return_value=HealthCheckResult(status=HealthStatus.UNKNOWN),
        ),
    ):
        res = await authed_client.post(
            "/api/v1/models/providers",
            json={
                "name": "unit-openai",
                "provider_type": "openai",
                "api_key": "",
                "models": ["gpt-4o"],
                "priority": 1,
            },
        )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "unit-openai"
    assert body["provider_type"] == "openai"
    assert body["models"] == ["gpt-4o"]
    assert body["health_status"] == "unknown"
    assert "uid" in body
    mock_reg.assert_called_once()


@pytest.mark.asyncio
async def test_update_delete_provider_not_found(authed_client: AsyncClient):
    r = await authed_client.put(
        "/api/v1/models/providers/no-such-provider",
        json={"name": "x"},
    )
    assert r.status_code == 404

    d = await authed_client.delete("/api/v1/models/providers/no-such-provider")
    assert d.status_code == 404


@pytest.mark.asyncio
async def test_test_model_endpoint_mocks_llm(authed_client: AsyncClient):
    mock_msg = MagicMock()
    mock_msg.content = "Hello from mock"

    with patch("cortex.orchestration.llm.LLMClient") as MockClient:
        inst = MockClient.return_value
        inst.ainvoke = AsyncMock(return_value=mock_msg)
        res = await authed_client.post(
            "/api/v1/models/test",
            json={"model": "gpt-4o", "prompt": "Hi"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["response"] == "Hello from mock"
    assert "latency_ms" in body
