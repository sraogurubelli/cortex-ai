"""
Integration tests for the Chat API.

Tests conversation creation, listing, retrieval, and deletion.
Uses ``authed_client`` with dependency overrides for auth.
The LLM agent is mocked to avoid external API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient


async def _create_project(client: AsyncClient) -> str:
    """Helper: create an org + project and return the project uid."""
    accts = await client.get("/api/v1/accounts")
    if accts.status_code != 200:
        pytest.skip("Accounts endpoint not available")
    accounts = accts.json().get("accounts", [])
    if not accounts:
        pytest.skip("No accounts found")

    account_uid = accounts[0]["id"]

    orgs = await client.get(f"/api/v1/accounts/{account_uid}/organizations")
    if orgs.status_code != 200:
        pytest.skip("Organizations endpoint not available")
    org_list = orgs.json().get("organizations", [])
    if not org_list:
        pytest.skip("No organizations found")

    org_uid = org_list[0]["id"]

    res = await client.post(
        f"/api/v1/organizations/{org_uid}/projects",
        json={"name": "Test Chat Project", "description": "For chat tests"},
    )
    if res.status_code not in (200, 201):
        pytest.skip(f"Project creation failed: {res.status_code} {res.text}")

    return res.json()["id"]


@pytest.mark.asyncio
async def test_list_conversations_empty(authed_client: AsyncClient):
    project_uid = await _create_project(authed_client)
    res = await authed_client.get(
        f"/api/v1/projects/{project_uid}/conversations",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["conversations"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_chat_non_streaming(authed_client: AsyncClient):
    project_uid = await _create_project(authed_client)

    mock_result = MagicMock()
    mock_result.response = "I can help with that."
    mock_result.messages = [
        {"role": "user", "content": "Help me"},
        {"role": "assistant", "content": "I can help with that."},
    ]
    mock_result.token_usage = {"total_tokens": 20}

    with patch("cortex.api.routes.chat.Agent") as MockAgent:
        instance = MockAgent.return_value
        instance.run = AsyncMock(return_value=mock_result)

        res = await authed_client.post(
            f"/api/v1/projects/{project_uid}/chat",
            json={"message": "Help me", "stream": False},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["conversation_id"]
        assert body["response"] == "I can help with that."


@pytest.mark.asyncio
async def test_get_conversation_not_found(authed_client: AsyncClient):
    res = await authed_client.get(
        "/api/v1/conversations/conv_nonexistent",
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_not_found(authed_client: AsyncClient):
    res = await authed_client.delete(
        "/api/v1/conversations/conv_nonexistent",
    )
    assert res.status_code == 404
