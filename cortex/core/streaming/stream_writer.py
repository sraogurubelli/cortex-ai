"""
StreamWriter: Server-Sent Events (SSE) streaming for Cortex-AI.

Handles:
- Async event streaming
- Event type management
- Size limiting and truncation
- SSE formatting
"""

import asyncio
import json
import structlog
from typing import Any, AsyncGenerator, Dict, Optional

logger = structlog.get_logger(__name__)


class StreamWriter:
    """
    Stream writer for Server-Sent Events (SSE).

    Manages an async queue of events and provides an async iterator
    interface for streaming events to clients.

    Features (ported from ml-infra StreamWriter):
      - Bounded queue with overflow drop (oldest dropped first)
      - Event size truncation for oversized payloads
      - Sequential event numbering for client ordering
      - Prompt buffering: ``prompts`` events are held back and flushed
        after the final message so they appear at the end of the stream
    """

    def __init__(
        self,
        max_queue_size: int = 100,
        max_event_size_kb: int = 64,
    ):
        """
        Initialize stream writer.

        Args:
            max_queue_size: Maximum events in queue (older events dropped if exceeded)
            max_event_size_kb: Maximum event size in KB (events truncated if exceeded)
        """
        self._queue = asyncio.Queue(maxsize=max_queue_size)
        self._closed = False
        self.max_event_size_kb = max_event_size_kb
        self.max_event_size_bytes = max_event_size_kb * 1024
        self._event_sequence: int = 0
        self._buffered_prompts: list[dict] = []

    async def write_event(
        self,
        event_type: str = "message",
        data: Any = None,
    ) -> None:
        """
        Write an event to the stream.

        Events of type ``prompts`` are buffered internally until
        ``flush_prompts()`` is called (typically after the final message).

        Args:
            event_type: Type of event (message, status, progress, error, etc.)
            data: Event data (will be JSON-encoded if not a string)
        """
        if self._closed:
            raise RuntimeError("Cannot write to a closed stream")

        # Assign sequential event number
        self._event_sequence += 1

        # Create event object
        event = {"event": event_type, "data": data, "seq": self._event_sequence}

        # Convert data to JSON if not a string
        if not isinstance(data, str):
            event["data"] = json.dumps(data)

        # Check event size and truncate if needed
        event_data = event.get("data", "")
        if event_data:
            original_size = len(event_data.encode("utf-8"))
            if original_size > self.max_event_size_bytes:
                event["data"] = self._truncate_event_data(event_data, original_size)
                logger.warning(
                    "Event data truncated",
                    event_type=event_type,
                    original_size_kb=original_size // 1024,
                    max_size_kb=self.max_event_size_kb,
                )

        # Buffer prompt events to emit them after the final message
        if event_type == "prompts":
            self._buffered_prompts.append(event)
            return

        logger.debug(
            "Writing event to stream",
            event_type=event_type,
            data_size=len(event.get("data", "")),
        )

        # If queue is full, remove oldest event
        if self._queue.full():
            try:
                self._queue.get_nowait()
                logger.debug("Queue full, removed oldest event")
            except asyncio.QueueEmpty:
                pass

        # Add to queue
        await self._queue.put(event)

    async def flush_prompts(self) -> None:
        """Flush buffered ``prompts`` events into the stream.

        Call this after the final assistant message so prompt metadata
        appears at the end of the SSE stream (matching ml-infra behavior).
        """
        for event in self._buffered_prompts:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await self._queue.put(event)
        self._buffered_prompts.clear()

    async def write_message(self, content: str) -> None:
        """
        Write a message event (convenience method).

        Args:
            content: Message content
        """
        await self.write_event("message", {"content": content})

    async def write_status(self, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Write a status event (convenience method).

        Args:
            status: Status message
            details: Optional additional status details
        """
        data = {"status": status}
        if details:
            data.update(details)
        await self.write_event("status", data)

    async def write_error(self, error: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Write an error event (convenience method).

        Args:
            error: Error message
            details: Optional error details
        """
        data = {"error": error}
        if details:
            data.update(details)
        await self.write_event("error", data)

    async def close(self) -> None:
        """Close the stream (no more events will be written)."""
        self._closed = True
        # Sentinel value to signal end of stream
        await self._queue.put(None)
        logger.debug("Stream closed")

    def __aiter__(self):
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> str:
        """Get next SSE-formatted event from the queue."""
        if self._closed and self._queue.empty():
            raise StopAsyncIteration

        item = await self._queue.get()

        if item is None:  # Sentinel value
            raise StopAsyncIteration

        # Format as Server-Sent Event
        event_type = item["event"]
        data = item["data"]
        formatted_event = f"event: {event_type}\r\ndata: {data}\r\n\r\n"

        logger.debug(
            "Yielding SSE event",
            event_type=event_type,
            size=len(formatted_event),
        )

        return formatted_event

    async def read(self) -> AsyncGenerator[str, None]:
        """
        Read events from stream as async generator.

        Yields:
            SSE-formatted event strings
        """
        logger.debug("Starting stream read")

        while True:
            if self._closed and self._queue.empty():
                logger.debug("Stream closed and queue empty")
                break

            try:
                item = await self._queue.get()

                if item is None:  # Sentinel value
                    logger.debug("Received stream end sentinel")
                    break

                # Format as Server-Sent Event
                event_type = item["event"]
                data = item["data"]
                formatted_event = f"event: {event_type}\r\ndata: {data}\r\n\r\n"

                logger.debug(
                    "Yielding SSE event",
                    event_type=event_type,
                    size=len(formatted_event),
                )

                yield formatted_event

                # Mark task as done
                self._queue.task_done()

            except Exception as e:
                logger.error("Error reading from stream", error=str(e), exc_info=True)
                raise

    def _truncate_event_data(self, event_data: str, original_size: int) -> str:
        """
        Truncate event data to stay under size limit.

        Attempts to maintain valid JSON structure.

        Args:
            event_data: JSON string to truncate
            original_size: Original size in bytes

        Returns:
            Truncated JSON string
        """
        # Reserve some space for wrapper and truncation message
        max_content_size = self.max_event_size_bytes - 1000

        try:
            # Parse original data
            parsed_data = json.loads(event_data)

            # Create truncated wrapper
            if isinstance(parsed_data, dict):
                # Truncate and mark as truncated
                content_str = json.dumps(parsed_data, separators=(",", ":"))
                if len(content_str.encode("utf-8")) > max_content_size:
                    truncated_str = content_str[:max_content_size]
                    # Try to find valid JSON end point
                    for i in range(len(truncated_str) - 1, -1, -1):
                        if truncated_str[i] in "}]":
                            truncated_str = truncated_str[:i+1]
                            break
                else:
                    truncated_str = content_str

                wrapper = {
                    "truncated": True,
                    "original_size_bytes": original_size,
                    "content": truncated_str,
                }
            else:
                # Non-dict data
                wrapper = {
                    "truncated": True,
                    "original_size_bytes": original_size,
                    "content": str(parsed_data)[:max_content_size],
                }

            result = json.dumps(wrapper)

        except json.JSONDecodeError:
            # Not valid JSON, wrap as-is
            wrapper = {
                "truncated": True,
                "original_size_bytes": original_size,
                "content": event_data[:max_content_size],
            }
            result = json.dumps(wrapper)

        final_size = len(result.encode("utf-8"))
        logger.info(
            "Truncated event data",
            original_size_kb=original_size // 1024,
            final_size_kb=final_size // 1024,
        )

        return result


def create_stream_writer(
    max_queue_size: int = 100,
    max_event_size_kb: int = 64,
) -> StreamWriter:
    """
    Create a StreamWriter instance.

    Args:
        max_queue_size: Maximum events in queue
        max_event_size_kb: Maximum event size in KB

    Returns:
        New StreamWriter instance
    """
    return StreamWriter(
        max_queue_size=max_queue_size,
        max_event_size_kb=max_event_size_kb,
    )


async def create_streaming_response(stream_writer: StreamWriter):
    """
    Create a FastAPI StreamingResponse from a StreamWriter.

    Args:
        stream_writer: StreamWriter to read from

    Returns:
        FastAPI StreamingResponse configured for SSE
    """
    from fastapi.responses import StreamingResponse

    async def event_generator():
        async for event in stream_writer.read():
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in Nginx
        },
    )
