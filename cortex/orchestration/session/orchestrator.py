"""
Session Orchestrator — single entry point for running an agent session.

Composes all building blocks (context, tools, MCP, skills, agent build,
streaming, usage tracking, persistence, cleanup) into a unified flow,
replacing ad-hoc wiring in route handlers.

Ported patterns from ml-infra unified_chat/session/runner.py:
  - Checkpoint health check with graceful fallback to conversation history
  - Smart message deduplication (skip history when checkpoint exists)
  - Guaranteed stream finalization (done event + close in finally block)
  - Langfuse span wrapping for observability
  - MCP progress streaming for long tool calls
  - Swarm support (multi-agent with handoffs)
  - Generic event hooks for extensible analytics
  - Conversation context sync during execution

Usage::

    from cortex.orchestration.session.orchestrator import SessionOrchestrator

    orchestrator = SessionOrchestrator()
    result = await orchestrator.run_session(SessionConfig(
        model="claude-sonnet-4-20250514",
        system_prompt="You are a helpful assistant.",
        message="Hello",
        tenant_id="acc_123",
        project_id="prj_456",
        principal_id="usr_789",
        conversation_id="conv_abc",
        stream_writer=writer,
    ))
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from cortex.orchestration.context import request_context
from cortex.orchestration.tools import ToolRegistry

logger = logging.getLogger(__name__)


# =============================================================================
# Event Hook Protocol
# =============================================================================


class SessionEventHook(Protocol):
    """Protocol for session lifecycle event hooks.

    Implement this to receive notifications at key points in the session
    lifecycle (analytics, observability, audit logging, etc.).

    All methods are optional -- implement only the ones you need.
    Hooks must not raise exceptions; errors are logged and swallowed.
    """

    async def on_session_start(self, config: SessionConfig, metadata: dict) -> None:
        ...

    async def on_session_complete(
        self, config: SessionConfig, result: SessionResult, metadata: dict
    ) -> None:
        ...

    async def on_session_error(
        self, config: SessionConfig, error: Exception, metadata: dict
    ) -> None:
        ...


# =============================================================================
# Built-in Analytics Hook
# =============================================================================


class AnalyticsHook:
    """Pluggable analytics hook that emits session lifecycle events.

    Fires ``started``, ``completed``, and ``failed`` events with rich metadata
    (provider, model, timing, token usage) to a configurable backend.

    Subclass and override ``_emit`` to send events to Segment, a webhook,
    a message queue, or any other analytics destination.

    Example::

        class SegmentAnalyticsHook(AnalyticsHook):
            async def _emit(self, event_name, properties):
                segment.track(user_id=properties.get("principal_id"), event=event_name, properties=properties)

        config = SessionConfig(
            ...,
            event_hooks=[SegmentAnalyticsHook(source="cortex-ai")],
        )
    """

    def __init__(self, source: str = "cortex-ai"):
        self._source = source

    async def _emit(self, event_name: str, properties: dict) -> None:
        """Override this method to send events to your analytics backend.

        The default implementation logs at INFO level.
        """
        logger.info("analytics_event: %s %s", event_name, properties)

    async def on_session_start(self, config: "SessionConfig", metadata: dict) -> None:
        await self._emit("session_started", {
            "source": self._source,
            "model": config.model,
            "mode": config.mode,
            "agent_name": config.agent_name,
            "tenant_id": config.tenant_id,
            "project_id": config.project_id,
            "principal_id": config.principal_id,
            "conversation_id": config.conversation_id,
            "use_mcp": config.use_mcp,
            "use_swarm": config.use_swarm,
            **metadata,
        })

    async def on_session_complete(
        self, config: "SessionConfig", result: "SessionResult", metadata: dict,
    ) -> None:
        await self._emit("session_completed", {
            "source": self._source,
            "model": config.model,
            "mode": config.mode,
            "agent_name": config.agent_name,
            "tenant_id": config.tenant_id,
            "principal_id": config.principal_id,
            "conversation_id": config.conversation_id,
            "duration_ms": result.duration_ms,
            "response_length": len(result.final_response),
            **result.usage,
            **metadata,
        })

    async def on_session_error(
        self, config: "SessionConfig", error: Exception, metadata: dict,
    ) -> None:
        await self._emit("session_failed", {
            "source": self._source,
            "model": config.model,
            "agent_name": config.agent_name,
            "tenant_id": config.tenant_id,
            "conversation_id": config.conversation_id,
            "error_type": type(error).__name__,
            "error_message": str(error)[:500],
            **metadata,
        })


# =============================================================================
# MCP Progress Handler
# =============================================================================


async def _handle_mcp_progress(
    params: Any,
    stream_writer: Any,
    mode: str = "standard",
) -> None:
    """Convert MCP progress notifications into rich SSE events.

    Translates MCP progress JSON into structured SSE events including
    part-based streaming for multi-step tool executions. Ported from
    ml-infra's ``handle_mcp_progress`` pattern.

    Supported MCP event types and their SSE mappings:
      - ``assistant_message`` → ``assistant_thought`` (or ``detailed_analysis``)
      - ``assistant_thought`` → ``assistant_thought`` (or ``detailed_analysis``)
      - ``part_start`` → ``part_start`` (begin streaming part)
      - ``part_delta`` → ``part_delta`` (incremental content)
      - ``part_end`` → ``part_end`` (close streaming part)
      - ``plan_presented`` → ``plan_presented``
      - ``capability_execution`` → ``capability_execution``
      - ``final_yaml_created`` → ``final_yaml_created``
      - ``kg_insights`` → ``kg_insights``
      - ``error`` with ``eof`` → ``assistant_thought`` completion

    Args:
        params: Progress notification params from MCP server.
        stream_writer: StreamWriter for SSE output.
        mode: Chat mode (standard/architect) — affects thought event names.
    """
    import json as _json

    if not params or not stream_writer:
        return

    message = getattr(params, "message", None)
    if not message or not isinstance(message, str):
        return

    try:
        message_data = _json.loads(message)
        if not isinstance(message_data, dict) or "data" not in message_data:
            return

        if message_data.get("data") == "eof" and message_data.get("type") == "error":
            logger.debug("MCP tool stream closed")
            await stream_writer.write_event(
                "assistant_thought", {"v": "Tool call complete."}
            )
            return

        try:
            data = _json.loads(message_data["data"])
        except (_json.JSONDecodeError, TypeError):
            data = message_data["data"]
            if not isinstance(data, dict):
                return

        event_type = message_data.get("type", "unknown")

        # Part-based streaming events pass through directly
        if event_type in ("part_start", "part_delta", "part_end"):
            await stream_writer.write_event(event_type, data)
            return

        # Capability / plan / result events pass through
        if event_type in (
            "plan_presented",
            "capability_execution",
            "final_yaml_created",
            "kg_insights",
        ):
            await stream_writer.write_event(event_type, data)
            return

        # Thought events: map assistant_message → assistant_thought
        if event_type == "assistant_message":
            event_type = "assistant_thought"
        if event_type == "assistant_thought" and mode == "architect":
            event_type = "detailed_analysis"

        await stream_writer.write_event(event_type, data)

    except _json.JSONDecodeError:
        logger.warning("Failed to decode MCP progress message")
    except Exception:
        logger.exception("Error processing MCP progress notification")


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class SessionConfig:
    """Configuration for a single session run."""

    # User message
    message: str = ""
    conversation_history: list[dict] = field(default_factory=list)

    # Model
    model: str = "gpt-4o"
    temperature: float = 0.0

    # System prompt
    system_prompt: str = ""

    # Request context
    tenant_id: str = ""
    project_id: str = ""
    principal_id: str = ""
    conversation_id: str = ""
    request_id: str = ""
    agent_name: str = "assistant"

    # Streaming
    stream_writer: Optional[Any] = None
    streaming: bool = True
    enable_part_streaming: bool = False
    enable_full_message_streaming: bool = True

    # Mode (standard / architect)
    mode: str = "standard"

    # Features
    use_tools: bool = True
    extra_tools: list[Any] = field(default_factory=list)
    use_mcp: bool = False
    mcp_config: Optional[str] = None
    use_summarization: bool = False
    summarization_strategy: Optional[str] = None
    use_filesystem: bool = False
    use_code_execution: bool = False
    use_prompt_caching: bool = False
    use_swarm: bool = False
    swarm_agents: list[Any] = field(default_factory=list)
    use_skills: bool = False
    skills_module: Optional[str] = None
    use_semantic_memory: bool = False
    semantic_memory_user_id: Optional[str] = None

    # Attachments (file references on the user message)
    attachments: list[dict] = field(default_factory=list)

    # System event (UI action continuation)
    system_event: Optional[dict] = None

    # Agent overrides
    max_iterations: int = 25
    thread_id: Optional[str] = None

    # Debug
    debug_monitor: bool = False

    # ---- Safety & Guardrails ----
    enable_pii_redaction: bool = False
    pii_entity_types: Optional[list[str]] = None
    enable_input_guardrails: bool = True
    enable_output_guardrails: bool = True
    system_prompt_fingerprints: list[str] = field(default_factory=list)
    guardrail_action: str = "block"
    max_total_tokens: int = 0
    max_completion_tokens: int = 0
    enable_feedback: bool = False
    feedback_reasons: Optional[list[str]] = None
    enable_history_dump: bool = False

    # Event hooks (Phase 4: extensible analytics callbacks)
    event_hooks: list[Any] = field(default_factory=list)

    # Metadata (extensible key-value pairs for hooks and logging)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionResult:
    """Result of a session run."""

    messages: list[BaseMessage] = field(default_factory=list)
    final_response: str = ""
    conversation_id: str = ""
    thread_id: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0


# =============================================================================
# Session Orchestrator
# =============================================================================


class SessionOrchestrator:
    """Orchestrates a complete agent session lifecycle.

    Implements battle-tested patterns from ml-infra's production runner:

    1. **Checkpoint health check** — pre-flight DB ping with graceful
       fallback to conversation history when Postgres is unreachable.
    2. **Smart message dedup** — only sends the new user message when
       a checkpoint exists (avoids duplicate history via add_messages).
    3. **Guaranteed finalization** — done event + stream close in
       ``finally`` block, even on errors.
    4. **Langfuse spans** — wraps each phase for observability.
    5. **MCP progress streaming** — streams tool progress to clients.
    6. **Swarm support** — multi-agent orchestration with handoffs.
    7. **Event hooks** — extensible callbacks for analytics/audit.
    8. **Context sync** — updates tool registry mid-run with new messages.
    9. **Safety guardrails** — PII redaction, prompt injection detection,
       output validation, token budgets, trace sanitization.
    """

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._tool_registry = tool_registry or ToolRegistry()

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    # =========================================================================
    # Public API
    # =========================================================================

    async def run_session(self, config: SessionConfig) -> SessionResult:
        """Run a complete agent session.

        Sets up the request context, loads tools, builds the agent/swarm,
        executes with streaming, and handles cleanup. The ``finally`` block
        always sends a ``done`` event and closes the stream.

        Safety middleware (PII redaction, guardrails, token budget) is
        auto-configured from ``SessionConfig`` flags and injected into the
        agent build pipeline.

        Args:
            config: Session configuration.

        Returns:
            SessionResult with response, messages, usage, and error info.
        """
        start_time = time.time()
        result = SessionResult(conversation_id=config.conversation_id)

        self._install_trace_sanitizer()
        self._register_safety_hooks(config)

        with request_context(
            tenant_id=config.tenant_id,
            project_id=config.project_id,
            principal_id=config.principal_id,
            conversation_id=config.conversation_id,
            stream_writer=config.stream_writer,
            request_id=config.request_id or str(uuid.uuid4()),
            agent_name=config.agent_name,
            model_name=config.model,
        ):
            try:
                await self._fire_hooks("on_session_start", config, {
                    "model": config.model,
                    "mode": config.mode,
                    "streaming": config.streaming,
                })

                result = await self._execute_session(config)

                await self._fire_hooks("on_session_complete", config, result, {
                    "duration_ms": result.duration_ms,
                    "usage": result.usage,
                })

            except Exception as e:
                logger.exception("Session failed: %s", e)
                result.error = str(e)

                await self._fire_hooks("on_session_error", config, e, {
                    "error_type": type(e).__name__,
                })

                if config.stream_writer:
                    try:
                        await config.stream_writer.write_event(
                            "error", {"error": str(e)}
                        )
                    except Exception:
                        logger.debug("Failed to write error event to stream")

            finally:
                result.duration_ms = int((time.time() - start_time) * 1000)

                if config.stream_writer:
                    try:
                        await config.stream_writer.write_event("done", {
                            "conversation_id": config.conversation_id,
                            "thread_id": result.thread_id,
                            "token_usage": result.usage,
                            "duration_ms": result.duration_ms,
                        })
                    except Exception:
                        logger.debug("Failed to write done event")
                    try:
                        await config.stream_writer.close()
                    except Exception:
                        logger.debug("Failed to close stream writer")

        return result

    # =========================================================================
    # Core execution pipeline
    # =========================================================================

    async def _execute_session(self, config: SessionConfig) -> SessionResult:
        """Execute the session pipeline.

        Steps:
          1. Resolve checkpointer with health check
          2. Load tools (registry + MCP + code exec)
          3. Build agent or swarm
          4. Determine input messages (checkpoint-aware dedup)
          5. Run with streaming and context sync
          6. Collect results and usage

        Each phase is wrapped in a Langfuse span for observability.
        """
        from cortex.orchestration.session.checkpointer import (
            build_thread_id,
            has_existing_checkpoint,
        )
        from cortex.orchestration.streaming import StreamHandler
        from cortex.orchestration.usage_tracking import ModelUsageTracker

        # ----- Phase 1: Checkpointer with health check -----
        checkpointer = await self._with_langfuse_span(
            "resolve_checkpointer",
            self._resolve_checkpointer(),
            input_data={"conversation_id": config.conversation_id},
        )

        # ----- Phase 2: Load tools -----
        tools = await self._with_langfuse_span(
            "load_tools",
            self._load_tools(config),
            input_data={"use_mcp": config.use_mcp, "tool_count": len(config.extra_tools)},
        )

        # ----- Phase 3: Build agent/swarm -----
        thread_id = config.thread_id or build_thread_id(
            config.agent_name,
            config.conversation_id or str(uuid.uuid4()),
        )

        if config.use_swarm and config.swarm_agents:
            compiled = await self._with_langfuse_span(
                "build_swarm",
                self._build_swarm(config, tools, checkpointer),
                input_data={"agent_count": len(config.swarm_agents)},
            )
        else:
            compiled = self._build_single_agent(config, tools, checkpointer)

        # ----- Phase 4: Message dedup (checkpoint-aware) -----
        user_text = self._build_user_message(config)
        user_message = HumanMessage(content=user_text)
        checkpoint_exists = await has_existing_checkpoint(thread_id)

        if config.stream_writer:
            try:
                await config.stream_writer.write_event(
                    "typing_indicator", {"status": "thinking"}
                )
            except Exception:
                pass

        if checkpointer is not None and checkpoint_exists:
            input_messages: list[BaseMessage] = [user_message]
        else:
            history_messages = self._convert_history(config.conversation_history)
            input_messages = history_messages + [user_message]

        logger.info(
            "Starting session",
            extra={
                "conversation_id": config.conversation_id,
                "message_count": len(input_messages),
                "checkpoint": "on" if checkpointer else "off",
                "checkpoint_exists": checkpoint_exists,
                "mode": config.mode,
            },
        )

        # ----- Phase 5: Execute with streaming (Langfuse-wrapped) -----
        run_config = {"configurable": {"thread_id": thread_id}}

        usage_tracker = ModelUsageTracker()
        monitor = self._create_monitor(config, thread_id)

        stream_handler: StreamHandler | None = None
        if config.streaming and config.stream_writer:
            stream_handler = StreamHandler(
                stream_writer=config.stream_writer,
                agent_name=config.agent_name,
                enable_part_streaming=config.enable_part_streaming,
                enable_full_message_streaming=config.enable_full_message_streaming,
                mode=config.mode.upper(),
            )

        current_agent = config.agent_name
        conversation_context = list(config.conversation_history)

        execution_span = self._start_langfuse_span(
            "run_agent",
            input_data={
                "model": config.model,
                "mode": config.mode,
                "message_count": len(input_messages),
                "thread_id": thread_id,
            },
        )

        try:
            async for event in compiled.astream_events(
                {"messages": input_messages},
                config=run_config,
                version="v2",
            ):
                event_type = event.get("event", "")

                if (
                    config.enable_full_message_streaming
                    and event_type == "on_chat_model_stream"
                ):
                    continue

                # Track agent handoffs in swarm mode
                if event_type == "on_tool_end":
                    tool_name = event.get("name", "")
                    if tool_name.startswith("transfer_to_"):
                        current_agent = tool_name[len("transfer_to_"):]

                    if tool_name in ("search_project_documents",) and config.stream_writer:
                        await self._emit_citations(event, config.stream_writer)

                self._sync_context(event, conversation_context, self._tool_registry)

                usage_tracker.record_from_event(event)

                if stream_handler:
                    await stream_handler.handle_event(
                        event, source_agent=current_agent
                    )
                if monitor:
                    monitor.record_event(event, source_agent=current_agent)

        finally:
            self._end_langfuse_span(execution_span, output_data={"success": True})
            if monitor:
                try:
                    monitor.flush()
                except Exception:
                    logger.debug("Failed to flush swarm monitor")

        if stream_handler:
            await stream_handler.close_active_part()

        # ----- Phase 6: Collect results (Langfuse-wrapped) -----
        usage_data = usage_tracker.get_usage()
        if usage_data and config.stream_writer:
            await config.stream_writer.write_event("model_usage", usage_data)

        collect_span = self._start_langfuse_span(
            "collect_results",
            input_data={"thread_id": thread_id},
        )
        all_messages = await self._get_history(compiled, run_config)
        final_response = self._extract_response(all_messages)
        self._end_langfuse_span(collect_span, output_data={
            "message_count": len(all_messages),
            "response_length": len(final_response),
            "usage": usage_data,
        })

        return SessionResult(
            messages=all_messages,
            final_response=final_response,
            conversation_id=config.conversation_id,
            thread_id=thread_id,
            usage=usage_data,
        )

    # =========================================================================
    # Phase 1: Checkpointer
    # =========================================================================

    @staticmethod
    async def _resolve_checkpointer() -> Any:
        """Resolve checkpointer with pre-flight health check.

        Returns None (graceful fallback) when the checkpoint database is
        unreachable.
        """
        from cortex.orchestration.session.checkpointer import (
            get_checkpointer,
            is_checkpointer_healthy,
        )

        checkpointer = get_checkpointer()
        if checkpointer is None:
            return None

        if not await is_checkpointer_healthy():
            logger.error(
                "Checkpoint DB unreachable — falling back to conversation history"
            )
            return None

        return checkpointer

    # =========================================================================
    # Phase 2: Tool loading
    # =========================================================================

    async def _load_tools(self, config: SessionConfig) -> list[Any]:
        """Collect all tools for the session."""
        tools: list[Any] = []

        if config.use_tools:
            self._tool_registry.set_context(
                tenant_id=config.tenant_id,
                project_id=config.project_id,
                principal_id=config.principal_id,
            )
            tools.extend(self._tool_registry.all())

        tools.extend(config.extra_tools)

        if config.use_code_execution:
            try:
                from cortex.tools.code_executor import create_code_execution_tool
                tools.append(create_code_execution_tool())
            except ImportError:
                logger.warning("Code execution tool unavailable (missing e2b)")

        if config.use_mcp and config.mcp_config:
            mcp_tools = await self._load_mcp_tools(config)
            tools.extend(mcp_tools)

        logger.info("Tools loaded: %d", len(tools))
        return tools

    async def _load_mcp_tools(self, config: SessionConfig) -> list[Any]:
        """Load tools from MCP server with progress streaming."""
        try:
            from cortex.orchestration.mcp.registry import mcp_server_registry
        except ImportError:
            logger.warning("MCP packages not installed")
            return []

        try:
            progress_callback = None
            if config.stream_writer:
                async def progress_callback(params: Any) -> None:
                    await _handle_mcp_progress(
                        params=params,
                        stream_writer=config.stream_writer,
                        mode=config.mode,
                    )

            loader = mcp_server_registry.create_loader(
                config.mcp_config,
                progress_callback=progress_callback,
            )

            async with loader:
                mcp_tools = await loader.load_tools()
                logger.info("Loaded %d MCP tools", len(mcp_tools))
                return list(mcp_tools)

        except Exception:
            logger.warning(
                "Failed to load MCP tools from %s", config.mcp_config, exc_info=True,
            )
            return []

    # =========================================================================
    # Phase 3: Agent / Swarm building
    # =========================================================================

    def _build_single_agent(
        self,
        config: SessionConfig,
        tools: list[Any],
        checkpointer: Any,
    ) -> Any:
        """Build a single agent with configured middleware + safety stack."""
        from langgraph.checkpoint.memory import MemorySaver

        from cortex.orchestration.builder import build_agent
        from cortex.orchestration.config import AgentConfig, ModelConfig

        middleware: list[Any] = []

        # --- Safety middleware (runs first, in order) ---
        safety_mw = self._build_safety_middleware(config)
        middleware.extend(safety_mw)

        if config.use_prompt_caching:
            try:
                from cortex.orchestration.caching.factory import (
                    CachingStrategyFactory,
                )
                strategy = CachingStrategyFactory.create_strategy(
                    provider=None, model=config.model
                )
                if strategy:
                    middleware.append(strategy)
            except Exception:
                logger.warning("Failed to create caching strategy", exc_info=True)

        if config.use_summarization and config.summarization_strategy:
            try:
                from cortex.orchestration.middleware.summarization import (
                    create_summarization_middleware,
                )
                mw = create_summarization_middleware(
                    strategy=config.summarization_strategy,
                )
                middleware.insert(0, mw)
            except Exception:
                logger.warning("Failed to create summarization middleware", exc_info=True)

        if config.use_skills:
            try:
                from cortex.orchestration.skills.middleware import (
                    SkillsMiddleware,
                )
                skills_mw = SkillsMiddleware(category=config.skills_module)
                middleware.append(skills_mw)
            except Exception:
                logger.warning("Failed to create skills middleware", exc_info=True)

        if config.use_semantic_memory:
            try:
                from cortex.orchestration.middleware.memory import MemoryMiddleware
                memory_mw = MemoryMiddleware()
                middleware.append(memory_mw)
            except Exception:
                logger.warning("Failed to create memory middleware", exc_info=True)

        agent_config = AgentConfig(
            name=config.agent_name,
            model=ModelConfig(
                model=config.model,
                temperature=config.temperature,
            ),
            system_prompt=config.system_prompt,
            tools=tools if tools else None,
            middleware=middleware if middleware else [],
            checkpointer=checkpointer or MemorySaver(),
            mode=config.mode,
        )

        return build_agent(agent_config, tool_registry=self._tool_registry)

    async def _build_swarm(
        self,
        config: SessionConfig,
        tools: list[Any],
        checkpointer: Any,
    ) -> Any:
        """Build a multi-agent swarm with handoff tools."""
        from cortex.orchestration.config import ModelConfig
        from cortex.orchestration.swarm import Swarm

        swarm = Swarm(
            model=ModelConfig(
                model=config.model,
                temperature=config.temperature,
            ),
            tool_registry=self._tool_registry,
            use_filesystem=config.use_filesystem,
        )

        for agent_config in config.swarm_agents:
            swarm.add(agent_config)

        return swarm.compile(checkpointer=checkpointer)

    # =========================================================================
    # Context sync (mid-execution)
    # =========================================================================

    @staticmethod
    def _sync_context(
        event: dict,
        conversation_history: list[dict],
        tool_registry: ToolRegistry,
    ) -> None:
        """Keep tool registry's conversation context in sync.

        Appends assistant responses to the history list and pushes the
        update into the tool registry so downstream tools that depend
        on conversation_raw see recent messages.
        """
        if event.get("event") != "on_chat_model_end":
            return

        output = event.get("data", {}).get("output")
        if output and hasattr(output, "content"):
            content = output.content
            if isinstance(content, str) and content:
                conversation_history.append({
                    "role": "assistant",
                    "content": content,
                })
                tool_registry.update_context({
                    "conversation_raw": conversation_history,
                })

    # =========================================================================
    # Langfuse observability (Phase 2)
    # =========================================================================

    @staticmethod
    async def _with_langfuse_span(
        name: str,
        coro: Any,
        input_data: dict | None = None,
    ) -> Any:
        """Wrap an awaitable in a Langfuse span if available.

        Falls through to plain ``await`` when Langfuse is not configured.
        """
        try:
            from langfuse import get_client

            langfuse = get_client()
            if langfuse is None:
                return await coro

            span = langfuse.span(name=name, input=input_data)
            try:
                result = await coro
                span.end(output={"success": True})
                return result
            except Exception as e:
                span.end(output={"error": str(e)})
                raise
        except ImportError:
            return await coro
        except Exception:
            logger.debug("Langfuse span '%s' failed, continuing without", name)
            return await coro

    @staticmethod
    def _start_langfuse_span(
        name: str,
        input_data: dict | None = None,
    ) -> Any:
        """Start a Langfuse span for long-running phases (e.g. streaming).

        Returns the span object, or None if Langfuse is unavailable.
        Call ``_end_langfuse_span`` when the phase completes.
        """
        try:
            from langfuse import get_client

            langfuse = get_client()
            if langfuse is None:
                return None
            return langfuse.span(name=name, input=input_data)
        except ImportError:
            return None
        except Exception:
            logger.debug("Failed to start Langfuse span '%s'", name)
            return None

    @staticmethod
    def _end_langfuse_span(
        span: Any,
        output_data: dict | None = None,
    ) -> None:
        """End a previously started Langfuse span."""
        if span is None:
            return
        try:
            span.end(output=output_data or {})
        except Exception:
            logger.debug("Failed to end Langfuse span")

    # =========================================================================
    # Monitor
    # =========================================================================

    @staticmethod
    def _create_monitor(config: SessionConfig, thread_id: str) -> Any:
        """Create a SwarmMonitor if debug monitoring is enabled."""
        enabled = config.debug_monitor or os.getenv(
            "ENABLE_SWARM_MONITOR", "false"
        ).lower() == "true"

        if not enabled:
            return None

        try:
            from cortex.orchestration.observability.monitor import SwarmMonitor
            return SwarmMonitor(conversation_id=thread_id)
        except Exception:
            logger.debug("Failed to create SwarmMonitor")
            return None

    # =========================================================================
    # Event hooks (Phase 4)
    # =========================================================================

    @staticmethod
    async def _fire_hooks(method_name: str, config: SessionConfig, *args: Any) -> None:
        """Fire a lifecycle hook on all registered event hooks.

        Errors are logged and swallowed — hooks must not break the session.
        """
        for hook in config.event_hooks:
            handler = getattr(hook, method_name, None)
            if handler is None:
                continue
            try:
                await handler(config, *args)
            except Exception:
                logger.debug(
                    "Event hook %s.%s failed",
                    type(hook).__name__,
                    method_name,
                    exc_info=True,
                )

    # =========================================================================
    # Safety & Guardrails
    # =========================================================================

    _trace_sanitizer_installed = False

    @classmethod
    def _install_trace_sanitizer(cls) -> None:
        """Install the Langfuse trace sanitizer (once per process)."""
        if cls._trace_sanitizer_installed:
            return
        cls._trace_sanitizer_installed = True
        try:
            from cortex.orchestration.safety.trace_sanitizer import (
                install_langfuse_sanitizer,
            )
            install_langfuse_sanitizer()
        except Exception:
            logger.debug("Trace sanitizer not installed", exc_info=True)

    @staticmethod
    def _register_safety_hooks(config: SessionConfig) -> None:
        """Auto-register safety event hooks from config flags."""
        if config.enable_feedback:
            from cortex.orchestration.safety.feedback import (
                FeedbackCollectionHook,
            )
            config.event_hooks.append(
                FeedbackCollectionHook(reasons=config.feedback_reasons)
            )

        if config.enable_history_dump:
            from cortex.orchestration.safety.history_dump import HistoryDumpHook
            config.event_hooks.append(HistoryDumpHook())

    @staticmethod
    def _build_safety_middleware(config: SessionConfig) -> list[Any]:
        """Build the safety middleware stack from config flags.

        Returns middleware in execution order:
          1. Input guardrails (reject bad input early)
          2. PII redaction (sanitize before LLM sees it)
          3. Token budget (enforce cost limits)
          4. Output guardrails (validate LLM response)
        """
        middleware: list[Any] = []

        if config.enable_input_guardrails:
            from cortex.orchestration.safety.input_guardrails import (
                InputGuardrailsMiddleware,
            )
            middleware.append(
                InputGuardrailsMiddleware(
                    on_violation=config.guardrail_action,
                )
            )

        if config.enable_pii_redaction:
            from cortex.orchestration.safety.pii_redaction import (
                PIIRedactionMiddleware,
            )
            middleware.append(
                PIIRedactionMiddleware(
                    entity_types=config.pii_entity_types,
                )
            )

        if config.max_total_tokens > 0 or config.max_completion_tokens > 0:
            from cortex.orchestration.safety.token_budget import (
                TokenBudgetMiddleware,
            )
            middleware.append(
                TokenBudgetMiddleware(
                    max_total_tokens=config.max_total_tokens,
                    max_completion_tokens=config.max_completion_tokens,
                )
            )

        if config.enable_output_guardrails:
            from cortex.orchestration.safety.output_guardrails import (
                OutputGuardrailsMiddleware,
            )
            middleware.append(
                OutputGuardrailsMiddleware(
                    system_prompt_fingerprints=config.system_prompt_fingerprints,
                    on_violation=config.guardrail_action,
                )
            )

        if middleware:
            names = [type(m).__name__ for m in middleware]
            logger.info("Safety middleware: %s", ", ".join(names))

        return middleware

    # =========================================================================
    # Message construction
    # =========================================================================

    @staticmethod
    def _build_user_message(config: SessionConfig) -> str:
        """Build the user message text, including attachments and system events.

        If a ``system_event`` is set (frontend continuation), it replaces
        the raw user message with a synthesized follow-up query.
        Attachments are appended as a formatted section.
        """
        if config.system_event:
            try:
                from cortex.orchestration.ui_actions.continuation_detector import (
                    build_system_event_query,
                )
                return build_system_event_query(
                    config.system_event,
                    [
                        {"role": e.get("role", ""), "content": e.get("content", "")}
                        for e in config.conversation_history[-5:]
                    ],
                )
            except ImportError:
                pass

        text = config.message

        if config.attachments:
            parts = ["\n\n---\n**Attached Files:**\n"]
            for att in config.attachments:
                name = att.get("name", "file")
                content = att.get("content", "")
                mime = att.get("mime_type", "")
                if content:
                    parts.append(f"\n**{name}** ({mime}):\n```\n{content[:10000]}\n```")
                else:
                    parts.append(f"\n- {name} ({mime})")
            text += "".join(parts)

        return text

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _convert_history(conversation_raw: list[dict]) -> list[BaseMessage]:
        """Convert raw conversation dicts to LangChain messages."""
        messages: list[BaseMessage] = []
        for entry in conversation_raw:
            role = entry.get("role", "")
            content = entry.get("content", "")
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        return messages

    @staticmethod
    async def _get_history(compiled: Any, config: dict) -> list[BaseMessage]:
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

    @staticmethod
    async def _emit_citations(event: dict, stream_writer: Any) -> None:
        """Parse document search results and emit structured citation events."""
        import re

        output = event.get("data", {}).get("output", "")
        if not output or not isinstance(output, str):
            return

        chunks = re.findall(
            r"\[(\d+)\]\s*(.+?)(?:\n|$)", output
        )
        if not chunks:
            return

        citations = []
        for idx, text in chunks[:10]:
            title_match = re.search(r"Source:\s*(.+)", text)
            citations.append({
                "index": int(idx),
                "text": text.strip()[:200],
                "source": title_match.group(1).strip() if title_match else None,
            })

        try:
            await stream_writer.write_event("citation", {"citations": citations})
        except Exception:
            logger.debug("Failed to emit citation event")
