"""
Streaming Infrastructure

SSE event streaming, event types, and part management for streaming responses.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage


# =========================================================================
# Event Types
# =========================================================================


class EventType:
    """Event types for SSE streaming.

    These match the existing /chat/unified implementation and include
    additional types ported from ml-infra for rich MCP progress streaming.
    """

    ASSISTANT_MESSAGE = "assistant_message"
    ASSISTANT_THOUGHT = "assistant_thought"
    ASSISTANT_TOOL_REQUEST = "assistant_tool_request"
    ASSISTANT_TOOL_RESULT = "assistant_tool_result"
    MODEL_USAGE = "model_usage"
    ERROR = "error"
    DONE = "done"

    # Part streaming events
    PART_START = "part_start"
    PART_DELTA = "part_delta"
    PART_END = "part_end"

    # ARCHITECT mode
    DETAILED_ANALYSIS = "detailed_analysis"

    # Chat extensions
    TYPING_INDICATOR = "typing_indicator"
    CITATION = "citation"
    UI_ACTION = "ui_action"
    UI_ACTION_UPDATE = "ui_action_update"
    COLLECT_FEEDBACK = "collect_feedback"
    STATUS = "status"

    # MCP progress events (ported from ml-infra)
    PLAN_PRESENTED = "plan_presented"
    CAPABILITY_EXECUTION = "capability_execution"
    FINAL_YAML_CREATED = "final_yaml_created"
    KG_INSIGHTS = "kg_insights"


# =========================================================================
# Part Manager
# =========================================================================


@dataclass
class ActivePart:
    """State of an active streaming part."""

    id: str
    type: str
    sequence: int
    started_at: int  # epoch ms


class PartManager:
    """
    Manages part streaming lifecycle.

    Part streaming breaks events like assistant_thought into:
    - part_start: Begin a new streaming part
    - part_delta: Incremental content updates
    - part_end: Close the active part

    Example:
        pm = PartManager()

        # Start part
        start_data = pm.start_part("assistant_thought")
        await writer.write_event("part_start", start_data)

        # Send deltas
        for chunk in chunks:
            delta_data = pm.create_delta(chunk)
            await writer.write_event("part_delta", delta_data)

        # End part
        end_data = pm.end_part()
        await writer.write_event("part_end", end_data)
    """

    # Event types that can be streamed as parts
    STREAMABLE_TYPES = {"assistant_thought", "detailed_analysis"}

    def __init__(self):
        self._active_part: ActivePart | None = None
        self._sequence: int = 0

    def should_stream_as_part(self, event_type: str) -> bool:
        """
        Check if event type supports part streaming.

        Args:
            event_type: The event type to check

        Returns:
            True if event type can be streamed as parts
        """
        return event_type in self.STREAMABLE_TYPES

    def start_part(self, event_type: str) -> dict:
        """
        Start a new streaming part.

        Args:
            event_type: The type of content being streamed

        Returns:
            part_start event data: {id, type, sequence, timestamp}
        """
        self._sequence += 1
        self._active_part = ActivePart(
            id=str(uuid.uuid4()),
            type=event_type,
            sequence=self._sequence,
            started_at=int(time.time() * 1000),
        )
        return {
            "id": self._active_part.id,
            "type": event_type,
            "sequence": self._sequence,
            "timestamp": self._active_part.started_at,
        }

    def create_delta(self, content: str) -> dict:
        """
        Create delta for active part.

        Args:
            content: Content chunk to send

        Returns:
            part_delta event data: {id, delta}

        Raises:
            ValueError: If no active part
        """
        if not self._active_part:
            raise ValueError("No active part - call start_part() first")
        return {
            "id": self._active_part.id,
            "delta": content,
        }

    def end_part(self) -> dict | None:
        """
        End active part.

        Returns:
            part_end event data: {id} or None if no active part
        """
        if not self._active_part:
            return None
        data = {"id": self._active_part.id}
        self._active_part = None
        return data

    @property
    def has_active_part(self) -> bool:
        """Check if there's an active part."""
        return self._active_part is not None

    @property
    def active_part_id(self) -> str | None:
        """Get active part ID if exists."""
        return self._active_part.id if self._active_part else None


# =========================================================================
# Stream Writer Protocol
# =========================================================================


