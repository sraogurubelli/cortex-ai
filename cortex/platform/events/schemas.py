"""
Event Schemas for Kafka

Pydantic schemas for all Kafka events in cortex-ai platform.

Topics:
- cortex.sessions - Session lifecycle events
- cortex.messages - Message created/updated/deleted
- cortex.usage - Token usage tracking
- cortex.documents - Document uploads/embeddings
- cortex.audit - Audit log events
"""

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Base Event Schema
# ============================================================================


class BaseEvent(BaseModel):
    """Base event schema for all Kafka events."""

    event_id: str = Field(..., description="Unique event ID")
    event_type: str = Field(..., description="Event type (e.g., session_started)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    tenant_id: Optional[str] = Field(None, description="Tenant ID for multi-tenancy")
    user_id: Optional[str] = Field(None, description="User ID")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============================================================================
# Session Events (cortex.sessions)
# ============================================================================


class SessionStartedEvent(BaseEvent):
    """Session started event."""

    event_type: Literal["session_started"] = "session_started"
    conversation_id: str = Field(..., description="Conversation UID")
    thread_id: str = Field(..., description="LangGraph thread ID")
    project_id: str = Field(..., description="Project UID")
    model: str = Field(..., description="LLM model (e.g., gpt-4o)")


class SessionCompletedEvent(BaseEvent):
    """Session completed event."""

    event_type: Literal["session_completed"] = "session_completed"
    conversation_id: str = Field(..., description="Conversation UID")
    thread_id: str = Field(..., description="LangGraph thread ID")
    total_tokens: int = Field(..., description="Total tokens used")
    duration_ms: float = Field(..., description="Session duration in milliseconds")
    message_count: int = Field(..., description="Number of messages in session")


class SessionErrorEvent(BaseEvent):
    """Session error event."""

    event_type: Literal["session_error"] = "session_error"
    conversation_id: str = Field(..., description="Conversation UID")
    thread_id: str = Field(..., description="LangGraph thread ID")
    error_type: str = Field(..., description="Error type (e.g., TimeoutError)")
    error_message: str = Field(..., description="Error message")
    stack_trace: Optional[str] = Field(None, description="Stack trace if available")


# ============================================================================
# Message Events (cortex.messages)
# ============================================================================


class MessageCreatedEvent(BaseEvent):
    """Message created event."""

    event_type: Literal["message_created"] = "message_created"
    message_id: str = Field(..., description="Message UID")
    conversation_id: str = Field(..., description="Conversation UID")
    role: str = Field(..., description="Message role (user/assistant/system/tool)")
    content: str = Field(..., description="Message content")
    token_count: Optional[int] = Field(None, description="Token count")
    model: Optional[str] = Field(None, description="Model used for assistant messages")
    has_attachments: bool = Field(default=False, description="Whether message has attachments")


class MessageUpdatedEvent(BaseEvent):
    """Message updated event (e.g., rating added)."""

    event_type: Literal["message_updated"] = "message_updated"
    message_id: str = Field(..., description="Message UID")
    conversation_id: str = Field(..., description="Conversation UID")
    update_type: str = Field(..., description="Update type (rating/content/metadata)")
    previous_value: Optional[Any] = Field(None, description="Previous value")
    new_value: Any = Field(..., description="New value")


class MessageDeletedEvent(BaseEvent):
    """Message deleted event."""

    event_type: Literal["message_deleted"] = "message_deleted"
    message_id: str = Field(..., description="Message UID")
    conversation_id: str = Field(..., description="Conversation UID")
    deleted_by: str = Field(..., description="User who deleted the message")


# ============================================================================
# Usage Events (cortex.usage)
# ============================================================================


class TokenUsageEvent(BaseEvent):
    """Token usage event."""

    event_type: Literal["token_usage"] = "token_usage"
    conversation_id: str = Field(..., description="Conversation UID")
    message_id: Optional[str] = Field(None, description="Message UID")
    model: str = Field(..., description="LLM model")
    provider: str = Field(..., description="Provider (openai/anthropic/google)")
    prompt_tokens: int = Field(..., description="Prompt tokens")
    completion_tokens: int = Field(..., description="Completion tokens")
    total_tokens: int = Field(..., description="Total tokens")
    cache_creation_tokens: Optional[int] = Field(None, description="Cache creation tokens (Anthropic)")
    cache_read_tokens: Optional[int] = Field(None, description="Cache read tokens (Anthropic)")
    estimated_cost_usd: Optional[float] = Field(None, description="Estimated cost in USD")


class EmbeddingUsageEvent(BaseEvent):
    """Embedding usage event."""

    event_type: Literal["embedding_usage"] = "embedding_usage"
    document_id: Optional[str] = Field(None, description="Document UID")
    query: Optional[str] = Field(None, description="Search query (for query embeddings)")
    model: str = Field(default="text-embedding-3-small", description="Embedding model")
    token_count: int = Field(..., description="Token count")
    vector_dimensions: int = Field(..., description="Vector dimensions")
    estimated_cost_usd: Optional[float] = Field(None, description="Estimated cost in USD")
    cache_hit: bool = Field(default=False, description="Whether result was cached")


# ============================================================================
# Document Events (cortex.documents)
# ============================================================================


class DocumentUploadedEvent(BaseEvent):
    """Document uploaded event."""

    event_type: Literal["document_uploaded"] = "document_uploaded"
    document_id: str = Field(..., description="Document UID")
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    size_bytes: int = Field(..., description="File size in bytes")
    project_id: str = Field(..., description="Project UID")


class DocumentEmbeddedEvent(BaseEvent):
    """Document embedded event (RAG ingestion complete)."""

    event_type: Literal["document_embedded"] = "document_embedded"
    document_id: str = Field(..., description="Document UID")
    chunk_count: int = Field(..., description="Number of chunks created")
    total_tokens: int = Field(..., description="Total tokens embedded")
    embedding_model: str = Field(..., description="Embedding model used")
    duration_ms: float = Field(..., description="Embedding duration in milliseconds")


class DocumentDeletedEvent(BaseEvent):
    """Document deleted event."""

    event_type: Literal["document_deleted"] = "document_deleted"
    document_id: str = Field(..., description="Document UID")
    deleted_by: str = Field(..., description="User who deleted the document")


# ============================================================================
# Audit Events (cortex.audit)
# ============================================================================


class AuditEvent(BaseEvent):
    """Audit event for security/compliance tracking."""

    event_type: Literal["audit"] = "audit"
    action: str = Field(..., description="Action performed (e.g., user_login, conversation_created)")
    resource_type: str = Field(..., description="Resource type (user/conversation/document)")
    resource_id: str = Field(..., description="Resource UID")
    actor_id: str = Field(..., description="User who performed the action")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="User agent")
    result: Literal["success", "failure"] = Field(..., description="Action result")
    failure_reason: Optional[str] = Field(None, description="Failure reason if result=failure")


