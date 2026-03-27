"""
WebSocket Chat Routes

Real-time bidirectional chat via WebSocket.

Features:
- Bidirectional streaming (client can cancel mid-generation)
- Multi-subscriber support (broadcast to all connected clients)
- Redis Pub/Sub for cross-instance broadcast

Usage:
    # Client connects
    ws = new WebSocket("ws://localhost:8000/api/v1/ws/chat/conv_123?token=<jwt>");

    # Client sends message
    ws.send(JSON.stringify({
        type: "user_message",
        message: "Hello, how are you?",
        conversation_id: "conv_123"
    }));

    # Client receives chunks
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "agent_chunk") {
            console.log(data.content);
        }
    };

    # Client cancels generation
    ws.send(JSON.stringify({
        type: "cancel_generation",
        conversation_id: "conv_123"
    }));
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.websocket.auth import get_websocket_principal
from cortex.api.websocket.events import (
    parse_client_event,
    UserMessageEvent,
    CancelGenerationEvent,
    PingEvent,
    ConnectionAckEvent,
    ErrorEvent,
    AgentCompleteEvent,
    PongEvent,
)
from cortex.api.websocket.manager import (
    get_connection_manager,
    MultiSubscriberStreamWriter,
)
from cortex.platform.database import Principal, Project, Conversation, Message, get_db
from cortex.platform.database.repositories import (
    ProjectRepository,
    ConversationRepository,
    MessageRepository,
)
from cortex.platform.auth import Permission, has_permission
from cortex.orchestration.session.orchestrator import SessionOrchestrator, SessionConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])


# ============================================================================
# WebSocket Chat Endpoint
# ============================================================================


@router.websocket("/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket chat endpoint for real-time bidirectional communication.

    Args:
        websocket: WebSocket connection
        conversation_id: Conversation UID
        db: Database session

    Query Parameters:
        token: JWT authentication token (required)

    Client → Server Events:
        - user_message: Send a message
        - cancel_generation: Cancel in-progress generation
        - ping: Keepalive ping

    Server → Client Events:
        - connection_ack: Connection established
        - agent_chunk: Agent response chunk
        - agent_complete: Agent response complete
        - tool_call: Tool execution started
        - tool_result: Tool execution result
        - error: Error occurred
        - pong: Keepalive pong
    """
    # Authenticate (before accepting connection)
    principal = await get_websocket_principal(websocket)
    if not principal:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    # Accept WebSocket connection
    await websocket.accept()

    # Get connection manager
    manager = get_connection_manager()

    # Connect to room
    room = await manager.connect(conversation_id, websocket)

    try:
        # Send connection acknowledgment
        connection_id = f"conn_{uuid.uuid4().hex[:12]}"
        ack_event = ConnectionAckEvent(
            connection_id=connection_id,
            conversation_id=conversation_id,
        )
        await websocket.send_json(ack_event.dict())

        logger.info(
            f"WebSocket connected: conversation={conversation_id}, "
            f"principal={principal.id}, connection={connection_id}"
        )

        # Handle incoming messages
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            # Parse event
            try:
                event = parse_client_event(data)
            except ValueError as e:
                error_event = ErrorEvent(
                    conversation_id=conversation_id,
                    error_type="validation",
                    message=f"Invalid event: {e}",
                )
                await websocket.send_json(error_event.dict())
                continue

            # Handle event
            if isinstance(event, UserMessageEvent):
                await handle_user_message(
                    event=event,
                    conversation_id=conversation_id,
                    principal=principal,
                    room=room,
                    db=db,
                )
            elif isinstance(event, CancelGenerationEvent):
                await handle_cancel_generation(
                    event=event,
                    conversation_id=conversation_id,
                    manager=manager,
                )
            elif isinstance(event, PingEvent):
                pong_event = PongEvent()
                await websocket.send_json(pong_event.dict())
            else:
                logger.warning(f"Unknown event type: {type(event)}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: conversation={conversation_id}, principal={principal.id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        error_event = ErrorEvent(
            conversation_id=conversation_id,
            error_type="internal",
            message="Internal server error",
        )
        try:
            await websocket.send_json(error_event.dict())
        except:
            pass
    finally:
        # Disconnect from room
        await manager.disconnect(conversation_id, websocket)