class StreamWriterProtocol(Protocol):
    """Protocol for stream writers."""

    async def write_event(self, event_type: str, data: Any) -> None:
        """Write an event to the stream."""
        ...

    async def close(self) -> None:
        """Close the stream."""
        ...


# =========================================================================
# Stream Handler
# =========================================================================


class StreamHandler:
    """
    Handles conversion of LangGraph events to SSE format.

    This handler processes LangGraph `astream_events` and converts them
    to the SSE event format expected by chat endpoints.

    Features:
    - Mode-aware thought event conversion (STANDARD vs ARCHITECT)
    - Part streaming for incremental content (opt-in)
    - Configurable event suppression via ``suppress_events``

    Does NOT track token usage. Callers should create a
    ``ModelUsageTracker`` externally and feed events to it.

    Example:
        handler = StreamHandler(
            stream_writer,
            enable_part_streaming=True,
            mode="ARCHITECT",
        )

        async for event in agent.astream_events({"messages": [...]}):
            await handler.handle_event(event)

        await handler.close_active_part()
        await handler.send_done()

    Suppression example (complete messages only, no tool events):
        handler = StreamHandler(
            stream_writer,
            suppress_events={
                StreamHandler.TOKENS,
                StreamHandler.TOOL_REQUEST,
                StreamHandler.TOOL_RESULT,
            },
        )
    """

    # Suppressible event categories
    TOKENS = "tokens"
    """Token-by-token streaming. When suppressed, complete messages
    are still sent from on_chat_model_end."""

    ASSISTANT_MESSAGE = "assistant_message"
    """All assistant messages (both token-by-token and complete).
    Suppressing this also implies TOKENS."""

    TOOL_REQUEST = "tool_request"
    """Tool request events (on_tool_start)."""

    TOOL_RESULT = "tool_result"
    """Tool result events (on_tool_end)."""

    THOUGHT = "thought"
    """Assistant thought / detailed analysis events."""

    ALL = "all"
    """All streamable event categories. Convenience shorthand for
    suppressing every event from an agent."""

    _ALL_CATEGORIES = frozenset(
        {
            TOKENS,
            ASSISTANT_MESSAGE,
            TOOL_REQUEST,
            TOOL_RESULT,
            THOUGHT,
        }
    )

    def __init__(
        self,
        stream_writer: StreamWriterProtocol,
        agent_name: str | None = None,
        enable_part_streaming: bool = False,
        enable_full_message_streaming: bool = True,
        mode: str = "STANDARD",
        suppress_events: set[str] | None = None,
        agent_suppress_events: dict[str, set[str]] | None = None,
    ):
        """
        Initialize the stream handler.

        Args:
            stream_writer: StreamWriter to write events to
            agent_name: Optional agent name to include in events
            enable_part_streaming: Wrap thought/analysis content in
                part_start / part_delta / part_end events.
            enable_full_message_streaming: When True, on_chat_model_end sends the
                full message (and on_chat_model_stream events should be filtered
                upstream). When False, on_chat_model_stream sends tokens and
                on_chat_model_end skips content to avoid duplicates.
            mode: Chat mode (STANDARD or ARCHITECT)
            suppress_events: Set of event categories to suppress globally.
                Use the class constants (TOKENS, ASSISTANT_MESSAGE,
                TOOL_REQUEST, TOOL_RESULT, THOUGHT). Default is None
                (stream everything).
            agent_suppress_events: Per-agent suppression. Maps agent name
                to a set of event categories to suppress for that agent.
                Use ``StreamHandler.ALL`` to suppress all events from an
                agent. The source agent is passed by the caller via
                ``handle_event(event, source_agent=...)``.
        """
        self._writer = stream_writer
        self._agent_name = agent_name
        self._enable_part_streaming = enable_part_streaming
        self._enable_full_message_streaming = enable_full_message_streaming
        self._mode = mode.upper() if mode else "STANDARD"
        self._suppress = suppress_events or set()

        # Per-agent suppression: expand ALL into concrete categories
        self._agent_suppress: dict[str, set[str]] = {}
        if agent_suppress_events:
            for name, categories in agent_suppress_events.items():
                if self.ALL in categories:
                    self._agent_suppress[name] = set(self._ALL_CATEGORIES)
                else:
                    self._agent_suppress[name] = set(categories)

        # Part manager for streaming (only if enabled)
        self._part_manager = PartManager() if enable_part_streaming else None

        # Tracks whether on_chat_model_stream sent content for the current
        # model call, so on_chat_model_end can skip re-sending the same text.
        self._streamed_content = False

    # =========================================================================
    # Message Events
    # =========================================================================

    async def send_message(self, content: str) -> None:
        """
        Send an assistant message event.

        Suppressed when ASSISTANT_MESSAGE is in suppress_events.

        Args:
            content: The message content
        """
        if self.ASSISTANT_MESSAGE in self._suppress:
            return

        data = {"v": content}
        if self._agent_name:
            data["agent"] = self._agent_name

        await self._writer.write_event(EventType.ASSISTANT_MESSAGE, data)

    async def send_thought(self, content: str) -> None:
        """
        Send assistant thought event (mode-aware, part-aware).

        In ARCHITECT mode, emits "detailed_analysis" instead of "assistant_thought".
        If part streaming is enabled, uses part_start/delta/end events.
        Suppressed when THOUGHT is in suppress_events.

        Args:
            content: The thought content
        """
        if self.THOUGHT in self._suppress:
            return

        # Determine event type based on mode
        event_type = (
            EventType.DETAILED_ANALYSIS
            if self._mode == "ARCHITECT"
            else EventType.ASSISTANT_THOUGHT
        )

        if self._enable_part_streaming and self._part_manager:
            await self._send_as_part(event_type, content)
        else:
            data = {"v": content}
            if self._agent_name:
                data["agent"] = self._agent_name
            await self._writer.write_event(event_type, data)

    async def _send_as_part(self, event_type: str, content: str) -> None:
        """
        Send content using part streaming.

        Args:
            event_type: The event type being streamed
            content: Content chunk
        """
        # Start part if not active
        if not self._part_manager.has_active_part:
            start_data = self._part_manager.start_part(event_type)
            await self._writer.write_event(EventType.PART_START, start_data)

        # Send delta
        delta_data = self._part_manager.create_delta(content)
        await self._writer.write_event(EventType.PART_DELTA, delta_data)

    async def close_active_part(self) -> None:
        """Close any active streaming part."""
        if self._part_manager and self._part_manager.has_active_part:
            end_data = self._part_manager.end_part()
            if end_data:
                await self._writer.write_event(EventType.PART_END, end_data)

    # =========================================================================
    # Error and Done Events
    # =========================================================================

    async def send_error(self, error: str) -> None:
        """
        Send an error event.

        Args:
            error: The error message
        """
        await self._writer.write_event(EventType.ERROR, {"error": error})

    async def send_done(self) -> None:
        """
        Send the done event and close the stream.
        """
        await self._writer.write_event(EventType.DONE, {})
        await self._writer.close()

    # =========================================================================
    # Tool Events
    # =========================================================================

    async def send_tool_request(
        self,
        tool_id: str,
        name: str,
        arguments: dict,
    ) -> None:
        """
        Send a tool request event.

        Args:
            tool_id: Unique ID for this tool call
            name: Tool name
            arguments: Tool arguments
        """
        data = {
            "v": [
                {
                    "id": tool_id,
                    "name": name,
                    "arguments": arguments,
                }
            ]
        }
        await self._writer.write_event(EventType.ASSISTANT_TOOL_REQUEST, data)

    async def send_tool_result(
        self,
        tool_id: str,
        name: str,
        result: Any,
    ) -> None:
        """
        Send a tool result event.

        Args:
            tool_id: ID from the tool request
            name: Tool name
            result: Tool result
        """
        data = {
            "v": [
                {
                    "id": tool_id,
                    "name": name,
                    "result": result,
                }
            ]
        }
        await self._writer.write_event(EventType.ASSISTANT_TOOL_RESULT, data)

    # =========================================================================
    # Message Chunk Handling (for astream with stream_mode="messages")
    # =========================================================================

    async def handle_message_chunk(self, message: Any, metadata: dict) -> None:
        """
        Handle a message chunk from astream(stream_mode="messages").

        This processes complete messages (not token-by-token streaming).

        Args:
            message: The message (AIMessage, AIMessageChunk, ToolMessage, etc.)
            metadata: Metadata about the message
        """
        # Handle AIMessage or AIMessageChunk
        if isinstance(message, (AIMessage, AIMessageChunk)):
            # Check for tool calls
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                for tool_call in tool_calls:
                    tool_id = tool_call.get("id", "")
                    name = tool_call.get("name", "")
                    args = tool_call.get("args", {})
                    await self.send_tool_request(tool_id, name, args)

            # Handle text content
            content = message.content
            if content and isinstance(content, str):
                await self.send_message(content)

        # Handle ToolMessage (tool results)
        elif isinstance(message, ToolMessage):
            tool_id = getattr(message, "tool_call_id", "")
            name = getattr(message, "name", "")
            result = message.content
            await self.send_tool_result(tool_id, name, result)

    # =========================================================================
    # Event Handling
    # =========================================================================

    def _is_suppressed(self, category: str, source_agent: str) -> bool:
        """Check global and per-agent suppression for a category."""
        if category in self._suppress:
            return True
        if source_agent and source_agent in self._agent_suppress:
            return category in self._agent_suppress[source_agent]
        return False

    async def handle_event(self, event: dict, source_agent: str = "") -> None:
        """
        Handle a LangGraph event from astream_events.

        Converts LangGraph events to SSE events and writes them.
        Applies both global and per-agent suppression.

        Args:
            event: LangGraph event from astream_events
            source_agent: Name of the agent that produced this event.
                Used for per-agent suppression. The caller is responsible
                for resolving this from the event metadata.
        """
        event_type = event.get("event", "")
        data = event.get("data", {})

        if event_type == "on_chat_model_stream":
            await self._handle_chat_stream(data, source_agent)
        elif event_type == "on_chat_model_end":
            await self._handle_chat_model_end(data, source_agent)
        elif event_type == "on_tool_start":
            await self._handle_tool_start(event, source_agent)
        elif event_type == "on_tool_end":
            await self._handle_tool_end(event, source_agent)

    async def _handle_chat_stream(self, data: dict, source_agent: str = "") -> None:
        """Handle chat model stream event (token-by-token)."""
        if self._is_suppressed(self.TOKENS, source_agent) or self._is_suppressed(
            self.ASSISTANT_MESSAGE, source_agent
        ):
            return

        chunk = data.get("chunk")

        if isinstance(chunk, AIMessageChunk):
            content = chunk.content
            if content:  # Skip empty content
                self._streamed_content = True
                if isinstance(content, str):
                    await self.send_message(content)
                elif isinstance(content, list):
                    # Claude/Anthropic format: list of content blocks
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                await self.send_message(text)
                        elif isinstance(block, str) and block:
                            await self.send_message(block)

    async def _handle_chat_model_end(self, data: dict, source_agent: str = "") -> None:
        """Handle chat model end event (full message).

        When enable_full_message_streaming=True, sends the complete message
        (unless tokens were already streamed via on_chat_model_stream).
        When False, token-by-token content was already sent via
        _handle_chat_stream, so content is skipped here.
        """
        if self._is_suppressed(self.ASSISTANT_MESSAGE, source_agent):
            self._streamed_content = False
            return

        output = data.get("output")

        if output and isinstance(output, (AIMessage, AIMessageChunk)):
            # Only send message content when full-message mode is active
            # AND tokens weren't already streamed via on_chat_model_stream.
            if self._enable_full_message_streaming and not self._streamed_content:
                content = output.content
                if content:
                    if isinstance(content, str):
                        await self.send_message(content)
                    elif isinstance(content, list):
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif isinstance(block, str):
                                text_parts.append(block)
                        if text_parts:
                            await self.send_message("".join(text_parts))

            # Reset for the next model call
            self._streamed_content = False

    async def _handle_tool_start(self, event: dict, source_agent: str = "") -> None:
        """Handle tool start event."""
        if self._is_suppressed(self.TOOL_REQUEST, source_agent):
            return

        tool_id = event.get("run_id", "")
        name = event.get("name", "")
        data = event.get("data", {})
        arguments = data.get("input", {})

        await self.send_tool_request(tool_id, name, arguments)

    async def _handle_tool_end(self, event: dict, source_agent: str = "") -> None:
        """Handle tool end event."""
        if self._is_suppressed(self.TOOL_RESULT, source_agent):
            return

        tool_id = event.get("run_id", "")
        name = event.get("name", "")
        data = event.get("data", {})
        result = data.get("output", {})

        # Convert non-serializable objects to string
        if hasattr(result, "content"):
            # ToolMessage or similar LangChain message type
            result = result.content
        elif not isinstance(result, (str, dict, list, int, float, bool, type(None))):
            result = str(result)

        await self.send_tool_result(tool_id, name, result)
