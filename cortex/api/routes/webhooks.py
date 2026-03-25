"""
Webhook Management Routes

Register outbound webhook URLs to receive event notifications.
Includes delivery history and manual test triggers.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Principal, Webhook, WebhookDelivery, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["webhooks"])

SUPPORTED_EVENTS = [
    "conversation.created",
    "conversation.completed",
    "conversation.deleted",
    "message.rated",
    "document.uploaded",
    "document.deleted",
]


class WebhookRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    events: list[str] = Field(..., min_length=1, description="Event types to subscribe to")
    secret: Optional[str] = Field(None, max_length=255, description="Signing secret for payload verification")
    active: bool = True


class WebhookInfo(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class DeliveryInfo(BaseModel):
    id: int
    event_type: str
    response_status: Optional[int]
    success: bool
    attempt: int
    created_at: datetime


class TestWebhookResponse(BaseModel):
    success: bool
    status_code: Optional[int]
    response_time_ms: int


@router.post("/webhooks", response_model=WebhookInfo, status_code=201)
async def create_webhook(
    request: WebhookRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Register a new webhook endpoint."""
    for evt in request.events:
        if evt not in SUPPORTED_EVENTS and evt != "*":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported event type: {evt}. Supported: {SUPPORTED_EVENTS}",
            )

    webhook = Webhook(
        uid=f"wh_{uuid.uuid4().hex[:12]}",
        tenant_id=principal.uid,
        url=request.url,
        secret=request.secret,
        events=json.dumps(request.events),
        active=request.active,
    )
    session.add(webhook)
    await session.commit()

    return WebhookInfo(
        id=webhook.uid,
        url=webhook.url,
        events=request.events,
        active=webhook.active,
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
    )


@router.get("/webhooks", response_model=list[WebhookInfo])
async def list_webhooks(
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """List all webhooks for the authenticated principal."""
    result = await session.execute(
        select(Webhook)
        .where(Webhook.tenant_id == principal.uid)
        .order_by(desc(Webhook.created_at))
    )
    webhooks = list(result.scalars().all())

    return [
        WebhookInfo(
            id=w.uid,
            url=w.url,
            events=json.loads(w.events) if w.events else [],
            active=w.active,
            created_at=w.created_at,
            updated_at=w.updated_at,
        )
        for w in webhooks
    ]


@router.delete("/webhooks/{webhook_uid}", status_code=204)
async def delete_webhook(
    webhook_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Delete a webhook."""
    result = await session.execute(
        select(Webhook).where(Webhook.uid == webhook_uid, Webhook.tenant_id == principal.uid)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await session.delete(webhook)
    await session.commit()
    return None


@router.get("/webhooks/{webhook_uid}/deliveries", response_model=list[DeliveryInfo])
async def list_deliveries(
    webhook_uid: str,
    limit: int = Query(default=20, le=100),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """List recent delivery attempts for a webhook."""
    result = await session.execute(
        select(Webhook).where(Webhook.uid == webhook_uid, Webhook.tenant_id == principal.uid)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    result = await session.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook.id)
        .order_by(desc(WebhookDelivery.created_at))
        .limit(limit)
    )
    deliveries = list(result.scalars().all())

    return [
        DeliveryInfo(
            id=d.id,
            event_type=d.event_type,
            response_status=d.response_status,
            success=d.success,
            attempt=d.attempt,
            created_at=d.created_at,
        )
        for d in deliveries
    ]


@router.post("/webhooks/{webhook_uid}/test", response_model=TestWebhookResponse)
async def test_webhook(
    webhook_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Send a test ping to the webhook URL."""
    result = await session.execute(
        select(Webhook).where(Webhook.uid == webhook_uid, Webhook.tenant_id == principal.uid)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    payload = {
        "event": "webhook.test",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {"message": "Test webhook delivery from Cortex-AI"},
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"Content-Type": "application/json"}

            if webhook.secret:
                body = json.dumps(payload)
                sig = hmac.new(
                    webhook.secret.encode(), body.encode(), hashlib.sha256
                ).hexdigest()
                headers["X-Cortex-Signature"] = f"sha256={sig}"

            resp = await client.post(webhook.url, json=payload, headers=headers)

        elapsed = int((time.monotonic() - start) * 1000)
        return TestWebhookResponse(
            success=resp.status_code < 400,
            status_code=resp.status_code,
            response_time_ms=elapsed,
        )
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return TestWebhookResponse(
            success=False,
            status_code=None,
            response_time_ms=elapsed,
        )


async def dispatch_webhook_event(
    event_type: str, payload: dict, tenant_id: str
) -> None:
    """Fire-and-forget webhook delivery for a tenant's matching webhooks.

    Called from application code (e.g. after a conversation completes).
    """
    try:
        from cortex.platform.database.session import get_db_manager

        async with get_db_manager().session() as session:
            result = await session.execute(
                select(Webhook).where(
                    Webhook.tenant_id == tenant_id,
                    Webhook.active.is_(True),
                )
            )
            webhooks = list(result.scalars().all())

            for webhook in webhooks:
                events = json.loads(webhook.events) if webhook.events else []
                if event_type not in events and "*" not in events:
                    continue

                asyncio.create_task(
                    _deliver(webhook, event_type, payload, session)
                )
    except Exception:
        logger.debug("Webhook dispatch failed", exc_info=True)


async def _deliver(
    webhook: Webhook, event_type: str, payload: dict, session: AsyncSession
) -> None:
    """Attempt delivery with up to 3 retries."""
    body_str = json.dumps({"event": event_type, "data": payload})

    for attempt in range(1, 4):
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event_type=event_type,
            payload=body_str,
            attempt=attempt,
        )

        try:
            headers = {"Content-Type": "application/json"}
            if webhook.secret:
                sig = hmac.new(
                    webhook.secret.encode(), body_str.encode(), hashlib.sha256
                ).hexdigest()
                headers["X-Cortex-Signature"] = f"sha256={sig}"

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook.url, content=body_str, headers=headers)

            delivery.response_status = resp.status_code
            delivery.response_body = resp.text[:1000]
            delivery.success = resp.status_code < 400

        except Exception as e:
            delivery.success = False
            delivery.response_body = str(e)[:500]

        try:
            from cortex.platform.database.session import get_db_manager
            async with get_db_manager().session() as db:
                db.add(delivery)
        except Exception:
            pass

        if delivery.success:
            break

        await asyncio.sleep(2 ** attempt)