# ============================================================================
# Event Handlers
# ============================================================================


async def handle_user_message(
    event: UserMessageEvent,
    conversation_id: str,
    principal: Principal,
    room: "ChatRoomState",
    db: AsyncSession,
) -> None:
    """
    Handle user message event.

    Args:
        event: User message event
        conversation_id: Conversation UID
        principal: Authenticated principal
        room: Chat room state
        db: Database session
    """
    logger.info(f"Received user message: conversation={conversation_id}, message={event.message[:50]}")

    # Load conversation
    conversation_repo = ConversationRepository(db)
    conversation = await conversation_repo.find_by_uid(conversation_id)

    if not conversation:
        error_event = ErrorEvent(
            conversation_id=conversation_id,
            error_type="not_found",
            message="Conversation not found",
        )
        await room.broadcast(error_event.dict())
        return

    # Verify access
    # TODO: Check project permissions
    # For now, just verify conversation belongs to principal
    if conversation.principal_id != principal.id:
        error_event = ErrorEvent(
            conversation_id=conversation_id,
            error_type="forbidden",
            message="Access denied",
        )
        await room.broadcast(error_event.dict())
        return

    # Cancel any existing generation
    if room.orchestrator_task and not room.orchestrator_task.done():
        room.orchestrator_task.cancel()
        try:
            await room.orchestrator_task
        except asyncio.CancelledError:
            pass

    # Create stream writer
    manager = get_connection_manager()
    stream_writer = MultiSubscriberStreamWriter(conversation_id, manager)
    room.stream_writer = stream_writer

    # Create orchestrator
    # TODO: Load actual agent configuration
    orchestrator = SessionOrchestrator(
        conversation_id=conversation_id,
        thread_id=conversation.thread_id,
        project_id=conversation.project.uid,
        model="gpt-4o",  # TODO: Load from conversation metadata
        stream_writer=stream_writer,
    )

    # Run orchestrator in background task
    async def run_orchestrator():
        try:
            start_time = datetime.utcnow()

            # Run agent
            result = await orchestrator.run(event.message)

            # Send completion event
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            complete_event = AgentCompleteEvent(
                conversation_id=conversation_id,
                message_id=f"msg_{uuid.uuid4().hex[:12]}",
                total_tokens=result.token_usage.get("total_tokens", 0),
                duration_ms=duration_ms,
                finish_reason="stop",
            )
            await manager.broadcast(conversation_id, complete_event)

        except asyncio.CancelledError:
            logger.info(f"Orchestrator cancelled: conversation={conversation_id}")
            error_event = ErrorEvent(
                conversation_id=conversation_id,
                error_type="cancelled",
                message="Generation cancelled",
            )
            await manager.broadcast(conversation_id, error_event)
        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            error_event = ErrorEvent(
                conversation_id=conversation_id,
                error_type="internal",
                message=f"Generation failed: {str(e)}",
            )
            await manager.broadcast(conversation_id, error_event)

    # Start orchestrator task
    room.orchestrator_task = asyncio.create_task(run_orchestrator())


async def handle_cancel_generation(
    event: CancelGenerationEvent,
    conversation_id: str,
    manager: "ConnectionManager",
) -> None:
    """
    Handle cancel generation event.

    Args:
        event: Cancel generation event
        conversation_id: Conversation UID
        manager: Connection manager
    """
    logger.info(f"Cancelling generation: conversation={conversation_id}")
    await manager.cancel_generation(conversation_id)


# ============================================================================
# Stats Endpoint
# ============================================================================


@router.get("/stats")
async def websocket_stats():
    """
    Get WebSocket connection statistics.

    Returns:
        Statistics dictionary
    """
    manager = get_connection_manager()
    return manager.get_stats()
