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
from cortex.orchestration.usage_tracking import ModelUsageTracker
from cortex.orchestration.streaming import StreamHandler, StreamWriterProtocol
from cortex.orchestration.tools import ToolRegistry
from cortex.orchestration.middleware.summarization import (
    create_summarization_middleware,
)
from cortex.orchestration.observability.monitor import SwarmMonitor

logger = logging.getLogger(__name__)

# Lazy-imported when MCP is actually used
_MCPConfig = None
_MCPLoader = None
_mcp_registry = None


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
        use_mcp: Whether to load tools from MCP servers on first build.
            Defaults to False.  When True, the agent lazily loads tools
            from either a named server in the MCPServerRegistry or from
            the provided *mcp_config*.
        mcp_config: An ``MCPConfig`` object (or registered server name
            string) specifying which MCP server to connect to.  If
            ``use_mcp=True`` and this is ``None``, the first server in
            the registry is used.
        mcp_enabled_tools: If set, only include these MCP tools (allowlist).
            Takes precedence over *mcp_disabled_tools*.
        mcp_disabled_tools: Tool names to exclude from MCP results.
        summarization_strategy: When set, auto-prepends a summarization
            middleware. ``"trim"`` for lightweight message trimming (no LLM
            call), ``"summarize"`` for LLM-based summarization (uses the
            agent's own model unless *summarization_model* is given).
        summarization_model: Explicit model for the ``"summarize"``
            strategy.  Ignored when strategy is ``"trim"`` or ``None``.
        middleware: AgentMiddleware instances for advanced interception.
        context: Dict of context values injected into tools at call time
            (e.g. user_id, session_id). Passed to registry.set_context().
        checkpointer: LangGraph state backend. Defaults to an ephemeral
            MemorySaver (sufficient for single-request use). Pass a durable
            backend (e.g. PostgresSaver) for cross-request persistence.
        debug_monitor: When True, streaming methods (``stream``,
            ``stream_to_writer``) automatically record events via a
            ``SwarmMonitor`` and flush them in the ``finally`` block.
            The monitor file is written to
            ``agent_execution_history/swarm_monitor/<thread_id>/``.
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
        use_mcp: bool = False,
        mcp_config: Any | None = None,
        mcp_enabled_tools: list[str] | None = None,
        mcp_disabled_tools: list[str] | None = None,
        summarization_strategy: Literal["trim", "summarize"] | None = None,
        summarization_model: Any = None,
        middleware: Sequence[Any] | None = None,
        context: dict[str, Any] | None = None,
        checkpointer: Any = None,
        debug_monitor: bool = False,
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

        # MCP configuration
        self._use_mcp = use_mcp
        self._mcp_config = mcp_config
        self._mcp_enabled_tools = (
            set(mcp_enabled_tools) if mcp_enabled_tools else None
        )
        self._mcp_disabled_tools = (
            set(mcp_disabled_tools) if mcp_disabled_tools else None
        )

        # Summarization
        self._summarization_strategy = summarization_strategy
        self._summarization_model = summarization_model

        # Middleware
        self._middleware = list(middleware) if middleware else []

        # Context injection
        if context:
            self._registry.set_context(**context)

        # Checkpointer
        self._checkpointer = checkpointer

        # Debug monitor
        self._debug_monitor = debug_monitor

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

        monitor = (
            SwarmMonitor(conversation_id=thread_id)
            if self._debug_monitor
            else None
        )

        input_messages = list(messages or []) + [HumanMessage(content=message)]

        try:
            async for event in compiled.astream_events(
                {"messages": input_messages}, version="v2", config=config
            ):
                if monitor:
                    monitor.record_event(event, source_agent=self._name)
                yield event
        finally:
            if monitor:
                monitor.flush()

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

        monitor = (
            SwarmMonitor(conversation_id=thread_id)
            if self._debug_monitor
            else None
        )

        usage_tracker = ModelUsageTracker()
        input_messages = list(messages or []) + [HumanMessage(content=message)]
        agent_error: str | None = None

        try:
            async for event in compiled.astream_events(
                {"messages": input_messages}, version="v2", config=config
            ):
                usage_tracker.record_from_event(event)
                if monitor:
                    monitor.record_event(event, source_agent=self._name)
                await handler.handle_event(event, source_agent=self._name)
        except Exception as e:
            agent_error = str(e)
            logger.exception("Agent streaming failed: %s", e)
            await handler.send_error(str(e))
        finally:
            if monitor:
                monitor.flush()

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

        # Load MCP tools if enabled
        if self._use_mcp:
            await self._load_mcp_tools()

        # Build middleware list — prepend auto-created summarization middleware
        all_middleware = list(self._middleware)
        if self._summarization_strategy:
            sum_mw = create_summarization_middleware(
                strategy=self._summarization_strategy,
                model=self._summarization_model,
                model_name=(
                    self._model_config.model
                    if self._summarization_strategy == "summarize"
                    and self._summarization_model is None
                    else None
                ),
            )
            all_middleware.insert(0, sum_mw)

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

    def _should_include_mcp_tool(self, tool_name: str) -> bool:
        """Check if an MCP tool passes the enabled/disabled filters."""
        if self._mcp_enabled_tools is not None:
            return tool_name in self._mcp_enabled_tools
        if self._mcp_disabled_tools is not None:
            return tool_name not in self._mcp_disabled_tools
        return True

    async def _load_mcp_tools(self) -> None:
        """Load tools from an MCP server into the registry, applying filters."""
        try:
            from cortex.orchestration.mcp import MCPConfig, MCPLoader
        except ImportError:
            logger.warning(
                "MCP packages not installed.  Install with: "
                "pip install mcp langchain-mcp-adapters"
            )
            return

        transport = self._mcp_config

        # Resolve from registry if a string name is given
        if isinstance(transport, str):
            try:
                from cortex.orchestration.mcp.registry import mcp_server_registry
                config_obj = mcp_server_registry.get_config(transport)
                loader = MCPLoader.from_config(config_obj)
            except (ImportError, KeyError) as exc:
                logger.warning("MCP server '%s' not found: %s", transport, exc)
                return
        elif transport is not None and isinstance(transport, MCPConfig):
            loader = MCPLoader.from_config(transport)
        elif transport is None:
            # Try to use the first registered server
            try:
                from cortex.orchestration.mcp.registry import mcp_server_registry
                servers = mcp_server_registry.list_servers()
                if not servers:
                    logger.debug("MCP enabled but no servers registered")
                    return
                config_obj = mcp_server_registry.get_config(servers[0])
                loader = MCPLoader.from_config(config_obj)
            except ImportError:
                logger.debug("MCP registry not available")
                return
        else:
            raise TypeError(
                f"mcp_config must be str, MCPConfig, or None; got {type(transport)}"
            )

        try:
            async with loader:
                mcp_tools = await loader.load_tools()
                registered = 0
                for tool in mcp_tools:
                    if self._should_include_mcp_tool(tool.name):
                        self._registry.register(tool)
                        registered += 1
                logger.info(
                    "Loaded %d/%d MCP tools", registered, len(mcp_tools)
                )
        except Exception:
            logger.exception("Failed to load MCP tools")

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
