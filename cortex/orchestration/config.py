"""
Orchestration Configuration

Configuration types for agents and models.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Sequence

from langchain_core.tools import BaseTool


# =========================================================================
# Model Configuration
# =========================================================================


def _get_default_gateway_url() -> str | None:
    """Build gateway URL from environment variables.

    Uses LLM_GATEWAY_HTTP_PORT (default 50057) for the OpenAI-compatible HTTP
    endpoint. This is separate from LLM_GATEWAY_PORT (gRPC, default 50055)
    used by the legacy autogen path.

    Returns the URL with /v1 path suffix because the OpenAI Python client
    appends /chat/completions to the base_url, so the full request path
    becomes /v1/chat/completions.
    """
    host = os.environ.get("LLM_GATEWAY_HOST")
    port = os.environ.get("LLM_GATEWAY_HTTP_PORT", "50057")
    if host:
        return f"http://{host}:{port}/v1"
    return None


# Provider inference patterns
PROVIDER_PATTERNS = {
    "openai": ["gpt-", "o1-", "o3-"],
    "anthropic": ["claude-"],
    "google": ["gemini-"],
}


def _infer_provider(model: str) -> str | None:
    """Infer provider from model name prefix."""
    model_lower = model.lower()
    for provider, prefixes in PROVIDER_PATTERNS.items():
        for prefix in prefixes:
            if model_lower.startswith(prefix):
                return provider
    return None


@dataclass
class ModelConfig:
    """
    Configuration for LLM models.

    Attributes:
        model: Model name (e.g., "gpt-4o", "claude-sonnet-4-20250514")
        provider: Provider name (e.g., "openai", "anthropic", "anthropic_vertex").
                  Inferred from model if not set.
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens in response
        use_gateway: Whether to route through LLM Gateway
        gateway_url: LLM Gateway URL (required if use_gateway=True)
        tenant_id: Tenant ID for gateway request tracking (typically account_id).
                   Falls back to LLM_GATEWAY_TENANT_ID env var.
        source: Source identifier for gateway (e.g., "unified-agent").
        product: Product identifier for gateway (e.g., "ci", "cd").
        project: GCP project ID (for anthropic_vertex provider).
                 Falls back to ANTHROPIC_VERTEX_GCP_PROJECT_ID env var.
        location: GCP region (for anthropic_vertex provider).
                  Falls back to ANTHROPIC_VERTEX_GCP_REGION env var.
        caching_strategy: Optional caching strategy for prompt caching.
                          Example: AnthropicCachingStrategy() for Anthropic models.
    """

    model: str = "gpt-4o"
    provider: str | None = field(default=None)
    temperature: float = 0.7
    max_tokens: int | None = None
    use_gateway: bool = False  # Default to False for open source (no gateway)
    gateway_url: str | None = field(default=None)
    tenant_id: str | None = field(default=None)
    source: str | None = field(default=None)
    product: str | None = field(default=None)
    project: str | None = field(default=None)
    location: str | None = field(default=None)
    caching_strategy: Any | None = field(default=None)

    def __post_init__(self):
        # Validate temperature
        if not (0 <= self.temperature <= 1):
            raise ValueError(
                f"temperature must be between 0 and 1, got {self.temperature}"
            )

        # Infer provider if not explicitly set
        if self.provider is None:
            self.provider = _infer_provider(self.model)

        # Set gateway defaults from environment if not provided
        if self.use_gateway:
            if self.gateway_url is None:
                self.gateway_url = _get_default_gateway_url()
            if self.tenant_id is None:
                self.tenant_id = os.environ.get("LLM_GATEWAY_TENANT_ID")

        # Set Vertex AI defaults from environment if not provided
        if self.provider == "anthropic_vertex":
            if self.project is None:
                self.project = os.environ.get("ANTHROPIC_VERTEX_GCP_PROJECT_ID")
            if self.location is None:
                self.location = os.environ.get("ANTHROPIC_VERTEX_GCP_REGION")


# =========================================================================
# Agent Configuration
# =========================================================================


@dataclass
class AgentConfig:
    """
    Configuration for an agent.

    Works for both standalone agents and agents in a swarm.

    Example (standalone - direct provider):
        config = AgentConfig(
            name="assistant",
            model=ModelConfig(model="gpt-4o", use_gateway=False),
            system_prompt="You are helpful...",
            tools=[search_tool],
        )
        agent = build_agent(config)

    Example (with gateway):
        config = AgentConfig(
            name="assistant",
            model=ModelConfig(
                model="gpt-4o",
                use_gateway=True,
                gateway_url="http://llm-gateway:50057/v1",
            ),
        )
        agent = build_agent(config)

    Example (swarm):
        config = AgentConfig(
            name="unified",
            description="General assistant",
            can_handoff_to=["architect"],
        )
        swarm.add(config)
    """

    # Identity
    name: str
    description: str = ""

    # Model configuration (includes gateway settings)
    model: ModelConfig = field(default_factory=ModelConfig)

    # Prompt
    system_prompt: str = ""

    # Tools - can be tool objects or names (resolved by registry)
    # If None, defaults to all tools from the registry
    tools: list[BaseTool | Callable | str] | None = None

    # Swarm handoffs (only used when in a swarm)
    can_handoff_to: list[str] = field(default_factory=list)

    # Chat mode - affects streaming behavior (thought vs detailed_analysis)
    mode: Literal["standard", "architect"] = "standard"

    # Additional context for system prompt augmentation
    additional_context: dict[str, Any] = field(default_factory=dict)

    # Set of event categories to suppress from SSE output.
    # Uses StreamHandler category constants: TOKENS, ASSISTANT_MESSAGE,
    # TOOL_REQUEST, TOOL_RESULT, THOUGHT.  Events are still processed
    # for usage tracking and context sync — only the SSE output is muted.
    # Example: suppress_events={"assistant_message", "tool_request", "tool_result"}
    suppress_events: set[str] = field(default_factory=set)

    # Advanced agent options (optional, passed through to create_agent)
    # AgentMiddleware instances for tool call wrapping, model hooks, etc.
    middleware: Sequence[Any] = field(default_factory=list)
    # Optional checkpointer for state persistence (e.g. MemorySaver)
    checkpointer: Any = None
