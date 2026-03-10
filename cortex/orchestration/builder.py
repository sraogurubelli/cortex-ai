"""
Agent Builder

Build standalone LangChain agents from AgentConfig.
"""

import logging

from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from cortex.orchestration.config import AgentConfig
from cortex.orchestration.llm import LLMClient
from cortex.orchestration.tools import ToolRegistry

logger = logging.getLogger(__name__)


def build_agent(
    config: AgentConfig,
    tool_registry: ToolRegistry | None = None,
) -> CompiledStateGraph:
    """
    Build a standalone agent from config.

    Note: `can_handoff_to` is ignored for standalone agents. Handoff tools
    are only injected when using Swarm for multi-agent orchestration.

    Args:
        config: Agent configuration
        tool_registry: Optional tool registry for resolving tool names.
                      Defaults to ToolRegistry.with_defaults() (empty by default).
                      Pass a configured registry with registered tools.
                      If config.tools is None, uses all tools from registry.

    Returns:
        Compiled LangGraph agent

    Example:
        # With specific tools
        config = AgentConfig(
            name="assistant",
            model=ModelConfig(model="gpt-4o", use_gateway=False),
            tools=[calculator_tool, search_tool],
        )
        agent = build_agent(config)

        # With tool registry
        registry = ToolRegistry()
        registry.register(calculator_tool)
        registry.register(search_tool)
        config = AgentConfig(name="assistant", tools=None)  # Use all from registry
        agent = build_agent(config, tool_registry=registry)
    """
    if tool_registry is None:
        tool_registry = ToolRegistry.with_defaults()

    # Get model using LLMClient
    client = LLMClient(config.model)
    model = client.get_model()

    # Resolve tools
    # If tools=None, use all tools from registry (wrapped with context)
    if config.tools is None:
        tools = tool_registry.all_wrapped()
    else:
        tools = []
        for tool in config.tools:
            if isinstance(tool, str):
                try:
                    resolved = tool_registry.get(tool)
                    tools.append(tool_registry.wrap_with_context(resolved))
                except KeyError:
                    raise ValueError(
                        f"Tool '{tool}' not found. Available: {tool_registry.list_names()}"
                    )
            else:
                # Wrap directly provided tools with context
                if isinstance(tool, BaseTool):
                    tools.append(tool_registry.wrap_with_context(tool))
                else:
                    tools.append(tool)

    # Build system prompt
    prompt = config.system_prompt or f"You are {config.name}. {config.description}"

    # Build kwargs for create_agent (only pass non-default advanced options)
    agent_kwargs: dict = {}
    if config.middleware:
        agent_kwargs["middleware"] = config.middleware
    if config.checkpointer is not None:
        agent_kwargs["checkpointer"] = config.checkpointer

    # Create agent
    return create_agent(
        model,
        tools=tools,
        system_prompt=prompt,
        name=config.name,
        **agent_kwargs,
    )
