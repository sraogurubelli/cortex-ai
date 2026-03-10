"""
Swarm Orchestrator

Multi-agent swarm with automatic handoff tool injection using langgraph-swarm.

Requires: pip install langgraph-swarm
"""

from typing import Any, Callable

from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph_swarm import create_handoff_tool, create_swarm

from cortex.orchestration.config import AgentConfig, ModelConfig
from cortex.orchestration.llm import LLMClient
from cortex.orchestration.tools import ToolRegistry

__all__ = [
    "Swarm",
    "AgentConfig",
    "create_handoff_tool",
]


class Swarm:
    """
    Multi-agent swarm orchestrator.

    Simple API for creating swarms with automatic handoff tool injection.
    By default uses an empty tool registry (pass tools explicitly or use
    a configured registry).

    Example (basic):
        swarm = Swarm(model="gpt-4o")

        swarm.add_agent(
            name="general",
            description="General assistant",
            system_prompt="You help with general questions",
            can_handoff_to=["specialist"],
        )

        swarm.add_agent(
            name="specialist",
            description="Expert in technical questions",
            system_prompt="You help with technical questions",
            can_handoff_to=["general"],
        )

        graph = swarm.compile()

    Example (with tools):
        swarm = Swarm(model="gpt-4o")

        swarm.add_agent(
            name="researcher",
            description="Research agent",
            tools=[search_tool, web_scraper],
            can_handoff_to=["writer"],
        )

        swarm.add_agent(
            name="writer",
            description="Writing agent",
            tools=[editor_tool],
            can_handoff_to=["researcher"],
        )

        graph = swarm.compile(checkpointer=memory)

    Example (with direct provider):
        swarm = Swarm(
            model=ModelConfig(model="gpt-4o", use_gateway=False)
        )
    """

    def __init__(
        self,
        model: str | ModelConfig = "gpt-4o",
        default_agent: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        """
        Initialize the swarm.

        Args:
            model: Default model for agents (string or ModelConfig)
            default_agent: Name of the default starting agent
            tool_registry: Optional tool registry. Defaults to empty registry.
                Pass ToolRegistry.with_defaults() for a pre-populated registry.
        """
        if isinstance(model, str):
            self._default_model = ModelConfig(model=model)
        else:
            self._default_model = model

        self._default_agent = default_agent
        self._agent_configs: dict[str, AgentConfig] = {}
        self._tool_registry = (
            tool_registry if tool_registry is not None else ToolRegistry()
        )

    # =========================================================================
    # Tool Registry
    # =========================================================================

    @property
    def tool_registry(self) -> ToolRegistry:
        """Get the tool registry for registration and context."""
        return self._tool_registry

    def _resolve_tools(
        self,
        tools: list[BaseTool | Callable | str],
        wrap_context: bool = True,
    ) -> list[BaseTool | Callable]:
        """
        Resolve tool names to tool objects.

        Args:
            tools: List of tools (BaseTool, Callable, or name strings)
            wrap_context: If True, wrap tools with context injection

        Returns:
            List of resolved (and optionally wrapped) tools
        """
        resolved = []
        for tool_item in tools:
            if isinstance(tool_item, str):
                try:
                    tool = self._tool_registry.get(tool_item)
                    if wrap_context and isinstance(tool, BaseTool):
                        tool = self._tool_registry.wrap_with_context(tool)
                    resolved.append(tool)
                except KeyError:
                    raise ValueError(
                        f"Tool '{tool_item}' not found. "
                        f"Available: {self._tool_registry.list_names()}"
                    )
            else:
                # Directly provided tool - wrap if requested
                if wrap_context and isinstance(tool_item, BaseTool):
                    resolved.append(self._tool_registry.wrap_with_context(tool_item))
                else:
                    resolved.append(tool_item)
        return resolved

    # =========================================================================
    # Agent Registration
    # =========================================================================

    def add_agent(
        self,
        name: str,
        description: str = "",
        tools: list[BaseTool | Callable | str] | None = None,
        system_prompt: str = "",
        can_handoff_to: list[str] | None = None,
        model: str | ModelConfig | None = None,
    ) -> "Swarm":
        """
        Add an agent to the swarm.

        Args:
            name: Unique name for the agent
            description: What this agent does (used in handoff tool descriptions)
            tools: Tools for this agent (objects or registry names).
                   If None, uses all tools from registry.
            system_prompt: System prompt for the agent
            can_handoff_to: Agent names this agent can hand off to
            model: Model override for this agent (string or ModelConfig)

        Returns:
            Self for chaining

        Example:
            swarm.add_agent(
                name="researcher",
                description="Research and gather information",
                tools=[search_tool, scraper_tool],
                system_prompt="You are a research assistant...",
                can_handoff_to=["writer", "analyst"],
            )
        """
        # Determine model config
        if model is None:
            agent_model = self._default_model
        elif isinstance(model, str):
            agent_model = ModelConfig(model=model)
        else:
            agent_model = model

        # Create AgentConfig
        # tools=None means "use all tools from registry"
        config = AgentConfig(
            name=name,
            description=description,
            model=agent_model,
            system_prompt=system_prompt,
            tools=tools,
            can_handoff_to=can_handoff_to or [],
        )

        self._agent_configs[name] = config

        # First agent becomes default
        if self._default_agent is None:
            self._default_agent = name

        return self

    def add(self, config: AgentConfig) -> "Swarm":
        """
        Add an agent using an AgentConfig.

        Args:
            config: Agent configuration

        Returns:
            Self for chaining

        Example:
            config = AgentConfig(
                name="assistant",
                description="General assistant",
                model=ModelConfig(model="gpt-4o"),
                tools=[tool1, tool2],
                can_handoff_to=["specialist"],
            )
            swarm.add(config)
        """
        self._agent_configs[config.name] = config

        if self._default_agent is None:
            self._default_agent = config.name

        return self

    # =========================================================================
    # Build
    # =========================================================================

    def _build_agents(self) -> list[CompiledStateGraph]:
        """Build all agents with handoff tools injected."""
        agents = []

        for name, config in self._agent_configs.items():
            # Create handoff tools for this agent
            handoff_tools = []
            for target in config.can_handoff_to:
                target_config = self._agent_configs.get(target)
                desc = (
                    f"Transfer to {target}: {target_config.description}"
                    if target_config
                    else f"Transfer to {target}"
                )
                handoff_tools.append(
                    create_handoff_tool(
                        agent_name=target,
                        description=desc,
                    )
                )

            # Resolve tools from registry
            # If tools=None, use all tools from registry (wrapped with context)
            if config.tools is None:
                resolved_tools = self._tool_registry.all_wrapped()
            else:
                resolved_tools = self._resolve_tools(config.tools)

            all_tools = resolved_tools + handoff_tools

            # Get model
            client = LLMClient(config.model)
            model = client.get_model()

            # Build system prompt
            prompt = config.system_prompt or f"You are {name}. {config.description}"

            # Build kwargs for create_agent
            agent_kwargs: dict[str, Any] = {}
            if config.middleware:
                agent_kwargs["middleware"] = config.middleware

            # Create agent
            # NOTE: checkpointer is intentionally NOT passed per-agent.
            # In a swarm the checkpointer belongs at the graph level
            # (swarm.compile(checkpointer=...)), not per-agent.
            agent = create_agent(
                model,
                tools=all_tools,
                system_prompt=prompt,
                name=name,
                **agent_kwargs,
            )

            agents.append(agent)

        return agents

    def compile(self, checkpointer: Any = None) -> CompiledStateGraph:
        """
        Compile the swarm.

        Args:
            checkpointer: Optional checkpointer for persistence.
                         Recommended to use PostgresSaver for multi-turn
                         conversations across requests.

        Returns:
            Compiled swarm graph

        Raises:
            ValueError: If no agents registered or handoff targets don't exist

        Example:
            from langgraph.checkpoint.memory import MemorySaver

            checkpointer = MemorySaver()
            graph = swarm.compile(checkpointer=checkpointer)

            # Run swarm
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="Hello")]},
                config={"configurable": {"thread_id": "session-1"}},
            )
        """
        if not self._agent_configs:
            raise ValueError("No agents registered")

        if self._default_agent is None:
            self._default_agent = next(iter(self._agent_configs))

        # Validate handoff targets exist
        for name, config in self._agent_configs.items():
            for target in config.can_handoff_to:
                if target not in self._agent_configs:
                    raise ValueError(
                        f"Agent '{name}' has handoff target '{target}' "
                        f"which does not exist. Available agents: {list(self._agent_configs.keys())}"
                    )

        # Build all agents
        agents = self._build_agents()

        # Create swarm
        workflow = create_swarm(
            agents,
            default_active_agent=self._default_agent,
        )

        # Compile with optional checkpointer
        if checkpointer:
            return workflow.compile(checkpointer=checkpointer)
        else:
            return workflow.compile()