# ============================================================================
# Event Type Mapping
# ============================================================================

EVENT_TYPE_MAP = {
    # Sessions
    "session_started": SessionStartedEvent,
    "session_completed": SessionCompletedEvent,
    "session_error": SessionErrorEvent,
    # Messages
    "message_created": MessageCreatedEvent,
    "message_updated": MessageUpdatedEvent,
    "message_deleted": MessageDeletedEvent,
    # Usage
    "token_usage": TokenUsageEvent,
    "embedding_usage": EmbeddingUsageEvent,
    # Documents
    "document_uploaded": DocumentUploadedEvent,
    "document_embedded": DocumentEmbeddedEvent,
    "document_deleted": DocumentDeletedEvent,
    # Audit
    "audit": AuditEvent,
}


def parse_event(event_data: dict) -> BaseEvent:
    """
    Parse event data into appropriate event schema.

    Args:
        event_data: Event data dictionary

    Returns:
        Parsed event object

    Raises:
        ValueError: If event_type is unknown
    """
    event_type = event_data.get("event_type")
    if not event_type:
        raise ValueError("event_type is required")

    event_class = EVENT_TYPE_MAP.get(event_type)
    if not event_class:
        raise ValueError(f"Unknown event_type: {event_type}")

    return event_class(**event_data)
