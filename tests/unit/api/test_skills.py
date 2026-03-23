"""Unit tests for ``cortex.api.routes.skills``."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_skills_requires_auth(client: AsyncClient):
    res = await client.get("/api/v1/skills")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_skill_validation_missing_content(authed_client: AsyncClient):
    res = await authed_client.post(
        "/api/v1/skills",
        json={"name": "N", "skill_md_content": ""},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_get_list_skill_schema(authed_client: AsyncClient):
    res = await authed_client.post(
        "/api/v1/skills",
        json={
            "name": "Unit Skill",
            "description": "d",
            "skill_md_content": "# Skill\nBody",
            "enabled": True,
            "metadata": {"x": "y"},
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Unit Skill"
    assert body["skill_md_content"] == "# Skill\nBody"
    assert body["metadata"] == {"x": "y"}
    assert body["enabled"] is True
    assert "uid" in body
    uid = body["uid"]

    g = await authed_client.get(f"/api/v1/skills/{uid}")
    assert g.status_code == 200
    assert g.json()["uid"] == uid

    lst = await authed_client.get("/api/v1/skills")
    assert lst.status_code == 200
    assert isinstance(lst.json(), list)
    assert any(s["uid"] == uid for s in lst.json())


@pytest.mark.asyncio
async def test_get_update_delete_skill_not_found(authed_client: AsyncClient):
    missing = await authed_client.get("/api/v1/skills/bad-skill-uid")
    assert missing.status_code == 404

    bad_put = await authed_client.put(
        "/api/v1/skills/bad-skill-uid",
        json={"name": "x"},
    )
    assert bad_put.status_code == 404

    bad_del = await authed_client.delete("/api/v1/skills/bad-skill-uid")
    assert bad_del.status_code == 404

    created = await authed_client.post(
        "/api/v1/skills",
        json={"name": "ToUpdate", "skill_md_content": "md"},
    )
    assert created.status_code == 201
    uid = created.json()["uid"]

    upd = await authed_client.put(
        f"/api/v1/skills/{uid}",
        json={"name": "Renamed", "enabled": False},
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "Renamed"
    assert upd.json()["enabled"] is False

    dl = await authed_client.delete(f"/api/v1/skills/{uid}")
    assert dl.status_code == 204


@pytest.mark.asyncio
async def test_attach_list_detach_agent_skills(authed_client: AsyncClient):
    agent_res = await authed_client.post(
        "/api/v1/projects/proj_skills_unit/agents",
        json={"name": "Agent", "model": "gpt-4o"},
    )
    assert agent_res.status_code == 201
    agent_uid = agent_res.json()["uid"]

    skill_res = await authed_client.post(
        "/api/v1/skills",
        json={"name": "Linked", "skill_md_content": "x"},
    )
    assert skill_res.status_code == 201
    skill_uid = skill_res.json()["uid"]

    att = await authed_client.post(
        f"/api/v1/agents/{agent_uid}/skills/{skill_uid}",
    )
    assert att.status_code == 201
    assert att.json()["message"] == "Skill attached"

    dup = await authed_client.post(
        f"/api/v1/agents/{agent_uid}/skills/{skill_uid}",
    )
    assert dup.status_code == 201
    assert dup.json()["message"] == "Skill already attached"

    listed = await authed_client.get(f"/api/v1/agents/{agent_uid}/skills")
    assert listed.status_code == 200
    skills = listed.json()
    assert len(skills) == 1
    assert skills[0]["uid"] == skill_uid

    det = await authed_client.delete(
        f"/api/v1/agents/{agent_uid}/skills/{skill_uid}",
    )
    assert det.status_code == 204

    empty = await authed_client.get(f"/api/v1/agents/{agent_uid}/skills")
    assert empty.status_code == 200
    assert empty.json() == []
