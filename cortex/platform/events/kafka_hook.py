"""
Kafka Analytics Hook

Integrates Kafka event streaming with SessionOrchestrator.

Emits events to Kafka topics for:
- Session lifecycle (started, completed, error)
- Messages (created, updated)
- Token usage tracking

Usage:
    from cortex.platform.events.kafka_hook import KafkaAnalyticsHook
    from cortex.orchestration.session import SessionOrchestrator

    hook = KafkaAnalyticsHook(bootstrap_servers="localhost:9092")
    await hook.connect()

    orchestrator = SessionOrchestrator(
        ...,
        analytics_hook=hook,
    )
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from cortex.platform.events.kafka_producer import KafkaProducer, get_kafka_producer
from cortex.platform.events.schemas import (
    SessionStartedEvent,
    SessionCompletedEvent,
    SessionErrorEvent,
    MessageCreatedEvent,
    TokenUsageEvent,
)

logger = logging.getLogger(__name__)


class KafkaAnalyticsHook:
    """
    Analytics hook that emits events to Kafka.

    Integrates with SessionOrchestrator to stream:
    - Session lifecycle events
    - Message events
    - Token usage events
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        enable_fallback: bool = True,
    ):
        """
        Initialize Kafka analytics hook.

        Args:
            bootstrap_servers: Kafka broker addresses
            enable_fallback: Enable fallback to logging if Kafka unavailable
        """
        self.bootstrap_servers = bootstrap_servers
        self.enable_fallback = enable_fallback
        self.producer: Optional[KafkaProducer] = None

        logger.info("KafkaAnalyticsHook initialized")

    async def connect(self) -> None:
        """Connect to Kafka cluster."""
        self.producer = get_kafka_producer(
            bootstrap_servers=self.bootstrap_servers,
            enable_fallback=self.enable_fallback,
        )
        await self.producer.connect()
        logger.info("KafkaAnalyticsHook connected")

    async def disconnect(self) -> None:
        """Disconnect from Kafka cluster."""
        if self.producer:
            await self.producer.disconnect()
            self.producer = None
        logger.info("KafkaAnalyticsHook disconnected")

    # ========================================================================
    # Session Lifecycle Events
    # ========================================================================

    async def on_session_start(
        self,
        conversation_id: str,
        thread_id: str,
        project_id: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        model: str = "gpt-4o",
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Emit session started event.

        Args:
            conversation_id: Conversation UID
            thread_id: LangGraph thread ID
            project_id: Project UID
            user_id: User ID
            tenant_id: Tenant ID
            model: LLM model
            metadata: Additional metadata
        """
        if not self.producer:
            logger.warning("Kafka producer not connected, skipping session_start event")
            return

        event = SessionStartedEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            thread_id=thread_id,
            project_id=project_id,
            user_id=user_id,
            tenant_id=tenant_id,
            model=model,
            metadata=metadata or {},
        )

        await self.producer.send_event(
            topic="cortex.sessions",
            event=event,
            key=conversation_id,  # Partition by conversation for ordering
        )

    async def on_session_complete(
        self,
        conversation_id: str,
        thread_id: str,
        total_tokens: int,
        duration_ms: float,
        message_count: int,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Emit session completed event.

        Args:
            conversation_id: Conversation UID
            thread_id: LangGraph thread ID
            total_tokens: Total tokens used
            duration_ms: Session duration in milliseconds
            message_count: Number of messages in session
            user_id: User ID
            tenant_id: Tenant ID
            metadata: Additional metadata
        """
        if not self.producer:
            logger.warning("Kafka producer not connected, skipping session_complete event")
            return

        event = SessionCompletedEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            thread_id=thread_id,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            message_count=message_count,
            user_id=user_id,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        await self.producer.send_event(
            topic="cortex.sessions",
            event=event,
            key=conversation_id,
        )

    async def on_session_error(
        self,
        conversation_id: str,
        thread_id: str,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Emit session error event.

        Args:
            conversation_id: Conversation UID
            thread_id: LangGraph thread ID
            error_type: Error type (e.g., TimeoutError)
            error_message: Error message
            stack_trace: Stack trace if available
            user_id: User ID
            tenant_id: Tenant ID
            metadata: Additional metadata
        """
        if not self.producer:
            logger.warning("Kafka producer not connected, skipping session_error event")
            return

        event = SessionErrorEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            thread_id=thread_id,
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            user_id=user_id,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        await self.producer.send_event(
            topic="cortex.sessions",
            event=event,
            key=conversation_id,
        )

    # ========================================================================
    # Message Events
    # ========================================================================

    async def on_message_created(
        self,
        message_id: str,
        conversation_id: str,
        role: str,
        content: str,
        token_count: Optional[int] = None,
        model: Optional[str] = None,
        has_attachments: bool = False,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Emit message created event.

        Args:
            message_id: Message UID
            conversation_id: Conversation UID
            role: Message role (user/assistant/system/tool)
            content: Message content
            token_count: Token count
            model: Model used for assistant messages
            has_attachments: Whether message has attachments
            user_id: User ID
            tenant_id: Tenant ID
            metadata: Additional metadata
        """
        if not self.producer:
            logger.warning("Kafka producer not connected, skipping message_created event")
            return

        event = MessageCreatedEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            message_id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            token_count=token_count,
            model=model,
            has_attachments=has_attachments,
            user_id=user_id,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        await self.producer.send_event(
            topic="cortex.messages",
            event=event,
            key=conversation_id,  # Partition by conversation
        )

    # ========================================================================
    # Usage Events
    # ========================================================================

    async def on_token_usage(
        self,
        conversation_id: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        message_id: Optional[str] = None,
        cache_creation_tokens: Optional[int] = None,
        cache_read_tokens: Optional[int] = None,
        estimated_cost_usd: Optional[float] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Emit token usage event.

        Args:
            conversation_id: Conversation UID
            model: LLM model
            provider: Provider (openai/anthropic/google)
            prompt_tokens: Prompt tokens
            completion_tokens: Completion tokens
            total_tokens: Total tokens
            message_id: Message UID
            cache_creation_tokens: Cache creation tokens (Anthropic)
            cache_read_tokens: Cache read tokens (Anthropic)
            estimated_cost_usd: Estimated cost in USD
            user_id: User ID
            tenant_id: Tenant ID
            metadata: Additional metadata
        """
        if not self.producer:
            logger.warning("Kafka producer not connected, skipping token_usage event")
            return

        event = TokenUsageEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            message_id=message_id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            estimated_cost_usd=estimated_cost_usd,
            user_id=user_id,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        await self.producer.send_event(
            topic="cortex.usage",
            event=event,
            key=conversation_id,
        )

    # ========================================================================
    # Generic Event Method
    # ========================================================================

    async def emit(self, event_name: str, properties: dict[str, Any]) -> None:
        """
        Generic emit method for compatibility with existing hooks.

        Args:
            event_name: Event name (session_started, message_created, etc.)
            properties: Event properties

        Example:
            >>> await hook.emit("session_started", {
            ...     "conversation_id": "conv_123",
            ...     "thread_id": "thread-abc",
            ...     "project_id": "proj_xyz",
            ...     "model": "gpt-4o",
            ... })
        """
        # Route to specific methods based on event_name
        if event_name == "session_started":
            await self.on_session_start(**properties)
        elif event_name == "session_completed":
            await self.on_session_complete(**properties)
        elif event_name == "session_error":
            await self.on_session_error(**properties)
        elif event_name == "message_created":
            await self.on_message_created(**properties)
        elif event_name == "token_usage":
            await self.on_token_usage(**properties)
        else:
            logger.warning(f"Unknown event name: {event_name}")
