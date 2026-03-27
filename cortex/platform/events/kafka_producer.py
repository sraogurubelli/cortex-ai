"""
Kafka Producer Client

Async Kafka producer for event streaming in cortex-ai platform.

Features:
- Async I/O with aiokafka
- Automatic topic creation
- JSON serialization
- Error handling with logging
- Graceful degradation (falls back to logging if Kafka unavailable)

Usage:
    producer = KafkaProducer(bootstrap_servers="localhost:9092")
    await producer.connect()

    # Send event
    await producer.send_event(
        topic="cortex.sessions",
        event=SessionStartedEvent(...),
    )

    # Cleanup
    await producer.disconnect()
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from cortex.platform.events.schemas import BaseEvent

logger = logging.getLogger(__name__)

try:
    from aiokafka import AIOKafkaProducer
    from aiokafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("aiokafka not installed. Kafka producer disabled.")


class KafkaProducer:
    """
    Async Kafka producer for event streaming.

    Features:
    - Automatic JSON serialization
    - Graceful degradation (logs events if Kafka unavailable)
    - Idempotent connection
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        enable_fallback: bool = True,
    ):
        """
        Initialize Kafka producer.

        Args:
            bootstrap_servers: Kafka broker addresses (comma-separated)
            enable_fallback: If True, log events when Kafka unavailable (graceful degradation)
        """
        self.bootstrap_servers = bootstrap_servers
        self.enable_fallback = enable_fallback
        self.producer: Any | None = None
        self.enabled = KAFKA_AVAILABLE

        if not self.enabled:
            logger.info("Kafka producer disabled (aiokafka not available)")
        else:
            logger.info(f"Kafka producer initialized (servers: {bootstrap_servers})")

    async def connect(self) -> None:
        """
        Connect to Kafka cluster.

        Safe to call multiple times - idempotent.
        Graceful degradation on connection failure.
        """
        if not self.enabled:
            return

        if self.producer is None:
            try:
                self.producer = AIOKafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    compression_type="gzip",  # Compress events
                    acks="all",  # Wait for all replicas (durability)
                    max_in_flight_requests_per_connection=5,
                    retries=3,
                )
                await self.producer.start()
                logger.info("Connected to Kafka cluster")
            except Exception as e:
                logger.warning(
                    f"Failed to connect to Kafka: {e}. "
                    "Producer disabled, falling back to logging."
                )
                self.enabled = False
                self.producer = None

    async def disconnect(self) -> None:
        """Disconnect from Kafka cluster."""
        if self.producer:
            try:
                await self.producer.stop()
                logger.info("Disconnected from Kafka cluster")
            except Exception as e:
                logger.error(f"Error disconnecting from Kafka: {e}")
            finally:
                self.producer = None

    async def send_event(
        self,
        topic: str,
        event: BaseEvent,
        key: Optional[str] = None,
    ) -> bool:
        """
        Send event to Kafka topic.

        Args:
            topic: Kafka topic name (e.g., cortex.sessions)
            event: Event object (must inherit from BaseEvent)
            key: Optional partition key (defaults to event_id)

        Returns:
            True if sent successfully, False otherwise

        Example:
            >>> await producer.send_event(
            ...     topic="cortex.sessions",
            ...     event=SessionStartedEvent(
            ...         event_id="evt_123",
            ...         conversation_id="conv_abc",
            ...         thread_id="thread-xyz",
            ...         project_id="proj_123",
            ...         model="gpt-4o",
            ...     ),
            ... )
        """
        if not self.enabled or not self.producer:
            if self.enable_fallback:
                # Fallback: Log event instead of sending to Kafka
                logger.info(
                    f"[FALLBACK] {topic}: {event.event_type}",
                    extra={
                        "topic": topic,
                        "event_type": event.event_type,
                        "event_id": event.event_id,
                        "event_data": event.dict(),
                    },
                )
            return False

        try:
            # Use event_id as default partition key for ordering
            partition_key = key or event.event_id

            # Convert event to dict
            event_data = event.dict()

            # Ensure timestamp is ISO format
            if isinstance(event_data.get("timestamp"), datetime):
                event_data["timestamp"] = event_data["timestamp"].isoformat()

            # Send to Kafka
            await self.producer.send(
                topic=topic,
                value=event_data,
                key=partition_key.encode("utf-8") if partition_key else None,
            )

            logger.debug(
                f"Sent event to {topic}: {event.event_type}",
                extra={
                    "topic": topic,
                    "event_type": event.event_type,
                    "event_id": event.event_id,
                },
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send event to {topic}: {e}",
                exc_info=True,
                extra={
                    "topic": topic,
                    "event_type": event.event_type,
                    "event_id": event.event_id,
                },
            )
            return False

    async def send_raw(
        self,
        topic: str,
        value: dict,
        key: Optional[str] = None,
    ) -> bool:
        """
        Send raw dictionary to Kafka topic.

        Args:
            topic: Kafka topic name
            value: Event data dictionary
            key: Optional partition key

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled or not self.producer:
            if self.enable_fallback:
                logger.info(
                    f"[FALLBACK] {topic}: raw event",
                    extra={"topic": topic, "value": value},
                )
            return False

        try:
            await self.producer.send(
                topic=topic,
                value=value,
                key=key.encode("utf-8") if key else None,
            )
            logger.debug(f"Sent raw event to {topic}")
            return True
        except Exception as e:
            logger.error(f"Failed to send raw event to {topic}: {e}", exc_info=True)
            return False

    async def flush(self) -> None:
        """
        Flush pending events.

        Waits for all buffered events to be sent.
        """
        if self.producer:
            try:
                await self.producer.flush()
                logger.debug("Flushed Kafka producer")
            except Exception as e:
                logger.error(f"Error flushing Kafka producer: {e}")


# ============================================================================
# Global Producer Instance
# ============================================================================

_producer: Optional[KafkaProducer] = None


def get_kafka_producer(
    bootstrap_servers: str = "localhost:9092",
    enable_fallback: bool = True,
) -> KafkaProducer:
    """
    Get or create global Kafka producer instance.

    Args:
        bootstrap_servers: Kafka broker addresses
        enable_fallback: Enable fallback to logging if Kafka unavailable

    Returns:
        KafkaProducer instance
    """
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            enable_fallback=enable_fallback,
        )
    return _producer


async def init_kafka_producer(
    bootstrap_servers: str = "localhost:9092",
    enable_fallback: bool = True,
) -> KafkaProducer:
    """
    Initialize and connect global Kafka producer.

    Args:
        bootstrap_servers: Kafka broker addresses
        enable_fallback: Enable fallback to logging if Kafka unavailable

    Returns:
        Connected KafkaProducer instance
    """
    producer = get_kafka_producer(bootstrap_servers, enable_fallback)
    await producer.connect()
    return producer


async def shutdown_kafka_producer() -> None:
    """Shutdown global Kafka producer."""
    global _producer
    if _producer:
        await _producer.disconnect()
        _producer = None
