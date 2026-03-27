"""
Analytics API Routes

Real-time analytics powered by StarRocks OLAP.

Features:
- Sub-second query response times (even on billions of rows)
- Token usage analytics by model/tenant/date
- Conversation volume and engagement metrics
- User activity analytics
- Cost tracking

Usage:
    # Token usage by model
    GET /api/v1/analytics/usage?start_date=2026-03-01&end_date=2026-03-31&group_by=model

    # Conversation volume
    GET /api/v1/analytics/conversations?start_date=2026-03-01&end_date=2026-03-31

    # User engagement
    GET /api/v1/analytics/engagement?tenant_id=tenant-123
"""

import logging
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Principal
from cortex.platform.analytics.starrocks_client import get_starrocks_client, StarRocksClient
from cortex.platform.auth import Permission, require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


# ============================================================================
# Response Models
# ============================================================================


class UsageDataPoint(BaseModel):
    """Usage data point."""

    date: date
    model: str
    provider: str
    total_tokens: int
    total_cost_usd: float
    conversation_count: int


class UsageResponse(BaseModel):
    """Token usage analytics response."""

    start_date: date
    end_date: date
    total_tokens: int
    total_cost_usd: float
    data_points: list[UsageDataPoint]


class ConversationVolume(BaseModel):
    """Conversation volume data point."""

    date: date
    conversation_count: int
    message_count: int
    avg_messages_per_conversation: float


class ConversationVolumeResponse(BaseModel):
    """Conversation volume response."""

    start_date: date
    end_date: date
    total_conversations: int
    total_messages: int
    data_points: list[ConversationVolume]


class UserEngagement(BaseModel):
    """User engagement metrics."""

    user_id: str
    conversation_count: int
    active_days: int
    total_messages: int
    total_tokens: int
    first_message_at: datetime
    last_message_at: datetime


class UserEngagementResponse(BaseModel):
    """User engagement response."""

    users: list[UserEngagement]
    total_users: int


class ModelUsage(BaseModel):
    """Model usage breakdown."""

    model: str
    provider: str
    total_tokens: int
    total_cost_usd: float
    percentage: float


class ModelUsageResponse(BaseModel):
    """Model usage breakdown response."""

    start_date: date
    end_date: date
    models: list[ModelUsage]


class HealthResponse(BaseModel):
    """Analytics health check response."""

    status: Literal["healthy", "degraded", "unavailable"]
    starrocks_available: bool
    message: str


# ============================================================================
# Analytics Endpoints
# ============================================================================


@router.get("/health", response_model=HealthResponse)
async def analytics_health():
    """
    Check analytics service health.

    Returns:
        Health status
    """
    client = get_starrocks_client()
    is_healthy = await client.health_check()

    if is_healthy:
        return HealthResponse(
            status="healthy",
            starrocks_available=True,
            message="Analytics service is healthy",
        )
    else:
        return HealthResponse(
            status="degraded",
            starrocks_available=False,
            message="StarRocks unavailable, falling back to PostgreSQL",
        )


