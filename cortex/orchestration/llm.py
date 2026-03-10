"""
LLM Client

Creates LangChain chat models with support for direct providers and optional LLM Gateway.
"""

from langchain_core.language_models import BaseChatModel

from cortex.orchestration.config import ModelConfig

# Lazy imports to avoid import errors when packages not installed
ChatOpenAI = None
ChatAnthropic = None
ChatGoogleGenerativeAI = None
ChatAnthropicVertex = None


def _ensure_openai():
    global ChatOpenAI
    if ChatOpenAI is None:
        from langchain_openai import ChatOpenAI as _ChatOpenAI

        ChatOpenAI = _ChatOpenAI
    return ChatOpenAI


def _ensure_anthropic():
    global ChatAnthropic
    if ChatAnthropic is None:
        from langchain_anthropic import ChatAnthropic as _ChatAnthropic

        ChatAnthropic = _ChatAnthropic
    return ChatAnthropic


def _ensure_google():
    global ChatGoogleGenerativeAI
    if ChatGoogleGenerativeAI is None:
        from langchain_google_genai import (
            ChatGoogleGenerativeAI as _ChatGoogleGenerativeAI,
        )

        ChatGoogleGenerativeAI = _ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI


def _ensure_anthropic_vertex():
    global ChatAnthropicVertex
    if ChatAnthropicVertex is None:
        from langchain_google_vertexai.model_garden import (
            ChatAnthropicVertex as _ChatAnthropicVertex,
        )

        ChatAnthropicVertex = _ChatAnthropicVertex
    return ChatAnthropicVertex


class LLMClient:
    """
    LLM Client for creating LangChain chat models.

    Supports:
    - Direct providers: OpenAI, Anthropic, Anthropic (Vertex AI), Google
    - LLM Gateway: Routes through centralized gateway (optional)

    Example (direct provider):
        client = LLMClient(ModelConfig(model="gpt-4o", use_gateway=False))
        model = client.get_model()

    Example (with gateway):
        config = ModelConfig(
            model="gpt-4o",
            use_gateway=True,
            gateway_url="http://llm-gateway:50057/v1"
        )
        client = LLMClient(config)
        model = client.get_model()

    Example (Anthropic via Vertex AI):
        config = ModelConfig(
            model="claude-sonnet-4@20250514",
            provider="anthropic_vertex",
            project="my-gcp-project",
            location="us-east5",
        )
        client = LLMClient(config)
        model = client.get_model()
    """

    def __init__(self, config: ModelConfig):
        """
        Initialize LLMClient.

        Args:
            config: ModelConfig object
        """
        self.config = config

    @property
    def gateway_model_name(self) -> str | None:
        """
        Get model name in gateway format.

        Returns:
            Model name formatted as 'online/{provider}/{model}' if gateway is enabled,
            None otherwise.
        """
        if not self.config.use_gateway:
            return None

        model = self.config.model

        # Already in gateway format
        if model.startswith("online/"):
            return model

        # Format as online/{provider}/{model}
        provider = self.config.provider or "anthropic"  # Default to anthropic
        # Map anthropic_vertex to anthropic for gateway routing
        if provider == "anthropic_vertex":
            provider = "anthropic"
        return f"online/{provider}/{model}"

    def get_model(self) -> BaseChatModel:
        """
        Create and return a LangChain chat model.

        Returns:
            Configured BaseChatModel instance.

        Raises:
            ValueError: If provider is unknown.
        """
        if self.config.use_gateway:
            return self._create_gateway_model()

        return self._create_direct_model()

    def _create_gateway_model(self) -> BaseChatModel:
        """Create model via LLM Gateway (OpenAI-compatible).

        Passes gateway metadata (tenant_id, source, product) as HTTP headers
        for request tracking and cost attribution. Uses api_key="not-needed"
        since the gateway handles auth.
        """
        ChatOpenAI = _ensure_openai()

        kwargs = {
            "model": self.gateway_model_name,
            "temperature": self.config.temperature,
            "api_key": "not-needed",
        }

        if self.config.gateway_url:
            kwargs["base_url"] = self.config.gateway_url

        if self.config.max_tokens is not None:
            kwargs["max_tokens"] = self.config.max_tokens

        # Build gateway headers for tracking/attribution
        headers = {}
        if self.config.tenant_id:
            headers["X-Tenant-Id"] = self.config.tenant_id
        if self.config.source:
            headers["X-Source"] = self.config.source
        if self.config.product:
            headers["X-Product"] = self.config.product

        if headers:
            kwargs["default_headers"] = headers

        return ChatOpenAI(**kwargs)

    def _create_direct_model(self) -> BaseChatModel:
        """Create model with direct provider access."""
        provider = self.config.provider

        if provider == "openai":
            return self._create_openai_model()
        elif provider == "anthropic":
            return self._create_anthropic_model()
        elif provider == "anthropic_vertex":
            return self._create_anthropic_vertex_model()
        elif provider == "google":
            return self._create_google_model()
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _create_openai_model(self) -> BaseChatModel:
        """Create OpenAI chat model."""
        ChatOpenAI = _ensure_openai()

        kwargs = {
            "model": self.config.model,
            "temperature": self.config.temperature,
        }

        if self.config.max_tokens is not None:
            kwargs["max_tokens"] = self.config.max_tokens

        return ChatOpenAI(**kwargs)

    def _create_anthropic_model(self) -> BaseChatModel:
        """Create Anthropic chat model."""
        ChatAnthropic = _ensure_anthropic()

        kwargs = {
            "model": self.config.model,
            "temperature": self.config.temperature,
        }

        if self.config.max_tokens is not None:
            kwargs["max_tokens"] = self.config.max_tokens

        # Enable prompt caching if strategy is provided and model supports it
        if self.config.caching_strategy:
            try:
                if self.config.caching_strategy.supports_caching(self.config.model):
                    # Anthropic supports caching via model_kwargs or extra_headers
                    # LangChain's ChatAnthropic handles cache_control in message content
                    cache_config = self.config.caching_strategy.get_cache_config()
                    if cache_config:
                        kwargs.update(cache_config)
            except Exception as e:
                # Log warning but don't fail model creation
                import logging

                logging.warning(f"Failed to configure prompt caching: {e}")

        return ChatAnthropic(**kwargs)

    def _create_anthropic_vertex_model(self) -> BaseChatModel:
        """Create Anthropic chat model via Google Vertex AI."""
        ChatAnthropicVertex = _ensure_anthropic_vertex()

        kwargs = {
            "model_name": self.config.model,
            "temperature": self.config.temperature,
        }

        if self.config.project:
            kwargs["project"] = self.config.project

        if self.config.location:
            kwargs["location"] = self.config.location

        if self.config.max_tokens is not None:
            kwargs["max_tokens"] = self.config.max_tokens

        return ChatAnthropicVertex(**kwargs)

    def _create_google_model(self) -> BaseChatModel:
        """Create Google chat model."""
        ChatGoogleGenerativeAI = _ensure_google()

        kwargs = {
            "model": self.config.model,
            "temperature": self.config.temperature,
        }

        if self.config.max_tokens is not None:
            kwargs["max_output_tokens"] = self.config.max_tokens

        return ChatGoogleGenerativeAI(**kwargs)
