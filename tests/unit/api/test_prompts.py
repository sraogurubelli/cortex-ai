"""Unit tests for ``cortex.api.routes.prompts``."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_prompts_requires_auth(client: AsyncClient):
    res = await client.get("/api/v1/prompts")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_all_prompts_response_shape(authed_client: AsyncClient):
    res = await authed_client.get("/api/v1/prompts")
    assert res.status_code == 200
    body = res.json()
    assert "prompts" in body
    assert "total" in body
    assert isinstance(body["prompts"], list)
    assert body["total"] == len(body["prompts"])
    if body["prompts"]:
        p = body["prompts"][0]
        assert "key" in p and "template" in p


@pytest.mark.asyncio
async def test_get_prompt_by_key_not_found(authed_client: AsyncClient):
    res = await authed_client.get("/api/v1/prompts/definitely.missing.prompt.key")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_prompt_validation_empty_template(authed_client: AsyncClient):
    res = await authed_client.put(
        "/api/v1/prompts/unit.test.dynamic",
        json={"template": ""},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_update_get_roundtrip(authed_client: AsyncClient):
    key = "unit.test.dynamic.roundtrip"
    tpl = "Hello {{ name }}!"
    put = await authed_client.put(
        f"/api/v1/prompts/{key}",
        json={"template": tpl},
    )
    assert put.status_code == 200
    assert put.json() == {"key": key, "template": tpl}

    got = await authed_client.get(f"/api/v1/prompts/{key}")
    assert got.status_code == 200
    assert got.json()["template"] == tpl


@pytest.mark.asyncio
async def test_render_stored_prompt(authed_client: AsyncClient):
    key = "unit.test.render.me"
    await authed_client.put(
        f"/api/v1/prompts/{key}",
        json={"template": "Value: {{ value }}"},
    )
    res = await authed_client.post(
        f"/api/v1/prompts/{key}/render",
        json={"variables": {"value": 42}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["key"] == key
    assert body["rendered"] == "Value: 42"


@pytest.mark.asyncio
async def test_render_inline_template(authed_client: AsyncClient):
    res = await authed_client.post(
        "/api/v1/prompts/any.key/render",
        json={"template": "{{ a }} + {{ b }}", "variables": {"a": 1, "b": 2}},
    )
    assert res.status_code == 200
    assert res.json()["rendered"] == "1 + 2"


@pytest.mark.asyncio
async def test_render_invalid_jinja_returns_422(authed_client: AsyncClient):
    res = await authed_client.post(
        "/api/v1/prompts/x/render",
        json={"template": "{% unknown_tag %}", "variables": {}},
    )
    assert res.status_code == 422
    assert "rendering failed" in res.json()["detail"].lower()
