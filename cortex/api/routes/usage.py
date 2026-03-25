"""
Usage Metering Routes

Per-tenant token usage tracking and reporting.
Records are created from session-level model_usage data and queried
via date range + tenant/model filters.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Principal, UsageRecord, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["usage"])


class UsageSummary(BaseModel):
    """Aggregated usage for a time period."""
    tenant_id: str
    date: date
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    request_count: int
    cost_estimate_usd: Optional[float]


class UsageResponse(BaseModel):
    """Usage report response."""
    records: list[UsageSummary]
    total_tokens: int
    total_requests: int
    total_cost_usd: Optional[float]
    period_start: date
    period_end: date


class RecordUsageRequest(BaseModel):
    """Record token usage from a completed session."""
    tenant_id: str
    project_id: Optional[str] = None
    principal_id: Optional[str] = None
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)


COST_PER_1K_TOKENS = {
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "claude-sonnet-4-20250514": {"prompt": 0.003, "completion": 0.015},
    "claude-3-5-haiku-20241022": {"prompt": 0.0008, "completion": 0.004},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
    for model_key, rates in COST_PER_1K_TOKENS.items():
        if model_key in model:
            return round(
                (prompt_tokens / 1000) * rates["prompt"]
                + (completion_tokens / 1000) * rates["completion"],
                6,
            )
    return None


@router.post("/usage/record", status_code=201)
async def record_usage(
    request: RecordUsageRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Record token usage from a completed session.

    This is typically called internally by the SessionOrchestrator
    after a chat completes, but can also be called externally.
    """
    total = request.prompt_tokens + request.completion_tokens
    cost = _estimate_cost(request.model, request.prompt_tokens, request.completion_tokens)
    today = date.today()

    existing = await session.execute(
        select(UsageRecord).where(
            UsageRecord.tenant_id == request.tenant_id,
            UsageRecord.model == request.model,
            UsageRecord.date == today,
            UsageRecord.project_id == request.project_id,
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        record.prompt_tokens += request.prompt_tokens
        record.completion_tokens += request.completion_tokens
        record.total_tokens += total
        record.cached_tokens += request.cached_tokens
        record.request_count += 1
        if cost and record.cost_estimate_usd:
            record.cost_estimate_usd += cost
        elif cost:
            record.cost_estimate_usd = cost
    else:
        record = UsageRecord(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            principal_id=request.principal_id,
            model=request.model,
            date=today,
            prompt_tokens=request.prompt_tokens,
            completion_tokens=request.completion_tokens,
            total_tokens=total,
            cached_tokens=request.cached_tokens,
            request_count=1,
            cost_estimate_usd=cost,
        )
        session.add(record)

    await session.commit()
    return {"status": "recorded", "total_tokens": total, "cost_estimate_usd": cost}


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    tenant_id: str = Query(..., description="Tenant (account) ID"),
    start_date: date = Query(..., description="Period start (inclusive)"),
    end_date: date = Query(..., description="Period end (inclusive)"),
    model: Optional[str] = Query(None, description="Filter by model name"),
    project_id: Optional[str] = Query(None, description="Filter by project"),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Get usage report for a tenant over a date range."""
    query = select(UsageRecord).where(
        UsageRecord.tenant_id == tenant_id,
        UsageRecord.date >= start_date,
        UsageRecord.date <= end_date,
    )

    if model:
        query = query.where(UsageRecord.model.ilike(f"%{model}%"))
    if project_id:
        query = query.where(UsageRecord.project_id == project_id)

    result = await session.execute(query.order_by(UsageRecord.date))
    records = list(result.scalars().all())

    total_tokens = sum(r.total_tokens for r in records)
    total_requests = sum(r.request_count for r in records)
    total_cost = sum(r.cost_estimate_usd or 0 for r in records)

    return UsageResponse(
        records=[
            UsageSummary(
                tenant_id=r.tenant_id,
                date=r.date,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                cached_tokens=r.cached_tokens,
                request_count=r.request_count,
                cost_estimate_usd=r.cost_estimate_usd,
            )
            for r in records
        ],
        total_tokens=total_tokens,
        total_requests=total_requests,
        total_cost_usd=round(total_cost, 4) if total_cost else None,
        period_start=start_date,
        period_end=end_date,
    )
