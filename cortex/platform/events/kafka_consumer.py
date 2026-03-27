"""
Kafka Consumer Framework

Async Kafka consumer framework for event processing in cortex-ai platform.

Features:
- Consumer groups for horizontal scaling
- Dead letter queue (DLQ) for failed events
- Graceful shutdown with offset commits
- Automatic retries
- Error handling and logging

Usage:
    # Define handler
    async def handle_session_event(event: SessionStartedEvent):
        print(f"Session started: {event.conversation_id}")

    # Create consumer
    consumer = KafkaConsumer(
        topics=["cortex.sessions"],
        group_id="session-processor",
        handler=handle_session_event,
    )

    # Run consumer
    await consumer.start()
    await consumer.consume()  # Runs until shutdown
    await consumer.stop()
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from cortex.platform.events.schemas import BaseEvent, parse_event

logger = logging.getLogger(__name__)

try:
    from aiokafka import AIOKafkaConsumer
    from aiokafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("aiokafka not installed. Kafka consumer disabled.")


# Type alias for event handler
EventHandler = Callable[[BaseEvent], Awaitable[None]]


class KafkaConsumer:
    """
    Async Kafka consumer with dead letter queue and graceful shutdown.

    Features:
    - Consumer groups for parallel processing
    - Dead letter queue for failed events
    - Automatic retries
    - Graceful shutdown
    """

    def __init__(
        self,
        topics: list[str],
        group_id: str,
        handler: EventHandler,
        bootstrap_servers: str = "localhost:9092",
        max_retries: int = 3,
        dlq_topic: Optional[str] = None,
    ):
        """
        Initialize Kafka consumer.

        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            handler: Async function to handle events
            bootstrap_servers: Kafka broker addresses
            max_retries: Maximum retries for failed events
            dlq_topic: Dead letter queue topic (defaults to {topic}.dlq)
        """
        self.topics = topics
        self.group_id = group_id
        self.handler = handler
        self.bootstrap_servers = bootstrap_servers
        self.max_retries = max_retries
        self.dlq_topic = dlq_topic
        self.consumer: Any | None = None
        self.enabled = KAFKA_AVAILABLE
        self._running = False

        if not self.enabled:
            logger.info("Kafka consumer disabled (aiokafka not available)")
        else:
            logger.info(
                f"Kafka consumer initialized (group: {group_id}, topics: {topics})"
            )

    async def start(self) -> None:
        """
        Start Kafka consumer.

        Connects to Kafka cluster and subscribes to topics.
        """
        if not self.enabled:
            logger.warning("Kafka consumer not available, skipping start")
            return

        try:
            self.consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="earliest",  # Start from beginning if no offset
                enable_auto_commit=False,  # Manual commit for reliability
                max_poll_records=100,  # Process up to 100 events per batch
            )
            await self.consumer.start()
            self._running = True
            logger.info(
                f"Kafka consumer started (group: {self.group_id}, topics: {self.topics})"
            )
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}", exc_info=True)
            self.enabled = False
            self.consumer = None

    async def stop(self) -> None:
        """
        Stop Kafka consumer.

        Gracefully shuts down consumer with offset commit.
        """
        self._running = False

        if self.consumer:
            try:
                # Commit pending offsets
                await self.consumer.commit()
                await self.consumer.stop()
                logger.info("Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def consume(self) -> None:
        """
        Consume events from Kafka topics.

        Runs until stop() is called.
        Handles events with retries and DLQ.
        """
        if not self.enabled or not self.consumer:
            logger.warning("Kafka consumer not available, skipping consume")
            return

        logger.info(f"Consuming from topics: {self.topics}")

        try:
            async for message in self.consumer:
                if not self._running:
                    logger.info("Consumer shutdown requested, stopping consume loop")
                    break

                # Process message
                await self._process_message(message)

                # Commit offset after successful processing
                try:
                    await self.consumer.commit()
                except Exception as e:
                    logger.error(f"Failed to commit offset: {e}")

        except asyncio.CancelledError:
            logger.info("Consumer task cancelled, shutting down")
        except Exception as e:
            logger.error(f"Error in consume loop: {e}", exc_info=True)

    async def _process_message(self, message: Any) -> None:
        """
        Process a single Kafka message with retries.

        Args:
            message: Kafka message object
        """
        topic = message.topic
        partition = message.partition
        offset = message.offset
        value = message.value

        logger.debug(
            f"Processing message from {topic}:{partition}:{offset}",
            extra={"topic": topic, "partition": partition, "offset": offset},
        )

        # Parse event
        try:
            event = parse_event(value)
        except Exception as e:
            logger.error(
                f"Failed to parse event from {topic}: {e}",
                exc_info=True,
                extra={"value": value},
            )
            await self._send_to_dlq(topic, value, error=str(e))
            return

        # Process event with retries
        for attempt in range(self.max_retries + 1):
            try:
                await self.handler(event)
                logger.debug(
                    f"Successfully processed event: {event.event_type}",
                    extra={
                        "event_type": event.event_type,
                        "event_id": event.event_id,
                    },
                )
                return  # Success

            except Exception as e:
                if attempt < self.max_retries:
                    # Retry
                    logger.warning(
                        f"Handler error (attempt {attempt + 1}/{self.max_retries}): {e}",
                        extra={
                            "event_type": event.event_type,
                            "event_id": event.event_id,
                            "attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    # Max retries exceeded - send to DLQ
                    logger.error(
                        f"Handler failed after {self.max_retries} retries: {e}",
                        exc_info=True,
                        extra={
                            "event_type": event.event_type,
                            "event_id": event.event_id,
                        },
                    )
                    await self._send_to_dlq(topic, value, error=str(e))

    async def _send_to_dlq(
        self,
        original_topic: str,
        value: dict,
        error: str,
    ) -> None:
        """
        Send failed event to dead letter queue.

        Args:
            original_topic: Original topic name
            value: Event data
            error: Error message
        """
        dlq_topic = self.dlq_topic or f"{original_topic}.dlq"

        dlq_message = {
            "original_topic": original_topic,
            "original_value": value,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
            "consumer_group": self.group_id,
        }

        logger.warning(
            f"Sending event to DLQ: {dlq_topic}",
            extra={
                "dlq_topic": dlq_topic,
                "original_topic": original_topic,
                "error": error,
            },
        )

        # TODO: Send to DLQ topic
        # For now, just log the DLQ message
        logger.error(
            "DLQ message (Kafka producer not integrated yet)",
            extra=dlq_message,
        )


# ============================================================================
# Consumer Manager
# ============================================================================


class ConsumerManager:
    """
    Manages multiple Kafka consumers.

    Starts/stops all consumers together.
    """

    def __init__(self):
        """Initialize consumer manager."""
        self.consumers: list[KafkaConsumer] = []
        self._tasks: list[asyncio.Task] = []

    def add_consumer(self, consumer: KafkaConsumer) -> None:
        """
        Add a consumer to the manager.

        Args:
            consumer: KafkaConsumer instance
        """
        self.consumers.append(consumer)
        logger.info(
            f"Added consumer to manager (group: {consumer.group_id}, topics: {consumer.topics})"
        )

    async def start_all(self) -> None:
        """Start all consumers."""
        logger.info(f"Starting {len(self.consumers)} Kafka consumers")

        for consumer in self.consumers:
            await consumer.start()

        # Create consume tasks
        for consumer in self.consumers:
            task = asyncio.create_task(consumer.consume())
            self._tasks.append(task)

        logger.info(f"All consumers started ({len(self._tasks)} tasks)")

    async def stop_all(self) -> None:
        """Stop all consumers."""
        logger.info("Stopping all Kafka consumers")

        # Cancel consume tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop consumers
        for consumer in self.consumers:
            await consumer.stop()

        self._tasks.clear()
        logger.info("All consumers stopped")


# ============================================================================
# Global Consumer Manager
# ============================================================================

_manager: Optional[ConsumerManager] = None


def get_consumer_manager() -> ConsumerManager:
    """
    Get or create global consumer manager.

    Returns:
        ConsumerManager instance
    """
    global _manager
    if _manager is None:
        _manager = ConsumerManager()
    return _manager
