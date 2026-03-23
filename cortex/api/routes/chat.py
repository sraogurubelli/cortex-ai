"""
Chat API Routes

AI chat endpoints with Agent orchestration and SSE streaming.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import (
    Principal,
    Project,
    Conversation,
    Message,
    get_db,
)
from cortex.platform.database.repositories import (
    ProjectRepository,
    OrganizationRepository,
    AccountRepository,
    ConversationRepository,
    MessageRepository,
)
from cortex.orchestration import Agent, ModelConfig, ToolRegistry
from cortex.orchestration.session.checkpointer import get_checkpointer
from cortex.core.streaming.stream_writer import StreamWriter, create_streaming_response
from cortex.prompts import get_prompt
from cortex.orchestration.ui_actions.emitter import emit_show_document
from cortex.tools.document_search import create_document_search_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ChatRequest(BaseModel):
    """Chat request."""

    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID (null for new)")
    stream: bool = Field(default=True, description="Enable SSE streaming")
    model: Optional[str] = Field(None, description="Model override (e.g., gpt-4o, claude-sonnet-4)")
    context: Optional[dict] = Field(default=None, description="Additional context")


class MessageInfo(BaseModel):
    """Message information."""

    id: str
    role: str
    content: str
    tool_calls: Optional[list[dict]] = None
    metadata: Optional[dict] = None
    created_at: datetime


class ChatResponse(BaseModel):
    """Chat response (non-streaming)."""

    conversation_id: str
    thread_id: str
    response: str
    token_usage: dict
    messages: list[MessageInfo]


class ConversationSummary(BaseModel):
    """Conversation summary for listing."""

    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message: Optional[str]


class ConversationList(BaseModel):
    """Conversation list response."""

    conversations: list[ConversationSummary]
    total: int
    limit: int
    offset: int


class ConversationDetail(BaseModel):
    """Conversation detail with messages."""

    id: str
    project_id: str
    title: Optional[str]
    thread_id: str
    messages: list[MessageInfo]
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Helper Functions
# ============================================================================


async def get_or_create_conversation(
    session: AsyncSession,
    project: Project,
    principal: Principal,
    conversation_id: Optional[str],
) -> Conversation:
    """
    Get existing conversation or create new one.

    Args:
        session: Database session
        project: Project instance
        principal: Principal instance
        conversation_id: Optional conversation ID

    Returns:
        Conversation instance
    """
    conversation_repo = ConversationRepository(session)

    if conversation_id:
        # Load existing conversation
        conversation = await conversation_repo.find_by_uid(conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Verify conversation belongs to this project
        if conversation.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Conversation does not belong to this project",
            )

        return conversation
    else:
        # Create new conversation
        conversation = Conversation(
            uid=f"conv_{uuid.uuid4().hex[:12]}",
            project_id=project.id,
            principal_id=principal.id,
            thread_id=f"thread-{uuid.uuid4()}",
            title="New conversation",  # Will update after first response
            meta_json=json.dumps({"model": "gpt-4o"}),
        )
        conversation = await conversation_repo.create(conversation)
        await session.commit()

        return conversation


async def persist_messages(
    session: AsyncSession,
    conversation: Conversation,
    messages: list,
    message_repo: MessageRepository,
) -> None:
    """
    Persist agent messages to database.

    Args:
        session: Database session
        conversation: Conversation instance
        messages: List of LangGraph messages
        message_repo: MessageRepository instance
    """
    try:
        message_models = []

        for msg in messages:
            # Extract message data
            role = msg.get("role", "assistant")
            content = msg.get("content", "")

            # Handle tool calls
            tool_calls = msg.get("tool_calls")
            tool_calls_json = json.dumps(tool_calls) if tool_calls else None

            # Handle tool call ID
            tool_call_id = msg.get("tool_call_id")

            # Extract metadata
            metadata = {}
            if "response_metadata" in msg:
                metadata["response_metadata"] = msg["response_metadata"]
            if "additional_kwargs" in msg:
                metadata["additional_kwargs"] = msg["additional_kwargs"]

            message_models.append(
                Message(
                    uid=f"msg_{uuid.uuid4().hex[:12]}",
                    conversation_id=conversation.id,
                    role=role,
                    content=content,
                    tool_calls=tool_calls_json,
                    tool_call_id=tool_call_id,
                    meta_json=json.dumps(metadata) if metadata else None,
                )
            )

        # Bulk insert
        if message_models:
            await message_repo.create_batch(message_models)
            await session.commit()

            # Update conversation title from first user message if needed
            if conversation.title == "New conversation":
                first_user_message = next(
                    (m for m in messages if m.get("role") == "user"), None
                )
                if first_user_message:
                    title = first_user_message.get("content", "")[:100]
                    conversation_repo = ConversationRepository(session)
                    await conversation_repo.update_title(conversation.id, title)
                    await session.commit()

    except Exception as e:
        logger.exception("Failed to persist messages", error=str(e))
        # Don't fail the request if persistence fails


# ============================================================================
# Chat Endpoints
# ============================================================================


@router.post("/projects/{project_uid}/chat/stream")
async def chat_stream(
    project_uid: str,
    request: ChatRequest,
    principal: Principal = Depends(
        require_permission(Permission.CONVERSATION_CREATE, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """
    Chat with streaming (SSE).

    Requires CONVERSATION_CREATE permission on the project.
    """
    # Load project with organization and account
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Load organization
    org_repo = OrganizationRepository(session)
    organization = await org_repo.find_by_id(project.organization_id)

    # Load account
    account_repo = AccountRepository(session)
    account = await account_repo.find_by_id(organization.account_id)

    # Get or create conversation
    conversation = await get_or_create_conversation(
        session, project, principal, request.conversation_id
    )

    # Build agent with context injection
    tool_registry = ToolRegistry()
    tool_registry.set_context(
        user_id=principal.uid,
        principal_id=str(principal.id),
        project_id=project.uid,
        organization_id=organization.uid,
        account_id=account.uid,
        tenant_id=account.uid,  # For multi-tenancy
    )
    tool_registry.register(create_document_search_tool())

    agent = Agent(
        name="assistant",
        system_prompt=get_prompt(
            "chat.system",
            agent_name="assistant",
            has_documents=True,
        ),
        model=ModelConfig(
            model=request.model or "gpt-4o",
            use_gateway=False,
        ),
        tool_registry=tool_registry,
        checkpointer=get_checkpointer(),
        max_iterations=25,
    )

    # Create SSE writer
    stream_writer = StreamWriter()

    # Stream agent response in background
    async def stream_agent():
        try:
            result = await agent.stream_to_writer(
                message=request.message,
                stream_writer=stream_writer,
                thread_id=conversation.thread_id,
                enable_part_streaming=True,
            )

            # Emit UI actions when the response references known entities
            if result.response and request.context:
                doc_id = request.context.get("referenced_document_id")
                if doc_id:
                    await emit_show_document(
                        stream_writer,
                        document_id=doc_id,
                        project_id=project.uid,
                    )

            # Send done event
            await stream_writer.write_event(
                "done",
                {
                    "conversation_id": conversation.uid,
                    "thread_id": conversation.thread_id,
                    "token_usage": result.token_usage,
                },
            )

            # Persist messages to database (background)
            message_repo = MessageRepository(session)
            await persist_messages(session, conversation, result.messages, message_repo)

        except Exception as e:
            logger.exception("Chat stream error", error=str(e))
            await stream_writer.write_event("error", {"error": str(e)})
        finally:
            await stream_writer.close()

    # Start streaming in background
    asyncio.create_task(stream_agent())

    # Return SSE response
    return await create_streaming_response(stream_writer)


@router.post("/projects/{project_uid}/chat", response_model=ChatResponse)
async def chat(
    project_uid: str,
    request: ChatRequest,
    principal: Principal = Depends(
        require_permission(Permission.CONVERSATION_CREATE, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """
    Chat without streaming.

    Requires CONVERSATION_CREATE permission on the project.
    """
    # Load project with organization and account
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Load organization
    org_repo = OrganizationRepository(session)
    organization = await org_repo.find_by_id(project.organization_id)

    # Load account
    account_repo = AccountRepository(session)
    account = await account_repo.find_by_id(organization.account_id)

    # Get or create conversation
    conversation = await get_or_create_conversation(
        session, project, principal, request.conversation_id
    )

    # Build agent with context injection
    tool_registry = ToolRegistry()
    tool_registry.set_context(
        user_id=principal.uid,
        principal_id=str(principal.id),
        project_id=project.uid,
        organization_id=organization.uid,
        account_id=account.uid,
        tenant_id=account.uid,
    )
    tool_registry.register(create_document_search_tool())

    agent = Agent(
        name="assistant",
        system_prompt=get_prompt(
            "chat.system",
            agent_name="assistant",
            has_documents=True,
        ),
        model=ModelConfig(
            model=request.model or "gpt-4o",
            use_gateway=False,
        ),
        tool_registry=tool_registry,
        checkpointer=get_checkpointer(),
        max_iterations=25,
    )

    # Run agent (non-streaming)
    result = await agent.run(
        message=request.message,
        thread_id=conversation.thread_id,
    )

    # Persist messages
    message_repo = MessageRepository(session)
    await persist_messages(session, conversation, result.messages, message_repo)

    # Get all messages for response
    messages = await message_repo.find_by_conversation(conversation.id)

    return ChatResponse(
        conversation_id=conversation.uid,
        thread_id=conversation.thread_id,
        response=result.response,
        token_usage=result.token_usage,
        messages=[
            MessageInfo(
                id=msg.uid,
                role=msg.role,
                content=msg.content,
                tool_calls=json.loads(msg.tool_calls) if msg.tool_calls else None,
                metadata=json.loads(msg.meta_json) if msg.meta_json else None,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
    )


# ============================================================================
# Conversation Management Endpoints
# ============================================================================


@router.get("/projects/{project_uid}/conversations", response_model=ConversationList)
async def list_conversations(
    project_uid: str,
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(
        require_permission(Permission.CONVERSATION_VIEW, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """
    List conversations in a project.

    Requires CONVERSATION_VIEW permission.
    """
    # Verify project exists
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Get conversations
    conversation_repo = ConversationRepository(session)
    conversations = await conversation_repo.find_by_project(
        project_id=project.id, limit=limit, offset=offset
    )

    # Count total
    total = await conversation_repo.count_by_project(project.id)

    # Build summaries
    message_repo = MessageRepository(session)
    summaries = []

    for conv in conversations:
        message_count = await message_repo.count_by_conversation(conv.id)
        last_message_obj = await message_repo.get_last_message(conv.id)
        last_message = last_message_obj.content[:100] if last_message_obj else None

        summaries.append(
            ConversationSummary(
                id=conv.uid,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=message_count,
                last_message=last_message,
            )
        )

    return ConversationList(
        conversations=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_uid}", response_model=ConversationDetail)
async def get_conversation(
    conversation_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    Get conversation with messages.

    Requires CONVERSATION_VIEW permission on the project.
    """
    # Load conversation
    conversation_repo = ConversationRepository(session)
    conversation = await conversation_repo.find_by_uid(conversation_uid)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Verify access via project RBAC (conversation → project FK)
    from cortex.platform.auth.dependencies import get_permission_checker

    checker = await get_permission_checker(session)
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_id(conversation.project_id)

    has_access = await checker.check(
        principal=principal,
        resource_type="project",
        resource_id=project.uid,
        permission=Permission.CONVERSATION_VIEW,
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Get messages
    message_repo = MessageRepository(session)
    messages = await message_repo.find_by_conversation(conversation.id)

    return ConversationDetail(
        id=conversation.uid,
        project_id=project.uid,
        title=conversation.title,
        thread_id=conversation.thread_id,
        messages=[
            MessageInfo(
                id=msg.uid,
                role=msg.role,
                content=msg.content,
                tool_calls=json.loads(msg.tool_calls) if msg.tool_calls else None,
                metadata=json.loads(msg.meta_json) if msg.meta_json else None,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.delete("/conversations/{conversation_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    Delete a conversation.

    Requires CONVERSATION_DELETE permission on the project.
    """
    # Load conversation
    conversation_repo = ConversationRepository(session)
    conversation = await conversation_repo.find_by_uid(conversation_uid)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Verify access via project RBAC
    from cortex.platform.auth.dependencies import get_permission_checker

    checker = await get_permission_checker(session)
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_id(conversation.project_id)

    has_access = await checker.check(
        principal=principal,
        resource_type="project",
        resource_id=project.uid,
        permission=Permission.CONVERSATION_DELETE,
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Delete conversation (messages cascade delete)
    await conversation_repo.delete(conversation.id)
    await session.commit()

    return None
