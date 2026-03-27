"""
WebSocket Event Schemas

Event types for WebSocket communication between client and server.

Event Flow:
- Client → Server: user_message, cancel_generation
- Server → Client: agent_chunk, agent_complete, error, ping

Usage:
    # Server sends chunk
    event = AgentChunkEvent(
        type="agent_chunk",
        content="Hello",
        token_count=1,
    )
    await websocket.send_json(event.dict())

    # Client receives
    data = await websocket.receive_json()
    event = parse_ws_event(data)
"""

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Client → Server Events
# ============================================================================


class UserMessageEvent(BaseModel):
    """User message event (client → server)."""

    type: Literal["user_message"] = "user_message"
    message: str = Field(..., description="User message content")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID")
    attachments: Optional[list[dict]] = Field(None, description="File attachments")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CancelGenerationEvent(BaseModel):
    """Cancel generation event (client → server)."""

    type: Literal["cancel_generation"] = "cancel_generation"
    conversation_id: str = Field(..., description="Conversation ID to cancel")


class PingEvent(BaseModel):
    """Ping event for keepalive (bidirectional)."""

    type: Literal["ping"] = "ping"
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)


# ============================================================================
# Server → Client Events
# ============================================================================


class AgentChunkEvent(BaseModel):
    """Agent response chunk event (server → client)."""

    type: Literal["agent_chunk"] = "agent_chunk"
    content: str = Field(..., description="Chunk of agent response")
    conversation_id: str = Field(..., description="Conversation ID")
    message_id: Optional[str] = Field(None, description="Message ID")
    token_count: Optional[int] = Field(None, description="Tokens in this chunk")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class AgentCompleteEvent(BaseModel):
    """Agent response complete event (server → client)."""

    type: Literal["agent_complete"] = "agent_complete"
    conversation_id: str = Field(..., description="Conversation ID")
    message_id: str = Field(..., description="Message ID")
    total_tokens: int = Field(..., description="Total tokens used")
    duration_ms: float = Field(..., description="Generation duration in ms")
    finish_reason: str = Field(default="stop", description="Finish reason (stop/length/error)")


class ToolCallEvent(BaseModel):
    """Tool call event (server → client)."""

    type: Literal["tool_call"] = "tool_call"
    conversation_id: str = Field(..., description="Conversation ID")
    tool_name: str = Field(..., description="Tool name")
    tool_args: dict = Field(..., description="Tool arguments")
    tool_call_id: str = Field(..., description="Tool call ID")


class ToolResultEvent(BaseModel):
    """Tool result event (server → client)."""

    type: Literal["tool_result"] = "tool_result"
    conversation_id: str = Field(..., description="Conversation ID")
    tool_call_id: str = Field(..., description="Tool call ID")
    result: Any = Field(..., description="Tool result")
    success: bool = Field(default=True, description="Whether tool succeeded")


class ErrorEvent(BaseModel):
    """Error event (server → client)."""

    type: Literal["error"] = "error"
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    error_type: str = Field(..., description="Error type (validation/timeout/internal)")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")


class ConnectionAckEvent(BaseModel):
    """Connection acknowledgment event (server → client)."""

    type: Literal["connection_ack"] = "connection_ack"
    connection_id: str = Field(..., description="Unique connection ID")
    conversation_id: Optional[str] = Field(None, description="Conversation ID if reconnecting")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PongEvent(BaseModel):
    """Pong response to ping (server → client)."""

    type: Literal["pong"] = "pong"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TypingIndicatorEvent(BaseModel):
    """Typing indicator event (server → client)."""

    type: Literal["typing"] = "typing"
    conversation_id: str = Field(..., description="Conversation ID")
    is_typing: bool = Field(..., description="Whether agent is typing")


class CitationEvent(BaseModel):
    """Citation event for RAG sources (server → client)."""

    type: Literal["citation"] = "citation"
    conversation_id: str = Field(..., description="Conversation ID")
    message_id: str = Field(..., description="Message ID")
    source: str = Field(..., description="Source document/URL")
    title: Optional[str] = Field(None, description="Source title")
    snippet: Optional[str] = Field(None, description="Relevant snippet")
    score: Optional[float] = Field(None, description="Relevance score")


# ============================================================================
# Event Type Mapping
# ============================================================================

CLIENT_EVENT_MAP = {
    "user_message": UserMessageEvent,
    "cancel_generation": CancelGenerationEvent,
    "ping": PingEvent,
}

SERVER_EVENT_MAP = {
    "agent_chunk": AgentChunkEvent,
    "agent_complete": AgentCompleteEvent,
    "tool_call": ToolCallEvent,
    "tool_result": ToolResultEvent,
    "error": ErrorEvent,
    "connection_ack": ConnectionAckEvent,
    "pong": PongEvent,
    "typing": TypingIndicatorEvent,
    "citation": CitationEvent,
}


def parse_client_event(data: dict) -> UserMessageEvent | CancelGenerationEvent | PingEvent:
    """
    Parse client event data into appropriate event schema.

    Args:
        data: Event data dictionary from client

    Returns:
        Parsed event object

    Raises:
        ValueError: If event type is unknown or invalid
    """
    event_type = data.get("type")
    if not event_type:
        raise ValueError("Event type is required")

    event_class = CLIENT_EVENT_MAP.get(event_type)
    if not event_class:
        raise ValueError(f"Unknown client event type: {event_type}")

    return event_class(**data)


def serialize_server_event(event: BaseModel) -> dict:
    """
    Serialize server event to JSON-safe dict.

    Args:
        event: Server event object

    Returns:
        JSON-safe dictionary
    """
    data = event.dict()

    # Convert datetime to ISO format
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()

    return data
