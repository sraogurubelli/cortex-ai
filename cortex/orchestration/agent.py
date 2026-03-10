"""
Agent

High-level agent that owns the full lifecycle: build, run/stream, track usage, cleanup.

Layers on top of AgentConfig + build_agent() to eliminate boilerplate.
For full control, use AgentConfig + build_agent() directly.

Example (minimal):
    agent = Agent(name="assistant", system_prompt="You are helpful.")
    result = await agent.run("What is 2 + 2?")
    print(result.response)

Example (with tools and streaming):
    agent = Agent(
        name="coder",
        system_prompt="You help with code.",
        tools=[search_tool, read_file_tool],
        context={"user_id": "user123"},
    )
    async for event in agent.stream("Fix the bug"):
        print(event)

Example (SSE streaming via writer):
    result = await agent.stream_to_writer(
        "Fix the bug",
        stream_writer=my_sse_writer,
    )
    print(result.token_usage)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Literal, Sequence
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from cortex.orchestration.builder import build_agent
from cortex.orchestration.config import AgentConfig, ModelConfig
from cortex.orchestration.observability import ModelUsageTracker
from cortex.orchestration.streaming import StreamHandler, StreamWriterProtocol
from cortex.orchestration.tools import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result from an agent run (both streaming and non-streaming)."""

    response: str
    """Final AI response text."""

    messages: list[BaseMessage] = field(default_factory=list)
    """Full conversation history from the run."""

    token_usage: dict[str, Any] = field(default_factory=dict)
    """Per-model token counts plus optional cache metrics.

    Shape: ``{model: {prompt_tokens, completion_tokens, total_tokens}, ...}``
    When Anthropic prompt caching is active a ``"cache"`` key is added:
    ``{"cache": {"cache_read": N, "cache_creation": M}}``
    """

    error: str | None = None
    """Error message if the run failed, None on success."""