@router.get("/usage", response_model=UsageResponse)
async def get_usage_analytics(
    start_date: date = Query(..., description="Start date (inclusive)"),
    end_date: date = Query(..., description="End date (inclusive)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    model: Optional[str] = Query(None, description="Filter by model"),
    group_by: Literal["day", "model", "provider"] = Query("day", description="Group by dimension"),
    principal: Principal = Depends(require_authentication),
):
    """
    Get token usage analytics.

    Query token consumption by date, model, or provider.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        tenant_id: Filter by tenant ID
        project_id: Filter by project ID
        model: Filter by model
        group_by: Group by dimension (day/model/provider)
        principal: Authenticated principal

    Returns:
        Token usage analytics

    Example:
        GET /api/v1/analytics/usage?start_date=2026-03-01&end_date=2026-03-31&group_by=model
    """
    client = get_starrocks_client()

    # Build WHERE clause
    where_conditions = [
        f"DATE(created_at) >= '{start_date}'",
        f"DATE(created_at) <= '{end_date}'",
    ]

    if tenant_id:
        where_conditions.append(f"tenant_id = '{tenant_id}'")
    if project_id:
        where_conditions.append(f"project_id = '{project_id}'")
    if model:
        where_conditions.append(f"model = '{model}'")

    where_clause = " AND ".join(where_conditions)

    # Build GROUP BY clause
    if group_by == "day":
        group_clause = "DATE(created_at), model, provider"
        select_clause = "DATE(created_at) as date, model, provider"
    elif group_by == "model":
        group_clause = "model, provider"
        select_clause = f"'{start_date}' as date, model, provider"
    elif group_by == "provider":
        group_clause = "provider"
        select_clause = f"'{start_date}' as date, 'all' as model, provider"
    else:
        group_clause = "DATE(created_at), model, provider"
        select_clause = "DATE(created_at) as date, model, provider"

    # Query StarRocks
    sql = f"""
        SELECT
            {select_clause},
            SUM(total_tokens) as total_tokens,
            SUM(estimated_cost_usd) as total_cost_usd,
            COUNT(DISTINCT conversation_id) as conversation_count
        FROM token_usage_fact
        WHERE {where_clause}
        GROUP BY {group_clause}
        ORDER BY date, total_tokens DESC
    """

    results = await client.query_dict(sql)

    # Calculate totals
    total_tokens = sum(row["total_tokens"] for row in results)
    total_cost_usd = sum(row["total_cost_usd"] or 0 for row in results)

    # Build data points
    data_points = [
        UsageDataPoint(
            date=row["date"],
            model=row["model"],
            provider=row["provider"],
            total_tokens=row["total_tokens"],
            total_cost_usd=row["total_cost_usd"] or 0,
            conversation_count=row["conversation_count"],
        )
        for row in results
    ]

    return UsageResponse(
        start_date=start_date,
        end_date=end_date,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        data_points=data_points,
    )


@router.get("/conversations", response_model=ConversationVolumeResponse)
async def get_conversation_volume(
    start_date: date = Query(..., description="Start date (inclusive)"),
    end_date: date = Query(..., description="End date (inclusive)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    principal: Principal = Depends(require_authentication),
):
    """
    Get conversation volume analytics.

    Query conversation and message counts by date.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        tenant_id: Filter by tenant ID
        project_id: Filter by project ID
        principal: Authenticated principal

    Returns:
        Conversation volume analytics

    Example:
        GET /api/v1/analytics/conversations?start_date=2026-03-01&end_date=2026-03-31
    """
    client = get_starrocks_client()

    # Build WHERE clause
    where_conditions = [
        f"DATE(m.created_at) >= '{start_date}'",
        f"DATE(m.created_at) <= '{end_date}'",
    ]

    if tenant_id:
        where_conditions.append(f"m.tenant_id = '{tenant_id}'")
    if project_id:
        where_conditions.append(f"m.project_id = '{project_id}'")

    where_clause = " AND ".join(where_conditions)

    # Query StarRocks
    sql = f"""
        SELECT
            DATE(m.created_at) as date,
            COUNT(DISTINCT m.conversation_id) as conversation_count,
            COUNT(*) as message_count
        FROM messages_fact m
        WHERE {where_clause}
        GROUP BY DATE(m.created_at)
        ORDER BY date
    """

    results = await client.query_dict(sql)

    # Calculate totals
    total_conversations = sum(row["conversation_count"] for row in results)
    total_messages = sum(row["message_count"] for row in results)

    # Build data points
    data_points = [
        ConversationVolume(
            date=row["date"],
            conversation_count=row["conversation_count"],
            message_count=row["message_count"],
            avg_messages_per_conversation=(
                row["message_count"] / row["conversation_count"]
                if row["conversation_count"] > 0
                else 0
            ),
        )
        for row in results
    ]

    return ConversationVolumeResponse(
        start_date=start_date,
        end_date=end_date,
        total_conversations=total_conversations,
        total_messages=total_messages,
        data_points=data_points,
    )


@router.get("/engagement", response_model=UserEngagementResponse)
async def get_user_engagement(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    min_conversations: int = Query(1, description="Minimum conversations", ge=0),
    limit: int = Query(100, description="Maximum users to return", ge=1, le=1000),
    principal: Principal = Depends(require_authentication),
):
    """
    Get user engagement metrics.

    Query active users with conversation counts, message counts, and activity dates.

    Args:
        tenant_id: Filter by tenant ID
        project_id: Filter by project ID
        min_conversations: Minimum number of conversations
        limit: Maximum users to return
        principal: Authenticated principal

    Returns:
        User engagement metrics

    Example:
        GET /api/v1/analytics/engagement?tenant_id=tenant-123&min_conversations=5
    """
    client = get_starrocks_client()

    # Build WHERE clause
    where_conditions = ["role = 'user'"]

    if tenant_id:
        where_conditions.append(f"tenant_id = '{tenant_id}'")
    if project_id:
        where_conditions.append(f"project_id = '{project_id}'")

    where_clause = " AND ".join(where_conditions)

    # Query StarRocks
    sql = f"""
        SELECT
            user_id,
            COUNT(DISTINCT conversation_id) as conversation_count,
            COUNT(DISTINCT DATE(created_at)) as active_days,
            COUNT(*) as total_messages,
            SUM(token_count) as total_tokens,
            MIN(created_at) as first_message_at,
            MAX(created_at) as last_message_at
        FROM messages_fact
        WHERE {where_clause}
        GROUP BY user_id
        HAVING conversation_count >= {min_conversations}
        ORDER BY conversation_count DESC, total_messages DESC
        LIMIT {limit}
    """

    results = await client.query_dict(sql)

    # Build user engagement list
    users = [
        UserEngagement(
            user_id=row["user_id"],
            conversation_count=row["conversation_count"],
            active_days=row["active_days"],
            total_messages=row["total_messages"],
            total_tokens=row["total_tokens"] or 0,
            first_message_at=row["first_message_at"],
            last_message_at=row["last_message_at"],
        )
        for row in results
    ]

    return UserEngagementResponse(
        users=users,
        total_users=len(users),
    )


@router.get("/models", response_model=ModelUsageResponse)
async def get_model_usage(
    start_date: date = Query(..., description="Start date (inclusive)"),
    end_date: date = Query(..., description="End date (inclusive)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    principal: Principal = Depends(require_authentication),
):
    """
    Get model usage breakdown.

    Query token consumption and cost by model/provider.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        tenant_id: Filter by tenant ID
        project_id: Filter by project ID
        principal: Authenticated principal

    Returns:
        Model usage breakdown

    Example:
        GET /api/v1/analytics/models?start_date=2026-03-01&end_date=2026-03-31
    """
    client = get_starrocks_client()

    # Build WHERE clause
    where_conditions = [
        f"DATE(created_at) >= '{start_date}'",
        f"DATE(created_at) <= '{end_date}'",
    ]

    if tenant_id:
        where_conditions.append(f"tenant_id = '{tenant_id}'")
    if project_id:
        where_conditions.append(f"project_id = '{project_id}'")

    where_clause = " AND ".join(where_conditions)

    # Query StarRocks
    sql = f"""
        SELECT
            model,
            provider,
            SUM(total_tokens) as total_tokens,
            SUM(estimated_cost_usd) as total_cost_usd
        FROM token_usage_fact
        WHERE {where_clause}
        GROUP BY model, provider
        ORDER BY total_tokens DESC
    """

    results = await client.query_dict(sql)

    # Calculate total for percentage
    grand_total_tokens = sum(row["total_tokens"] for row in results)

    # Build model usage list
    models = [
        ModelUsage(
            model=row["model"],
            provider=row["provider"],
            total_tokens=row["total_tokens"],
            total_cost_usd=row["total_cost_usd"] or 0,
            percentage=(
                (row["total_tokens"] / grand_total_tokens * 100)
                if grand_total_tokens > 0
                else 0
            ),
        )
        for row in results
    ]

    return ModelUsageResponse(
        start_date=start_date,
        end_date=end_date,
        models=models,
    )
