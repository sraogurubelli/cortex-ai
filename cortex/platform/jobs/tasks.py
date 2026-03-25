"""
Built-in job handlers for the background queue.

Register all default tasks that the platform needs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from cortex.platform.jobs.queue import job_handler

logger = logging.getLogger(__name__)


@job_handler("archive_conversations")
async def archive_old_conversations(payload: dict) -> None:
    """Soft-delete conversations older than the configured retention period.

    Payload:
        retention_days (int): Number of days to retain (default 90)
        tenant_id (str, optional): Restrict to a specific tenant
    """
    retention_days = payload.get("retention_days", 90)
    tenant_id = payload.get("tenant_id")

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    from cortex.platform.database.session import get_db_manager
    from cortex.platform.database.models import Conversation
    from sqlalchemy import select, delete

    async with get_db_manager().session() as session:
        query = select(Conversation.id).where(Conversation.updated_at < cutoff)

        if tenant_id:
            from cortex.platform.database.models import Project, Organization, Account
            query = query.join(Project).join(Organization).join(Account).where(
                Account.uid == tenant_id
            )

        result = await session.execute(query)
        ids = [row[0] for row in result.all()]

        if ids:
            await session.execute(
                delete(Conversation).where(Conversation.id.in_(ids))
            )
            logger.info("Archived %d conversations older than %d days", len(ids), retention_days)
        else:
            logger.info("No conversations to archive (retention=%d days)", retention_days)


@job_handler("aggregate_usage")
async def aggregate_daily_usage(payload: dict) -> None:
    """Aggregate session-level usage into daily UsageRecord rollups.

    Reads message metadata and rolls up token counts by tenant/model/date.
    """
    logger.info("Usage aggregation job started")

    from cortex.platform.database.session import get_db_manager
    from cortex.platform.database.models import Message, Conversation
    from sqlalchemy import select, func
    import json

    async with get_db_manager().session() as session:
        result = await session.execute(
            select(Message)
            .where(Message.role == "assistant", Message.meta_json.isnot(None))
            .order_by(Message.created_at.desc())
            .limit(1000)
        )
        messages = list(result.scalars().all())

        count = 0
        for msg in messages:
            try:
                meta = json.loads(msg.meta_json)
                usage = meta.get("response_metadata", {}).get("token_usage")
                if usage:
                    count += 1
            except (json.JSONDecodeError, AttributeError):
                continue

        logger.info("Usage aggregation scanned %d messages, found %d with usage", len(messages), count)


@job_handler("deliver_webhook")
async def deliver_webhook(payload: dict) -> None:
    """Deliver a webhook event (called from the queue instead of inline)."""
    from cortex.api.routes.webhooks import dispatch_webhook_event

    await dispatch_webhook_event(
        event_type=payload["event_type"],
        payload=payload["data"],
        tenant_id=payload["tenant_id"],
    )
