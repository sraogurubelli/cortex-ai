"""
WebSocket Connection Manager

Manages WebSocket connections, rooms, and broadcasting.

Features:
- Multi-subscriber rooms (multiple clients in same conversation)
- Redis Pub/Sub for cross-instance broadcast
- Graceful connection handling
- Room lifecycle management

Usage:
    manager = get_connection_manager()
    await manager.connect(conversation_id, websocket)

    # Broadcast to room
    await manager.broadcast(conversation_id, event)

    # Disconnect
    await manager.disconnect(conversation_id, websocket)
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Optional
from datetime import datetime

from fastapi import WebSocket

from cortex.api.websocket.events import serialize_server_event
from cortex.platform.config.settings import get_settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available. Cross-instance broadcast disabled.")


# ============================================================================
# Multi-Subscriber Stream Writer
# ============================================================================


class MultiSubscriberStreamWriter:
    """
    Stream writer that broadcasts to multiple WebSocket subscribers.

    Compatible with SessionOrchestrator's stream_writer interface.
    """

    def __init__(self, conversation_id: str, manager: "ConnectionManager"):
        """
        Initialize multi-subscriber stream writer.

        Args:
            conversation_id: Conversation ID
            manager: Connection manager instance
        """
        self.conversation_id = conversation_id
        self.manager = manager
        self.buffer: list[str] = []

    async def write(self, content: str) -> None:
        """
        Write content chunk to all subscribers.

        Args:
            content: Content chunk to broadcast
        """
        from cortex.api.websocket.events import AgentChunkEvent

        self.buffer.append(content)

        event = AgentChunkEvent(
            content=content,
            conversation_id=self.conversation_id,
            token_count=len(content.split()),  # Rough estimate
        )

        await self.manager.broadcast(self.conversation_id, event)

    async def write_event(self, event_type: str, data: dict) -> None:
        """
        Write typed event to all subscribers.

        Args:
            event_type: Event type
            data: Event data
        """
        event_data = {"type": event_type, **data}
        await self.manager.broadcast_raw(self.conversation_id, event_data)

    def get_content(self) -> str:
        """Get buffered content."""
        return "".join(self.buffer)

    async def close(self) -> None:
        """Close stream writer."""
        self.buffer.clear()


# ============================================================================
# Chat Room State
# ============================================================================


class ChatRoomState:
    """
    State for a chat room (conversation).

    Tracks:
    - Connected WebSocket subscribers
    - Active orchestrator task
    - Stream writer
    """

    def __init__(self, conversation_id: str):
        """
        Initialize chat room state.

        Args:
            conversation_id: Conversation ID
        """
        self.conversation_id = conversation_id
        self.subscribers: set[WebSocket] = set()
        self.orchestrator_task: Optional[asyncio.Task] = None
        self.stream_writer: Optional[MultiSubscriberStreamWriter] = None
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()

    def add_subscriber(self, websocket: WebSocket) -> None:
        """Add subscriber to room."""
        self.subscribers.add(websocket)
        self.last_activity = datetime.utcnow()
        logger.info(
            f"Added subscriber to room {self.conversation_id} ({len(self.subscribers)} total)"
        )

    def remove_subscriber(self, websocket: WebSocket) -> None:
        """Remove subscriber from room."""
        self.subscribers.discard(websocket)
        self.last_activity = datetime.utcnow()
        logger.info(
            f"Removed subscriber from room {self.conversation_id} ({len(self.subscribers)} remaining)"
        )

    def is_empty(self) -> bool:
        """Check if room has no subscribers."""
        return len(self.subscribers) == 0

    async def broadcast(self, event_data: dict) -> None:
        """
        Broadcast event to all subscribers in room.

        Args:
            event_data: Event data dictionary
        """
        disconnected: list[WebSocket] = []

        for ws in self.subscribers:
            try:
                await ws.send_json(event_data)
            except Exception as e:
                logger.warning(
                    f"Failed to send to subscriber in room {self.conversation_id}: {e}"
                )
                disconnected.append(ws)

        # Remove disconnected subscribers
        for ws in disconnected:
            self.remove_subscriber(ws)

    async def cancel_generation(self) -> None:
        """Cancel active orchestrator task."""
        if self.orchestrator_task and not self.orchestrator_task.done():
            self.orchestrator_task.cancel()
            logger.info(f"Cancelled generation for room {self.conversation_id}")


# ============================================================================
# Connection Manager
# ============================================================================


class ConnectionManager:
    """
    Manages WebSocket connections and chat rooms.

    Features:
    - Multi-subscriber rooms
    - Redis Pub/Sub for cross-instance broadcast
    - Room lifecycle management
    """

    def __init__(self):
        """Initialize connection manager."""
        self.rooms: dict[str, ChatRoomState] = {}
        self.redis: Any | None = None
        self.redis_pubsub: Any | None = None
        self.redis_listener_task: Optional[asyncio.Task] = None
        self.instance_id = f"instance-{uuid.uuid4().hex[:8]}"
        self.enabled_redis = REDIS_AVAILABLE

        logger.info(f"ConnectionManager initialized (instance: {self.instance_id})")

    async def connect_redis(self) -> None:
        """
        Connect to Redis for cross-instance broadcast.

        Graceful degradation if Redis unavailable.
        """
        if not self.enabled_redis:
            logger.info("Redis disabled, cross-instance broadcast unavailable")
            return

        try:
            settings = get_settings()
            self.redis = await aioredis.from_url(
                settings.redis_url,
                socket_connect_timeout=2,
                decode_responses=True,
            )
            await self.redis.ping()

            # Subscribe to broadcast channel
            self.redis_pubsub = self.redis.pubsub()
            await self.redis_pubsub.subscribe("cortex:ws:broadcast")

            # Start listener task
            self.redis_listener_task = asyncio.create_task(self._redis_listener())

            logger.info("Connected to Redis for WebSocket broadcast")
        except Exception as e:
            logger.warning(
                f"Failed to connect to Redis: {e}. "
                "Cross-instance broadcast disabled."
            )
            self.enabled_redis = False
            self.redis = None

    async def disconnect_redis(self) -> None:
        """Disconnect from Redis."""
        if self.redis_listener_task:
            self.redis_listener_task.cancel()
            try:
                await self.redis_listener_task
            except asyncio.CancelledError:
                pass
            self.redis_listener_task = None

        if self.redis_pubsub:
            await self.redis_pubsub.unsubscribe("cortex:ws:broadcast")
            await self.redis_pubsub.close()
            self.redis_pubsub = None

        if self.redis:
            await self.redis.close()
            self.redis = None

        logger.info("Disconnected from Redis")

    async def _redis_listener(self) -> None:
        """
        Listen for Redis Pub/Sub messages and broadcast to local subscribers.

        Runs in background task.
        """
        if not self.redis_pubsub:
            return

        logger.info("Started Redis Pub/Sub listener")

        try:
            async for message in self.redis_pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])

                    # Ignore messages from this instance
                    if data.get("instance_id") == self.instance_id:
                        continue

                    conversation_id = data.get("conversation_id")
                    event_data = data.get("event")

                    if conversation_id and event_data:
                        # Broadcast to local subscribers
                        room = self.rooms.get(conversation_id)
                        if room:
                            await room.broadcast(event_data)
                            logger.debug(
                                f"Redis broadcast to room {conversation_id} "
                                f"from {data.get('instance_id')}"
                            )

                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")

        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Redis listener error: {e}", exc_info=True)

    async def connect(
        self,
        conversation_id: str,
        websocket: WebSocket,
    ) -> ChatRoomState:
        """
        Connect WebSocket to conversation room.

        Args:
            conversation_id: Conversation ID
            websocket: WebSocket connection

        Returns:
            ChatRoomState instance
        """
        # Get or create room
        if conversation_id not in self.rooms:
            self.rooms[conversation_id] = ChatRoomState(conversation_id)
            logger.info(f"Created new room: {conversation_id}")

        room = self.rooms[conversation_id]
        room.add_subscriber(websocket)

        return room

    async def disconnect(
        self,
        conversation_id: str,
        websocket: WebSocket,
    ) -> None:
        """
        Disconnect WebSocket from conversation room.

        Args:
            conversation_id: Conversation ID
            websocket: WebSocket connection
        """
        room = self.rooms.get(conversation_id)
        if not room:
            return

        room.remove_subscriber(websocket)

        # Clean up empty rooms
        if room.is_empty():
            # Cancel any active generation
            await room.cancel_generation()
            del self.rooms[conversation_id]
            logger.info(f"Deleted empty room: {conversation_id}")

    async def broadcast(
        self,
        conversation_id: str,
        event: Any,
    ) -> None:
        """
        Broadcast event to all subscribers in room (local + remote instances).

        Args:
            conversation_id: Conversation ID
            event: Event object (Pydantic model)
        """
        event_data = serialize_server_event(event)
        await self.broadcast_raw(conversation_id, event_data)

    async def broadcast_raw(
        self,
        conversation_id: str,
        event_data: dict,
    ) -> None:
        """
        Broadcast raw event data to room.

        Args:
            conversation_id: Conversation ID
            event_data: Event data dictionary
        """
        # Broadcast to local subscribers
        room = self.rooms.get(conversation_id)
        if room:
            await room.broadcast(event_data)

        # Broadcast to remote instances via Redis Pub/Sub
        if self.redis:
            try:
                message = {
                    "instance_id": self.instance_id,
                    "conversation_id": conversation_id,
                    "event": event_data,
                }
                await self.redis.publish(
                    "cortex:ws:broadcast",
                    json.dumps(message),
                )
                logger.debug(
                    f"Published event to Redis: {conversation_id} ({event_data.get('type')})"
                )
            except Exception as e:
                logger.error(f"Failed to publish to Redis: {e}")

    async def cancel_generation(self, conversation_id: str) -> None:
        """
        Cancel active generation for conversation.

        Args:
            conversation_id: Conversation ID
        """
        room = self.rooms.get(conversation_id)
        if room:
            await room.cancel_generation()

    def get_room(self, conversation_id: str) -> Optional[ChatRoomState]:
        """
        Get room by conversation ID.

        Args:
            conversation_id: Conversation ID

        Returns:
            ChatRoomState or None if room doesn't exist
        """
        return self.rooms.get(conversation_id)

    def get_stats(self) -> dict:
        """
        Get connection manager statistics.

        Returns:
            Statistics dictionary
        """
        total_subscribers = sum(len(room.subscribers) for room in self.rooms.values())

        return {
            "instance_id": self.instance_id,
            "total_rooms": len(self.rooms),
            "total_subscribers": total_subscribers,
            "redis_enabled": self.enabled_redis,
            "rooms": [
                {
                    "conversation_id": room.conversation_id,
                    "subscribers": len(room.subscribers),
                    "has_active_task": room.orchestrator_task is not None,
                    "created_at": room.created_at.isoformat(),
                    "last_activity": room.last_activity.isoformat(),
                }
                for room in self.rooms.values()
            ],
        }


# ============================================================================
# Global Connection Manager
# ============================================================================

_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """
    Get or create global connection manager.

    Returns:
        ConnectionManager instance
    """
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def init_connection_manager() -> ConnectionManager:
    """
    Initialize and connect global connection manager.

    Returns:
        Connected ConnectionManager instance
    """
    manager = get_connection_manager()
    await manager.connect_redis()
    return manager


async def shutdown_connection_manager() -> None:
    """Shutdown global connection manager."""
    global _manager
    if _manager:
        await _manager.disconnect_redis()
        _manager = None
