"""
Audit Log Routes

Query audit trail of mutations across the platform.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import AuditLog, Principal, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["audit"])


class AuditLogEntry(BaseModel):
    id: str
    actor_uid: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    resource_name: Optional[str]
    detail: Optional[str]
    ip_address: Optional[str]
    request_id: Optional[str]
    created_at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int
    limit: int
    offset: int


@router.get("/audit-logs", response_model=AuditLogResponse)
async def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action (create, update, delete, chat, etc.)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type (conversation, project, etc.)"),
    actor_uid: Optional[str] = Query(None, description="Filter by actor UID"),
    since: Optional[datetime] = Query(None, description="Only entries after this datetime"),
    until: Optional[datetime] = Query(None, description="Only entries before this datetime"),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Query audit log entries with filters.

    Requires authentication. Non-admin users see only their own actions.
    """
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if not principal.admin:
        query = query.where(AuditLog.actor_id == principal.id)
        count_query = count_query.where(AuditLog.actor_id == principal.id)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)

    if actor_uid and principal.admin:
        query = query.where(AuditLog.actor_uid == actor_uid)
        count_query = count_query.where(AuditLog.actor_uid == actor_uid)

    if since:
        query = query.where(AuditLog.created_at >= since)
        count_query = count_query.where(AuditLog.created_at >= since)

    if until:
        query = query.where(AuditLog.created_at <= until)
        count_query = count_query.where(AuditLog.created_at <= until)

    total = (await session.execute(count_query)).scalar_one()

    result = await session.execute(
        query.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
    )
    logs = list(result.scalars().all())

    return AuditLogResponse(
        entries=[
            AuditLogEntry(
                id=log.uid,
                actor_uid=log.actor_uid,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                resource_name=log.resource_name,
                detail=log.detail,
                ip_address=log.ip_address,
                request_id=log.request_id,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
