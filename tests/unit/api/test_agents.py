"""Unit tests for ``cortex.api.routes.agents``."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_agent_requires_auth(client: AsyncClient):
    res = await client.post(
        "/api/v1/projects/proj_x/agents",
        json={"name": "A", "description": "", "system_prompt": "", "model": "gpt-4o"},
    )
    assert res.status_code == 401
    assert "Authentication" in res.json().get("detail", "")


@pytest.mark.asyncio
async def test_create_agent_validation_empty_name(authed_client: AsyncClient):
    res = await authed_client.post(
        "/api/v1/projects/proj_x/agents",
        json={"name": "", "model": "gpt-4o"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_list_get_agent_response_shape(authed_client: AsyncClient):
    project_uid = "proj_unit_agents_1"
    create = await authed_client.post(
        f"/api/v1/projects/{project_uid}/agents",
        json={
            "name": "Researcher",
            "description": "desc",
            "system_prompt": "be helpful",
            "model": "gpt-4o",
            "tools": ["t1"],
            "skills": ["s1"],
            "middleware": {"k": "v"},
            "max_iterations": 10,
            "temperature": 0,
            "metadata": {"a": 1},
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Researcher"
    assert body["project_uid"] == project_uid
    assert body["model"] == "gpt-4o"
    assert body["tools"] == ["t1"]
    assert body["skills"] == ["s1"]
    assert body["middleware"] == {"k": "v"}
    assert body["max_iterations"] == 10
    assert body["temperature"] == 0
    assert body["metadata"] == {"a": 1}
    assert body["enabled"] is True
    assert "uid" in body and body["uid"]
    for key in (
        "created_by",
        "created_at",
        "updated_at",
        "system_prompt",
        "description",
    ):
        assert key in body

    agent_uid = body["uid"]

    listed = await authed_client.get(f"/api/v1/projects/{project_uid}/agents")
    assert listed.status_code == 200
    agents = listed.json()
    assert isinstance(agents, list)
    assert len(agents) >= 1
    assert any(a["uid"] == agent_uid for a in agents)

    one = await authed_client.get(f"/api/v1/agents/{agent_uid}")
    assert one.status_code == 200
    assert one.json()["uid"] == agent_uid


@pytest.mark.asyncio
async def test_get_agent_not_found(authed_client: AsyncClient):
    res = await authed_client.get("/api/v1/agents/nonexistent-agent-uid-00000")
    assert res.status_code == 404
    assert res.json()["detail"] == "Agent not found"


@pytest.mark.asyncio
async def test_update_delete_agent(authed_client: AsyncClient):
    project_uid = "proj_unit_agents_2"
    r = await authed_client.post(
        f"/api/v1/projects/{project_uid}/agents",
        json={"name": "Before", "model": "gpt-4o"},
    )
    assert r.status_code == 201
    uid = r.json()["uid"]

    upd = await authed_client.put(
        f"/api/v1/agents/{uid}",
        json={"name": "After", "enabled": False},
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "After"
    assert upd.json()["enabled"] is False

    deleted = await authed_client.delete(f"/api/v1/agents/{uid}")
    assert deleted.status_code == 204

    missing = await authed_client.get(f"/api/v1/agents/{uid}")
    assert missing.status_code == 404
