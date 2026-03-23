"""
Integration tests for the Documents / RAG API.

Mocks the RAG services (Qdrant / embeddings) to test endpoint logic
in isolation.  Uses ``authed_client`` for auth.
"""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient


async def _create_project(client: AsyncClient) -> str:
    """Create a test project and return its uid."""
    accts = await client.get("/api/v1/accounts")
    if accts.status_code != 200:
        pytest.skip("Accounts endpoint not available")
    accounts = accts.json().get("accounts", [])
    if not accounts:
        pytest.skip("No accounts")

    account_uid = accounts[0]["id"]
    orgs = await client.get(f"/api/v1/accounts/{account_uid}/organizations")
    if orgs.status_code != 200:
        pytest.skip("Organizations endpoint not available")
    org_list = orgs.json().get("organizations", [])
    if not org_list:
        pytest.skip("No organizations")

    org_uid = org_list[0]["id"]
    res = await client.post(
        f"/api/v1/organizations/{org_uid}/projects",
        json={"name": "Doc Test Project", "description": "For doc tests"},
    )
    if res.status_code not in (200, 201):
        pytest.skip(f"Project creation failed: {res.text}")

    return res.json()["id"]


def _mock_rag_services():
    """Return a mocked (doc_manager, retriever) pair."""
    doc_manager = AsyncMock()
    doc_manager.ingest_document = AsyncMock(return_value=3)
    doc_manager.list_documents = AsyncMock(return_value=([], 0))
    doc_manager.delete_document = AsyncMock()

    retriever = AsyncMock()
    retriever.search = AsyncMock(return_value=[])
    retriever.format_results = MagicMock(return_value="")

    return doc_manager, retriever


@pytest.mark.asyncio
async def test_upload_document(authed_client: AsyncClient):
    project_uid = await _create_project(authed_client)
    dm, ret = _mock_rag_services()

    with patch(
        "cortex.api.routes.documents._get_rag_services",
        new_callable=AsyncMock,
        return_value=(dm, ret),
    ):
        file_content = b"This is a test document about AI agents."
        res = await authed_client.post(
            f"/api/v1/projects/{project_uid}/documents",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["doc_id"].startswith("doc_")
        assert body["chunks"] == 3


@pytest.mark.asyncio
async def test_list_documents(authed_client: AsyncClient):
    project_uid = await _create_project(authed_client)
    dm, ret = _mock_rag_services()
    dm.list_documents = AsyncMock(
        return_value=(
            [
                {
                    "id": "doc_abc123",
                    "content": "Some content here",
                    "metadata": {"filename": "readme.md"},
                }
            ],
            1,
        )
    )

    with patch(
        "cortex.api.routes.documents._get_rag_services",
        new_callable=AsyncMock,
        return_value=(dm, ret),
    ):
        res = await authed_client.get(
            f"/api/v1/projects/{project_uid}/documents",
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["documents"][0]["id"] == "doc_abc123"


@pytest.mark.asyncio
async def test_search_documents(authed_client: AsyncClient):
    project_uid = await _create_project(authed_client)
    dm, ret = _mock_rag_services()

    mock_result = MagicMock()
    mock_result.id = "chunk_1"
    mock_result.content = "AI agents can collaborate."
    mock_result.score = 0.92
    mock_result.metadata = {"filename": "agents.md"}

    ret.search = AsyncMock(return_value=[mock_result])

    with patch(
        "cortex.api.routes.documents._get_rag_services",
        new_callable=AsyncMock,
        return_value=(dm, ret),
    ):
        res = await authed_client.post(
            f"/api/v1/projects/{project_uid}/search",
            json={"query": "AI agents", "top_k": 5},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["results"][0]["content"] == "AI agents can collaborate."
        assert body["results"][0]["score"] == 0.92


@pytest.mark.asyncio
async def test_delete_document(authed_client: AsyncClient):
    project_uid = await _create_project(authed_client)
    dm, ret = _mock_rag_services()

    with patch(
        "cortex.api.routes.documents._get_rag_services",
        new_callable=AsyncMock,
        return_value=(dm, ret),
    ):
        res = await authed_client.delete(
            f"/api/v1/projects/{project_uid}/documents/doc_abc123",
        )
        assert res.status_code == 204


@pytest.mark.asyncio
async def test_search_no_results(authed_client: AsyncClient):
    project_uid = await _create_project(authed_client)
    dm, ret = _mock_rag_services()
    ret.search = AsyncMock(return_value=[])

    with patch(
        "cortex.api.routes.documents._get_rag_services",
        new_callable=AsyncMock,
        return_value=(dm, ret),
    ):
        res = await authed_client.post(
            f"/api/v1/projects/{project_uid}/search",
            json={"query": "nonexistent topic", "top_k": 3},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 0
        assert body["results"] == []
