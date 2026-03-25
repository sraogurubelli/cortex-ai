"""
Feature Flags Routes

Lightweight per-tenant feature gating with in-memory caching.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import FeatureFlag, Principal, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["feature-flags"])

_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 30


class FlagRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    tenant_id: Optional[str] = None
    enabled: bool = False
    description: Optional[str] = None
    metadata: Optional[dict] = None


class FlagInfo(BaseModel):
    key: str
    tenant_id: Optional[str]
    enabled: bool
    description: Optional[str]
    metadata: Optional[dict]


class FlagEvaluation(BaseModel):
    key: str
    tenant_id: Optional[str]
    enabled: bool


@router.post("/flags", response_model=FlagInfo, status_code=201)
async def create_flag(
    request: FlagRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Create or update a feature flag."""
    if not principal.admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    existing = await session.execute(
        select(FeatureFlag).where(
            FeatureFlag.key == request.key,
            FeatureFlag.tenant_id == request.tenant_id,
        )
    )
    flag = existing.scalar_one_or_none()

    meta_json = json.dumps(request.metadata) if request.metadata else None

    if flag:
        flag.enabled = request.enabled
        flag.description = request.description
        flag.metadata_json = meta_json
    else:
        flag = FeatureFlag(
            key=request.key,
            tenant_id=request.tenant_id,
            enabled=request.enabled,
            description=request.description,
            metadata_json=meta_json,
        )
        session.add(flag)

    await session.commit()

    cache_key = f"{request.key}:{request.tenant_id or '_global'}"
    _cache[cache_key] = (request.enabled, time.time())

    return FlagInfo(
        key=flag.key,
        tenant_id=flag.tenant_id,
        enabled=flag.enabled,
        description=flag.description,
        metadata=request.metadata,
    )


@router.get("/flags", response_model=list[FlagInfo])
async def list_flags(
    tenant_id: Optional[str] = Query(None),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """List all feature flags."""
    query = select(FeatureFlag)
    if tenant_id:
        from sqlalchemy import or_
        query = query.where(
            or_(FeatureFlag.tenant_id == tenant_id, FeatureFlag.tenant_id.is_(None))
        )

    result = await session.execute(query.order_by(FeatureFlag.key))
    flags = list(result.scalars().all())

    return [
        FlagInfo(
            key=f.key,
            tenant_id=f.tenant_id,
            enabled=f.enabled,
            description=f.description,
            metadata=json.loads(f.metadata_json) if f.metadata_json else None,
        )
        for f in flags
    ]


@router.get("/flags/evaluate", response_model=FlagEvaluation)
async def evaluate_flag(
    key: str = Query(..., description="Flag key to evaluate"),
    tenant_id: Optional[str] = Query(None, description="Tenant context"),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Evaluate a flag for a specific tenant.

    Checks tenant-specific override first, then falls back to global.
    Results are cached in-memory for 30s.
    """
    cache_key = f"{key}:{tenant_id or '_global'}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[1]) < _CACHE_TTL:
        return FlagEvaluation(key=key, tenant_id=tenant_id, enabled=cached[0])

    enabled = False

    if tenant_id:
        result = await session.execute(
            select(FeatureFlag).where(
                FeatureFlag.key == key,
                FeatureFlag.tenant_id == tenant_id,
            )
        )
        flag = result.scalar_one_or_none()
        if flag:
            enabled = flag.enabled
            _cache[cache_key] = (enabled, time.time())
            return FlagEvaluation(key=key, tenant_id=tenant_id, enabled=enabled)

    result = await session.execute(
        select(FeatureFlag).where(
            FeatureFlag.key == key,
            FeatureFlag.tenant_id.is_(None),
        )
    )
    flag = result.scalar_one_or_none()
    if flag:
        enabled = flag.enabled

    _cache[cache_key] = (enabled, time.time())
    return FlagEvaluation(key=key, tenant_id=tenant_id, enabled=enabled)


@router.delete("/flags/{key}")
async def delete_flag(
    key: str,
    tenant_id: Optional[str] = Query(None),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Delete a feature flag."""
    if not principal.admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await session.execute(
        select(FeatureFlag).where(
            FeatureFlag.key == key,
            FeatureFlag.tenant_id == tenant_id,
        )
    )
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    await session.delete(flag)
    await session.commit()

    cache_key = f"{key}:{tenant_id or '_global'}"
    _cache.pop(cache_key, None)

    return {"status": "deleted", "key": key, "tenant_id": tenant_id}
