"""
Chat Extensions — production features that complete the chat experience.

Adds to the core chat endpoints:
  - Chat attachments (file references on messages)
  - LLM-based conversation title generation
  - Message regeneration (replay from a point)
  - Stop/cancel running generation
  - Conversation search (title + content)
  - Message ratings (thumbs up/down)
  - Conversation export (JSON / Markdown)
  - System events / UI action continuations
  - Typing indicator + citation SSE events

All routes share the /api/v1 prefix and follow the same RBAC model
as the core chat endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import (
    Conversation,
    Message,
    Principal,
    get_db,
)
from cortex.platform.database.repositories import (
    ConversationRepository,
    MessageRepository,
    ProjectRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat-extensions"])


# ============================================================================
# Request / Response Models
# ============================================================================


class AttachmentRef(BaseModel):
    """Reference to an uploaded file attached to a message."""
    id: str = Field(..., description="Document/file UID")
    name: str = Field(..., description="Original filename")
    mime_type: str = Field(default="application/octet-stream")
    size_bytes: int = Field(default=0)


class SystemEvent(BaseModel):
    """Frontend → backend continuation after a UI action."""
    type: str = Field(..., description="action_completed | action_cancelled")
    capability_id: Optional[str] = None
    result: Optional[dict] = None
    target_page_id: Optional[str] = None


class RegenerateRequest(BaseModel):
    """Regenerate the assistant response from a specific message."""
    from_message_id: str = Field(
        ..., description="UID of the user message to replay from"
    )
    model: Optional[str] = Field(None, description="Model override")


class RatingRequest(BaseModel):
    """Rate a specific message."""
    rating: int = Field(
        ..., ge=-1, le=1,
        description="-1 = thumbs down, 0 = neutral, 1 = thumbs up",
    )
    feedback: Optional[str] = Field(
        None, max_length=2000, description="Optional text feedback"
    )


class TitleUpdateRequest(BaseModel):
    """Manually update conversation title."""
    title: str = Field(..., min_length=1, max_length=500)


class SearchResult(BaseModel):
    """Conversation search result."""
    id: str
    title: Optional[str]
    snippet: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int


class SearchResponse(BaseModel):
    """Search results list."""
    results: list[SearchResult]
    total: int
    query: str


class ExportFormat(BaseModel):
    """Export options."""
    format: str = Field(default="json", description="json | markdown")


class ExportResponse(BaseModel):
    """Exported conversation."""
    conversation_id: str
    format: str
    content: str
    exported_at: datetime


# ============================================================================
# 1. Conversation Search
# ============================================================================


@router.get(
    "/projects/{project_uid}/conversations/search",
    response_model=SearchResponse,
)
async def search_conversations(
    project_uid: str,
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(
        require_permission(Permission.CONVERSATION_VIEW, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """Search conversations by title or message content."""
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    search_pattern = f"%{q}%"

    from sqlalchemy import select, func, distinct

    matching_conv_ids = (
        select(distinct(Message.conversation_id))
        .where(Message.content.ilike(search_pattern))
        .scalar_subquery()
    )

    query = (
        select(Conversation)
        .where(
            Conversation.project_id == project.id,
            or_(
                Conversation.title.ilike(search_pattern),
                Conversation.id.in_(matching_conv_ids),
            ),
        )
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(query)
    conversations = list(result.scalars().all())

    count_query = select(func.count(Conversation.id)).where(
        Conversation.project_id == project.id,
        or_(
            Conversation.title.ilike(search_pattern),
            Conversation.id.in_(matching_conv_ids),
        ),
    )
    total = (await session.execute(count_query)).scalar_one()

    message_repo = MessageRepository(session)
    results = []
    for conv in conversations:
        msg_count = await message_repo.count_by_conversation(conv.id)
        last_msg = await message_repo.get_last_message(conv.id)
        results.append(SearchResult(
            id=conv.uid,
            title=conv.title,
            snippet=last_msg.content[:150] if last_msg else None,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
        ))

    return SearchResponse(results=results, total=total, query=q)


# ============================================================================
# 2. LLM Title Generation
# ============================================================================


@router.post("/conversations/{conversation_uid}/generate-title")
async def generate_title(
    conversation_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Generate an LLM-based title from conversation content."""
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.find_by_uid(conversation_uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message_repo = MessageRepository(session)
    messages = await message_repo.find_by_conversation(conversation.id, limit=10)

    if not messages:
        raise HTTPException(status_code=400, detail="No messages to generate title from")

    transcript = "\n".join(
        f"{m.role}: {m.content[:200]}" for m in messages if m.content
    )

    try:
        from cortex.orchestration.llm import LLMClient
        from cortex.orchestration.config import ModelConfig

        client = LLMClient(ModelConfig(model="gpt-4o-mini", temperature=0.3))
        model = client.get_model()

        from langchain_core.messages import HumanMessage as HM

        result = await model.ainvoke([
            HM(content=(
                "Generate a concise title (max 60 chars) for this conversation. "
                "Return ONLY the title, no quotes or explanation.\n\n"
                f"{transcript}"
            ))
        ])
        title = result.content.strip().strip('"\'')[:100]
    except Exception as e:
        logger.warning("LLM title generation failed, using fallback: %s", e)
        first_user = next((m for m in messages if m.role == "user"), None)
        title = (first_user.content[:80] + "...") if first_user else "Untitled"

    await conv_repo.update_title(conversation.id, title)
    await session.commit()

    return {"conversation_id": conversation_uid, "title": title}


# ============================================================================
# 3. Title Update (manual)
# ============================================================================


@router.patch("/conversations/{conversation_uid}/title")
async def update_title(
    conversation_uid: str,
    request: TitleUpdateRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Manually update conversation title."""
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.find_by_uid(conversation_uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await conv_repo.update_title(conversation.id, request.title)
    await session.commit()

    return {"conversation_id": conversation_uid, "title": request.title}


# ============================================================================
# 4. Message Rating
# ============================================================================


@router.post("/messages/{message_uid}/rate")
async def rate_message(
    message_uid: str,
    request: RatingRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Rate a message (thumbs up/down).

    Stores rating in the message's meta_json field.
    """
    from sqlalchemy import select

    result = await session.execute(
        select(Message).where(Message.uid == message_uid)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    existing_meta = json.loads(message.meta_json) if message.meta_json else {}
    existing_meta["rating"] = {
        "value": request.rating,
        "feedback": request.feedback,
        "rated_by": principal.uid,
        "rated_at": datetime.utcnow().isoformat(),
    }
    message.meta_json = json.dumps(existing_meta)
    await session.commit()

    return {
        "message_id": message_uid,
        "rating": request.rating,
        "feedback": request.feedback,
    }


# ============================================================================
# 5. Conversation Export
# ============================================================================


@router.get("/conversations/{conversation_uid}/export")
async def export_conversation(
    conversation_uid: str,
    format: str = Query(default="json", regex="^(json|markdown)$"),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Export conversation as JSON or Markdown."""
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.find_by_uid(conversation_uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message_repo = MessageRepository(session)
    messages = await message_repo.find_by_conversation(conversation.id, limit=10000)

    if format == "markdown":
        content = _export_markdown(conversation, messages)
    else:
        content = _export_json(conversation, messages)

    return ExportResponse(
        conversation_id=conversation_uid,
        format=format,
        content=content,
        exported_at=datetime.utcnow(),
    )


def _export_json(conversation: Conversation, messages: list[Message]) -> str:
    data = {
        "conversation_id": conversation.uid,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "messages": [
            {
                "id": m.uid,
                "role": m.role,
                "content": m.content,
                "tool_calls": json.loads(m.tool_calls) if m.tool_calls else None,
                "created_at": m.created_at.isoformat(),
                "metadata": json.loads(m.meta_json) if m.meta_json else None,
            }
            for m in messages
        ],
    }
    return json.dumps(data, indent=2)


def _export_markdown(conversation: Conversation, messages: list[Message]) -> str:
    lines = [
        f"# {conversation.title or 'Conversation'}",
        f"*Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "---",
        "",
    ]
    for m in messages:
        role_label = {"user": "**User**", "assistant": "**Assistant**", "system": "**System**", "tool": "**Tool**"}.get(m.role, m.role)
        timestamp = m.created_at.strftime("%H:%M") if m.created_at else ""
        lines.append(f"### {role_label} ({timestamp})")
        lines.append("")
        lines.append(m.content)
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# 6. Message Regeneration
# ============================================================================


@router.post("/conversations/{conversation_uid}/regenerate")
async def regenerate_message(
    conversation_uid: str,
    request: RegenerateRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Regenerate assistant response from a specific user message.

    Deletes all messages after the specified user message and returns
    the conversation_id + thread_id so the client can re-initiate
    streaming with the same context.
    """
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.find_by_uid(conversation_uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from sqlalchemy import select, delete

    result = await session.execute(
        select(Message).where(Message.uid == request.from_message_id)
    )
    target_message = result.scalar_one_or_none()
    if not target_message:
        raise HTTPException(status_code=404, detail="Message not found")
    if target_message.role != "user":
        raise HTTPException(status_code=400, detail="Can only regenerate from a user message")
    if target_message.conversation_id != conversation.id:
        raise HTTPException(status_code=400, detail="Message does not belong to this conversation")

    await session.execute(
        delete(Message).where(
            Message.conversation_id == conversation.id,
            Message.created_at > target_message.created_at,
        )
    )
    await session.commit()

    return {
        "conversation_id": conversation_uid,
        "thread_id": conversation.thread_id,
        "from_message_id": request.from_message_id,
        "message": target_message.content,
        "model": request.model,
        "status": "ready_to_stream",
    }


# ============================================================================
# 7. Stop / Cancel Generation
# ============================================================================

_active_tasks: dict[str, asyncio.Task] = {}


def register_active_task(conversation_id: str, task: asyncio.Task) -> None:
    """Register a running generation task for cancellation."""
    _active_tasks[conversation_id] = task


def unregister_active_task(conversation_id: str) -> None:
    """Remove a completed task from the registry."""
    _active_tasks.pop(conversation_id, None)


@router.post("/conversations/{conversation_uid}/stop")
async def stop_generation(
    conversation_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Stop an in-progress generation for a conversation."""
    task = _active_tasks.get(conversation_uid)
    if not task or task.done():
        raise HTTPException(status_code=404, detail="No active generation found")

    task.cancel()
    _active_tasks.pop(conversation_uid, None)

    return {"conversation_id": conversation_uid, "status": "cancelled"}


# ============================================================================
# 8. System Events / UI Action Continuations
# ============================================================================


@router.post("/conversations/{conversation_uid}/system-event")
async def handle_system_event(
    conversation_uid: str,
    event: SystemEvent,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Handle a frontend system event (action completed/cancelled).

    The frontend sends this after a UI action (navigate, create entity)
    completes or is cancelled. The backend synthesizes a follow-up
    message that the client can pass as the next chat message.
    """
    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.find_by_uid(conversation_uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message_repo = MessageRepository(session)
    recent = await message_repo.find_by_conversation(conversation.id, limit=5)
    history = [{"role": m.role, "content": m.content} for m in recent]

    try:
        from cortex.orchestration.ui_actions.continuation_detector import (
            build_system_event_query,
        )
        follow_up = build_system_event_query(event.model_dump(), history)
    except ImportError:
        if event.type == "action_completed":
            follow_up = (
                f"The action '{event.capability_id or 'unknown'}' completed successfully. "
                "Please continue with the next step."
            )
        else:
            follow_up = (
                f"The action '{event.capability_id or 'unknown'}' was cancelled. "
                "What would you like to do instead?"
            )

    return {
        "conversation_id": conversation_uid,
        "follow_up_message": follow_up,
        "event_type": event.type,
    }
