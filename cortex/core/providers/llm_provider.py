"""
LLM Provider abstraction for Cortex-AI.

Supports multiple LLM providers:
- Anthropic (Claude)
- OpenAI (GPT)
- Google VertexAI (Gemini, Claude via Vertex)
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional, Union
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    VERTEX_AI = "vertex_ai"


class Message(dict):
    """Message format for LLM interactions."""

    def __init__(self, role: str, content: str, **kwargs):
        super().__init__(role=role, content=content, **kwargs)
        self.role = role
        self.content = content


class LLMResponse:
    """Response from LLM provider."""

    def __init__(
        self,
        content: str,
        model: str,
        usage: Optional[Dict[str, int]] = None,
        finish_reason: Optional[str] = None,
        **metadata
    ):
        self.content = content
        self.model = model
        self.usage = usage or {}
        self.finish_reason = finish_reason
        self.metadata = metadata


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_params = kwargs

    @abstractmethod
    async def create(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """Create a completion from messages."""
        pass

    @abstractmethod
    async def create_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Create a streaming completion from messages."""
        pass

    async def close(self):
        """Close client connections."""
        pass


class LLMProviderFactory:
    """Factory for creating LLM provider clients."""

    # Default models for each provider
    DEFAULT_MODELS = {
        LLMProvider.ANTHROPIC: "claude-sonnet-4",
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.VERTEX_AI: "gemini-2.0-flash-exp",
    }

    @classmethod
    def get_provider_from_model(cls, model: str) -> LLMProvider:
        """Infer provider from model name."""
        model_lower = model.lower()

        if model_lower.startswith(("claude", "opus", "sonnet", "haiku")):
            return LLMProvider.ANTHROPIC
        elif model_lower.startswith(("gpt", "o1", "o3")):
            return LLMProvider.OPENAI
        elif model_lower.startswith("gemini"):
            return LLMProvider.VERTEX_AI
        else:
            # Default to Anthropic
            logger.warning(
                f"Could not infer provider from model '{model}', defaulting to Anthropic"
            )
            return LLMProvider.ANTHROPIC

    @classmethod
    def get_default_model(cls, provider: Union[str, LLMProvider]) -> str:
        """Get default model for a provider."""
        if isinstance(provider, str):
            provider = LLMProvider(provider)
        return cls.DEFAULT_MODELS.get(provider, cls.DEFAULT_MODELS[LLMProvider.ANTHROPIC])

    @classmethod
    def create(
        cls,
        provider: Optional[Union[str, LLMProvider]] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ) -> BaseLLMClient:
        """
        Create an LLM client instance.

        Args:
            provider: Provider name (anthropic, openai, vertex_ai)
            model: Model name (if not provided, uses default for provider)
            api_key: API key for the provider
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Returns:
            BaseLLMClient instance for the specified provider
        """
        # Determine provider and model
        if not provider and not model:
            provider = LLMProvider.ANTHROPIC
            model = cls.DEFAULT_MODELS[provider]
        elif model and not provider:
            provider = cls.get_provider_from_model(model)
        elif provider and not model:
            if isinstance(provider, str):
                provider = LLMProvider(provider)
            model = cls.get_default_model(provider)
        else:
            if isinstance(provider, str):
                provider = LLMProvider(provider)

        # Import and create the appropriate client
        if provider == LLMProvider.ANTHROPIC:
            from .anthropic import AnthropicClient
            return AnthropicClient(
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        elif provider == LLMProvider.OPENAI:
            from .openai import OpenAIClient
            return OpenAIClient(
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        elif provider == LLMProvider.VERTEX_AI:
            from .vertex_ai import VertexAIClient
            return VertexAIClient(
                model=model,
                project_id=kwargs.pop("project_id", None),
                region=kwargs.pop("region", "us-central1"),
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")
