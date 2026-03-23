"""
Session Orchestrator — single entry point for running an agent session.

Composes all building blocks (context, tools, MCP, skills, agent build,
streaming, usage tracking, persistence, cleanup) into a unified flow,
replacing ad-hoc wiring in route handlers.

Usage::

    from cortex.orchestration.session.orchestrator import SessionOrchestrator

    orchestrator = SessionOrchestrator()
    result = await orchestrator.run_session(SessionConfig(
        model="claude-sonnet-4-20250514",
        system_prompt="You are a helpful assistant.",
        messages=[HumanMessage(content="Hello")],
        tenant_id="acc_123",
        project_id="prj_456",
        principal_id="usr_789",
        conversation_id="conv_abc",
        stream_writer=writer,
    ))
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.messages import BaseMessage

from cortex.orchestration.context import request_context
from cortex.orchestration.tools import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """Configuration for a single session run."""

    model: str = "gpt-4o"
    system_prompt: str = ""
    messages: list[BaseMessage] = field(default_factory=list)

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

    # Features
    use_tools: bool = True
    extra_tools: list[Any] = field(default_factory=list)
    use_mcp: bool = False
    mcp_config: Optional[str] = None
    use_skills: bool = False
    skills_category: Optional[str] = None
    use_summarization: bool = False
    use_filesystem: bool = False
    use_code_execution: bool = False
    use_prompt_caching: bool = False

    # Agent overrides
    max_iterations: int = 25
    temperature: float = 0.0
    thread_id: Optional[str] = None

    # Metadata
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


class SessionOrchestrator:
    """Orchestrates a complete agent session lifecycle.

    Steps:
      1. setup_context — set request-scoped vars
      2. load_tools — register tools from registry + MCP + skills + code exec
      3. build_agent — create Agent with middleware
      4. stream / invoke — run the agent
      5. collect result — gather response and usage
      6. cleanup — release resources
    """

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry()

    async def run_session(self, config: SessionConfig) -> SessionResult:
        """Run a complete agent session."""
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
                tools = await self._load_tools(config)
                agent = self._build_agent(config, tools)
                result = await self._execute(agent, config)
                return result
            except Exception as e:
                logger.exception("Session failed: %s", e)
                return SessionResult(error=str(e))

    async def _load_tools(self, config: SessionConfig) -> list[Any]:
        """Collect all tools for the session."""
        tools: list[Any] = []

        if config.use_tools:
            self._tool_registry.set_context(
                tenant_id=config.tenant_id,
                project_id=config.project_id,
            )
            tools.extend(self._tool_registry.all())

        tools.extend(config.extra_tools)

        if config.use_code_execution:
            from cortex.tools.code_executor import create_code_execution_tool
            tools.append(create_code_execution_tool())

        if config.use_mcp and config.mcp_config:
            try:
                from cortex.orchestration.mcp.registry import mcp_server_registry
                loader = mcp_server_registry.create_loader(config.mcp_config)
                async with loader:
                    mcp_tools = await loader.load_tools()
                    tools.extend(mcp_tools)
            except Exception:
                logger.warning("Failed to load MCP tools from %s", config.mcp_config, exc_info=True)

        return tools

    def _build_skill_files(self, config: SessionConfig) -> dict[str, Any]:
        """Build skill files for filesystem injection when skills are enabled."""
        if not config.use_skills:
            return {}
        try:
            from cortex.orchestration.skills.loader import build_skill_files
            return build_skill_files(category=config.skills_category)
        except Exception:
            logger.warning("Failed to build skill files", exc_info=True)
            return {}

    def _build_agent(self, config: SessionConfig, tools: list[Any]) -> Any:
        """Build the agent with configured middleware."""
        from cortex.orchestration import Agent, ModelConfig

        agent = Agent(
            name=config.agent_name,
            model=ModelConfig(model=config.model, temperature=config.temperature),
            system_prompt=config.system_prompt,
            tools=tools,
            max_iterations=config.max_iterations,
        )

        if config.use_skills:
            try:
                from cortex.orchestration.skills.middleware import SkillsMiddleware
                skills_mw = SkillsMiddleware(category=config.skills_category)
                skill_context = skills_mw.get_skill_context("")
                if skill_context and config.system_prompt:
                    agent.system_prompt = config.system_prompt + "\n\n" + skill_context
                elif skill_context:
                    agent.system_prompt = skill_context
            except Exception:
                logger.warning("Failed to add skills middleware", exc_info=True)

        if config.use_filesystem:
            try:
                from cortex.orchestration.filesystem.middleware import FilesystemMiddleware
                agent.add_middleware(FilesystemMiddleware())
            except Exception:
                logger.warning("Failed to add filesystem middleware", exc_info=True)

        if config.use_summarization:
            try:
                from cortex.orchestration.middleware import create_summarization_middleware
                agent.add_middleware(create_summarization_middleware())
            except Exception:
                logger.warning("Failed to add summarization middleware", exc_info=True)

        if config.use_prompt_caching:
            try:
                from cortex.orchestration.caching import AnthropicCachingStrategy
                agent.add_middleware(AnthropicCachingStrategy())
            except Exception:
                logger.warning("Failed to add prompt caching middleware", exc_info=True)

        return agent

    async def _execute(self, agent: Any, config: SessionConfig) -> SessionResult:
        """Run the agent and collect results."""
        thread_id = config.thread_id or str(uuid.uuid4())

        if config.streaming and config.stream_writer:
            result = await agent.stream_to_writer(
                messages=config.messages,
                writer=config.stream_writer,
                thread_id=thread_id,
            )
        else:
            result = await agent.run(
                messages=config.messages,
                thread_id=thread_id,
            )

        final_response = ""
        result_messages: list[BaseMessage] = []

        if hasattr(result, "messages"):
            result_messages = result.messages
            if result_messages:
                last = result_messages[-1]
                if hasattr(last, "content"):
                    final_response = str(last.content)
        elif hasattr(result, "content"):
            final_response = str(result.content)

        usage = {}
        if hasattr(result, "usage"):
            usage = result.usage if isinstance(result.usage, dict) else {}

        return SessionResult(
            messages=result_messages,
            final_response=final_response,
            conversation_id=config.conversation_id,
            thread_id=thread_id,
            usage=usage,
        )
