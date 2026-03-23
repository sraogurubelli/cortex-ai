"""
Observability / Tracing API

Endpoints for querying traces from Langfuse (or local SwarmMonitor JSONL).
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["traces"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TraceSpan(BaseModel):
    id: str
    name: str
    start_time: str
    end_time: str = ""
    duration_ms: float = 0.0
    input: str = ""
    output: str = ""
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    status: str = "ok"
    metadata: dict = Field(default_factory=dict)


class TraceSummary(BaseModel):
    id: str
    name: str = ""
    session_id: str = ""
    start_time: str
    duration_ms: float = 0.0
    model: str = ""
    total_tokens: int = 0
    status: str = "ok"
    spans_count: int = 0


class TraceDetail(BaseModel):
    id: str
    name: str = ""
    session_id: str = ""
    start_time: str
    duration_ms: float = 0.0
    model: str = ""
    total_tokens: int = 0
    status: str = "ok"
    spans: list[TraceSpan] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class TraceStats(BaseModel):
    total_traces: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    error_count: int = 0
    error_rate: float = 0.0
    model_breakdown: dict = Field(default_factory=dict)
    period: str = "24h"


# ---------------------------------------------------------------------------
# Langfuse proxy helpers
# ---------------------------------------------------------------------------


def _langfuse_configured() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def _langfuse_client() -> httpx.AsyncClient:
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    public = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret = os.environ.get("LANGFUSE_SECRET_KEY", "")
    return httpx.AsyncClient(
        base_url=host,
        auth=(public, secret),
        timeout=15.0,
    )


# ---------------------------------------------------------------------------
# Local JSONL fallback
# ---------------------------------------------------------------------------


_MONITOR_DIR = Path(os.environ.get("CORTEX_MONITOR_DIR", "/tmp/cortex_monitor"))


def _read_local_events(limit: int = 100) -> list[dict]:
    """Read events from SwarmMonitor JSONL files."""
    events: list[dict] = []
    if not _MONITOR_DIR.exists():
        return events

    for jsonl_path in sorted(_MONITOR_DIR.glob("*.jsonl"), reverse=True):
        try:
            for line in jsonl_path.read_text().strip().splitlines():
                if line.strip():
                    events.append(json.loads(line))
                    if len(events) >= limit:
                        return events
        except Exception:
            logger.warning("Failed to read monitor file: %s", jsonl_path, exc_info=True)
    return events


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/traces", response_model=list[TraceSummary])
async def list_traces(
    session_id: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(require_authentication),
):
    """List recent traces."""
    if _langfuse_configured():
        async with _langfuse_client() as client:
            params = {"limit": limit, "orderBy": "timestamp.DESC"}
            resp = await client.get("/api/public/traces", params=params)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return [
                    TraceSummary(
                        id=t.get("id", ""),
                        name=t.get("name", ""),
                        session_id=t.get("sessionId", ""),
                        start_time=t.get("timestamp", ""),
                        duration_ms=t.get("latency", 0) * 1000 if t.get("latency") else 0,
                        model=t.get("metadata", {}).get("model", ""),
                        total_tokens=(t.get("usage", {}) or {}).get("totalTokens", 0),
                        status="error" if t.get("level") == "ERROR" else "ok",
                    )
                    for t in data
                ]

    events = _read_local_events(limit)
    traces: list[TraceSummary] = []
    seen: set[str] = set()
    for ev in events:
        tid = ev.get("run_id", ev.get("id", ""))
        if tid in seen:
            continue
        seen.add(tid)
        traces.append(TraceSummary(
            id=tid,
            name=ev.get("event", ""),
            start_time=ev.get("timestamp", ""),
            model=ev.get("model", ""),
        ))
    return traces[:limit]


@router.get("/traces/stats", response_model=TraceStats)
async def trace_stats(
    hours: int = Query(24, ge=1, le=720),
    principal: Principal = Depends(require_authentication),
):
    """Aggregate trace statistics."""
    if _langfuse_configured():
        async with _langfuse_client() as client:
            resp = await client.get("/api/public/traces", params={"limit": 200})
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                total = len(data)
                latencies = [
                    (t.get("latency", 0) or 0) * 1000 for t in data
                ]
                tokens = sum(
                    (t.get("usage", {}) or {}).get("totalTokens", 0) for t in data
                )
                errors = sum(1 for t in data if t.get("level") == "ERROR")
                latencies_sorted = sorted(latencies)
                p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0
                p95_idx = int(len(latencies_sorted) * 0.95)
                p95 = latencies_sorted[p95_idx] if latencies_sorted else 0

                model_counts: dict[str, int] = {}
                for t in data:
                    m = (t.get("metadata") or {}).get("model", "unknown")
                    model_counts[m] = model_counts.get(m, 0) + 1

                return TraceStats(
                    total_traces=total,
                    total_tokens=tokens,
                    avg_latency_ms=sum(latencies) / total if total else 0,
                    p50_latency_ms=p50,
                    p95_latency_ms=p95,
                    error_count=errors,
                    error_rate=errors / total if total else 0,
                    model_breakdown=model_counts,
                    period=f"{hours}h",
                )

    events = _read_local_events(500)
    return TraceStats(
        total_traces=len(events),
        period=f"{hours}h",
    )


@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace(
    trace_id: str,
    principal: Principal = Depends(require_authentication),
):
    """Get detailed trace with spans."""
    if _langfuse_configured():
        async with _langfuse_client() as client:
            resp = await client.get(f"/api/public/traces/{trace_id}")
            if resp.status_code == 200:
                t = resp.json()
                obs_resp = await client.get(
                    "/api/public/observations",
                    params={"traceId": trace_id, "limit": 100},
                )
                spans = []
                if obs_resp.status_code == 200:
                    for o in obs_resp.json().get("data", []):
                        spans.append(TraceSpan(
                            id=o.get("id", ""),
                            name=o.get("name", ""),
                            start_time=o.get("startTime", ""),
                            end_time=o.get("endTime", ""),
                            duration_ms=(o.get("latency", 0) or 0) * 1000,
                            model=o.get("model", ""),
                            tokens_input=(o.get("usage", {}) or {}).get("input", 0),
                            tokens_output=(o.get("usage", {}) or {}).get("output", 0),
                            status="error" if o.get("level") == "ERROR" else "ok",
                        ))

                return TraceDetail(
                    id=t.get("id", trace_id),
                    name=t.get("name", ""),
                    session_id=t.get("sessionId", ""),
                    start_time=t.get("timestamp", ""),
                    total_tokens=(t.get("usage", {}) or {}).get("totalTokens", 0),
                    spans=spans,
                    metadata=t.get("metadata", {}),
                )
            raise HTTPException(status_code=404, detail="Trace not found in Langfuse")

    events = _read_local_events(500)
    matching = [e for e in events if e.get("run_id") == trace_id or e.get("id") == trace_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Trace not found")

    spans = [
        TraceSpan(
            id=e.get("id", ""),
            name=e.get("event", ""),
            start_time=e.get("timestamp", ""),
        )
        for e in matching
    ]
    return TraceDetail(
        id=trace_id,
        start_time=matching[0].get("timestamp", ""),
        spans=spans,
    )
