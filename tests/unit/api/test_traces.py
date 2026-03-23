"""Unit tests for ``cortex.api.routes.traces``."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_traces_requires_auth(client: AsyncClient):
    res = await client.get("/api/v1/traces")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_traces_invalid_limit_query(authed_client: AsyncClient, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    res = await authed_client.get("/api/v1/traces?limit=0")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_list_traces_local_jsonl(authed_client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("cortex.api.routes.traces._MONITOR_DIR", tmp_path)

    jsonl = tmp_path / "run.jsonl"
    line = (
        '{"run_id": "trace-unit-1", "event": "start", '
        '"timestamp": "2025-01-01T00:00:00Z", "model": "gpt-4o"}'
    )
    jsonl.write_text(line + "\n")

    res = await authed_client.get("/api/v1/traces?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["id"] == "trace-unit-1"
    assert data[0]["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_get_trace_not_found_local(authed_client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("cortex.api.routes.traces._MONITOR_DIR", tmp_path)

    res = await authed_client.get("/api/v1/traces/missing-trace-id")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_trace_detail_local(authed_client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("cortex.api.routes.traces._MONITOR_DIR", tmp_path)

    jsonl = tmp_path / "e.jsonl"
    jsonl.write_text(
        '{"run_id": "tid-42", "id": "span-1", "event": "step", '
        '"timestamp": "2025-01-02T01:00:00Z"}\n'
    )

    res = await authed_client.get("/api/v1/traces/tid-42")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "tid-42"
    assert "spans" in body
    assert isinstance(body["spans"], list)
    assert len(body["spans"]) >= 1


@pytest.mark.asyncio
async def test_trace_stats_local(authed_client: AsyncClient, tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("cortex.api.routes.traces._MONITOR_DIR", tmp_path)

    (tmp_path / "s.jsonl").write_text('{"id": "e1"}\n{"id": "e2"}\n')

    res = await authed_client.get("/api/v1/traces/stats?hours=24")
    assert res.status_code == 200
    stats = res.json()
    assert stats["total_traces"] == 2
    assert stats["period"] == "24h"