class Agent:
    """
    High-level agent that owns the full lifecycle.

    Wraps AgentConfig + build_agent() with convenience methods for
    running, streaming, and tracking usage.

    The Agent creates its own ToolRegistry, ModelUsageTracker, and
    MemorySaver checkpointer internally. Pass a pre-configured
    tool_registry to share tools across agents or add domain-specific
    tools after construction via agent.tool_registry.

    Args:
        name: Agent name (used in system prompt fallback and logging).
        system_prompt: System prompt for the agent.
        description: Agent description (used in default system prompt).
        model: Model name string or ModelConfig. Defaults to "gpt-4o".
        tools: Tools to register. Can be BaseTool objects, callables,
            or string names (resolved from tool_registry). If None,
            uses all tools from the registry.
        tool_registry: Pre-configured ToolRegistry. If None, uses
            ToolRegistry.with_defaults() (empty by default).
            Pass a configured ToolRegistry with registered tools.
        middleware: AgentMiddleware instances for advanced interception.
        context: Dict of context values injected into tools at call time
            (e.g. user_id, session_id). Passed to registry.set_context().
        checkpointer: LangGraph state backend. Defaults to an ephemeral
            MemorySaver (sufficient for single-request use). Pass a durable
            backend (e.g. PostgresSaver) for cross-request persistence.
        suppress_events: Event categories to suppress from SSE output.
            Uses StreamHandler constants (e.g. "assistant_message",
            "tool_request").
        max_iterations: Maximum agent iterations before stopping.
        mode: Chat mode affecting streaming behavior ("standard" or "architect").
    """

    def __init__(
        self,
        name: str,
        system_prompt: str = "",
        description: str = "",
        *,
        model: str | ModelConfig = "gpt-4o",
        tools: list[str | BaseTool | Callable] | None = None,
        tool_registry: ToolRegistry | None = None,
        middleware: Sequence[Any] | None = None,
        context: dict[str, Any] | None = None,
        checkpointer: Any = None,
        suppress_events: set[str] | None = None,
        max_iterations: int = 25,
        mode: Literal["standard", "architect"] = "standard",
    ):
        self._name = name
        self._system_prompt = system_prompt
        self._description = description
        self._mode = mode
        self._max_iterations = max_iterations
        self._suppress_events = set(suppress_events) if suppress_events else set()

        # Model config
        if isinstance(model, str):
            self._model_config = ModelConfig(model=model)
        else:
            self._model_config = model

        # Tools
        self._tools = tools
        self._registry = (
            tool_registry if tool_registry is not None else ToolRegistry.with_defaults()
        )

        # Middleware
        self._middleware = list(middleware) if middleware else []

        # Context injection
        if context:
            self._registry.set_context(**context)

        # Checkpointer
        self._checkpointer = checkpointer

        # Lazy-built compiled graph
        self._compiled: CompiledStateGraph | None = None

    @property
    def tool_registry(self) -> ToolRegistry:
        """Access the tool registry to register additional tools."""
        return self._registry

    @property
    def model_config(self) -> ModelConfig:
        """Access the model configuration."""
        return self._model_config

    async def run(
        self,
        message: str,
        *,
        messages: list[BaseMessage] | None = None,
        thread_id: str | None = None,
    ) -> AgentResult:
        """
        Run the agent and return the result.

        Args:
            message: User message to send to the agent.
            messages: Optional preceding messages (e.g. knowledge injection).
            thread_id: Thread ID for checkpointer state. Auto-generated if None.

        Returns:
            AgentResult with response text, full history, and token usage.
        """
        compiled = await self._build()
        thread_id = thread_id or str(uuid4())
        config = self._run_config(thread_id)

        input_messages = list(messages or []) + [HumanMessage(content=message)]

        try:
            result = await compiled.ainvoke({"messages": input_messages}, config=config)
        except Exception as e:
            logger.exception("Agent run failed: %s", e)
            return AgentResult(response=f"Error: {e}", error=str(e))

        all_messages = result.get("messages", [])

        # Extract final response text
        response_text = self._extract_response(all_messages)

        # Aggregate token usage
        tracker = ModelUsageTracker()
        tracker.record_from_messages(all_messages)
        token_usage = tracker.get_usage()

        return AgentResult(
            response=response_text,
            messages=all_messages,
            token_usage=token_usage,
        )

    async def stream(
        self,
        message: str,
        *,
        messages: list[BaseMessage] | None = None,
        thread_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """
        Stream raw LangGraph events.

        Yields dicts from LangGraph's astream_events(version="v2").
        Use this for custom event handling. For SSE streaming, use
        stream_to_writer() instead.

        Args:
            message: User message to send to the agent.
            messages: Optional preceding messages.
            thread_id: Thread ID for checkpointer state.

        Yields:
            LangGraph event dicts.
        """
        compiled = await self._build()
        thread_id = thread_id or str(uuid4())
        config = self._run_config(thread_id)

        input_messages = list(messages or []) + [HumanMessage(content=message)]

        async for event in compiled.astream_events(
            {"messages": input_messages}, version="v2", config=config
        ):
            yield event

    async def stream_to_writer(
        self,
        message: str,
        stream_writer: StreamWriterProtocol,
        *,
        messages: list[BaseMessage] | None = None,
        thread_id: str | None = None,
        enable_part_streaming: bool = False,
    ) -> AgentResult:
        """
        Stream agent output through a StreamWriter (SSE).

        Handles the full streaming lifecycle: event conversion,
        usage tracking, and sending usage events.

        Does NOT send a "done" event or close the writer — the caller
        is responsible for that (typically after sending domain-specific
        events like YAML responses).

        Args:
            message: User message to send to the agent.
            stream_writer: Writer implementing StreamWriterProtocol.
            messages: Optional preceding messages.
            thread_id: Thread ID for checkpointer state.
            enable_part_streaming: Wrap thought/analysis events in
                part_start / part_delta / part_end envelopes.

        Returns:
            AgentResult with response, messages, token/cache usage, and error.
        """
        compiled = await self._build()
        thread_id = thread_id or str(uuid4())
        config = self._run_config(thread_id)

        handler = StreamHandler(
            stream_writer=stream_writer,
            agent_name=self._name,
            enable_part_streaming=enable_part_streaming,
            mode=self._mode.upper(),
            suppress_events=self._suppress_events or None,
        )

        usage_tracker = ModelUsageTracker()
        input_messages = list(messages or []) + [HumanMessage(content=message)]
        agent_error: str | None = None

        try:
            async for event in compiled.astream_events(
                {"messages": input_messages}, version="v2", config=config
            ):
                usage_tracker.record_from_event(event)
                await handler.handle_event(event, source_agent=self._name)
        except Exception as e:
            agent_error = str(e)
            logger.exception("Agent streaming failed: %s", e)
            await handler.send_error(str(e))

        await handler.close_active_part()

        # Retrieve full history from checkpointer for accurate usage
        all_messages = await self._get_history(compiled, config)
        if all_messages:
            primary_tracker = ModelUsageTracker()
            primary_tracker.record_from_messages(all_messages)
            token_usage = primary_tracker.get_usage()
        else:
            # Fallback: use event-based tracker
            token_usage = usage_tracker.get_usage()

        # Send model_usage event (unless suppressed)
        if "model_usage" not in self._suppress_events:
            if token_usage:
                await stream_writer.write_event("model_usage", token_usage)

        response_text = self._extract_response(all_messages)

        return AgentResult(
            response=response_text,
            messages=all_messages,
            token_usage=token_usage,
            error=agent_error,
        )

    async def run_streaming(
        self,
        message: str,
        *,
        messages: list[BaseMessage] | None = None,
        thread_id: str | None = None,
    ) -> "AgentResult":
        """
        Run the agent with streaming internally, returning a result like run().

        Streams events for usage tracking but does not write to any stream
        writer. Useful when you want accurate token usage from streaming
        events but don't need SSE output.

        Args:
            message: User message to send to the agent.
            messages: Optional preceding messages.
            thread_id: Thread ID for checkpointer state.

        Returns:
            AgentResult with response text, full history, and token usage.
        """
        compiled = await self._build()
        thread_id = thread_id or str(uuid4())
        config = self._run_config(thread_id)

        usage_tracker = ModelUsageTracker()
        input_messages = list(messages or []) + [HumanMessage(content=message)]

        try:
            async for event in compiled.astream_events(
                {"messages": input_messages}, version="v2", config=config
            ):
                usage_tracker.record_from_event(event)
        except Exception as e:
            logger.exception("Agent streaming run failed: %s", e)
            return AgentResult(response=f"Error: {e}", error=str(e))

        # Retrieve full history from checkpointer
        all_messages = await self._get_history(compiled, config)

        response_text = self._extract_response(all_messages)

        if all_messages:
            primary_tracker = ModelUsageTracker()
            primary_tracker.record_from_messages(all_messages)
            token_usage = primary_tracker.get_usage()
        else:
            token_usage = usage_tracker.get_usage()

        return AgentResult(
            response=response_text,
            messages=all_messages,
            token_usage=token_usage,
        )

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _run_config(self, thread_id: str) -> dict:
        """Build the LangGraph run config."""
        return {
            "recursion_limit": self._max_iterations * 2,
            "configurable": {"thread_id": thread_id},
        }

    async def _build(self) -> CompiledStateGraph:
        """Build or return cached compiled graph."""
        if self._compiled is not None:
            return self._compiled

        # Build middleware list
        all_middleware = list(self._middleware)

        # MemorySaver is ephemeral (in-process dict) — it does NOT persist
        # across requests.  It exists so aget_state() works within a single
        # run (needed by _get_history to build AgentResult).  For cross-request
        # persistence, pass a durable checkpointer (e.g. PostgresSaver).
        checkpointer = (
            self._checkpointer if self._checkpointer is not None else MemorySaver()
        )

        config = AgentConfig(
            name=self._name,
            description=self._description,
            model=self._model_config,
            system_prompt=self._system_prompt,
            tools=self._tools,
            middleware=all_middleware,
            checkpointer=checkpointer,
            mode=self._mode,
        )

        self._compiled = build_agent(config, tool_registry=self._registry)
        return self._compiled

    async def _get_history(
        self, compiled: CompiledStateGraph, config: dict
    ) -> list[BaseMessage]:
        """Retrieve full message history from checkpointer."""
        try:
            state = await compiled.aget_state(config)
            return state.values.get("messages", [])
        except Exception as e:
            logger.warning("Failed to retrieve checkpointer state: %s", e)
            return []

    @staticmethod
    def _extract_response(messages: list[BaseMessage]) -> str:
        """Extract the final AI response text from message history."""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content if isinstance(msg.content, str) else str(msg.content)
        return ""
