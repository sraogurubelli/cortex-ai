"""
Base caching strategy interface for provider-agnostic prompt caching.

This module defines the abstract interface that all provider-specific caching
strategies must implement, enabling clean separation of concerns and easy extensibility.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheTokens:
    """Container for cache-related token usage information."""

    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary for serialization."""
        return {
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
        }


class CachingStrategy(ABC):
    """
    Abstract base class for provider-specific caching strategies.

    Each LLM provider (Anthropic, OpenAI, Google, etc.) can implement their own
    caching strategy while maintaining a consistent interface for the agent.
    """

    def __init__(self, provider_name: str):
        """
        Initialize caching strategy.

        Args:
            provider_name: Name of the LLM provider (e.g., "anthropic", "openai")
        """
        self.provider_name = provider_name

    @abstractmethod
    def supports_caching(self, model_name: str) -> bool:
        """
        Check if the provider/model supports prompt caching.

        Args:
            model_name: Name of the model to check

        Returns:
            bool: True if caching is supported for this model
        """
        pass

    @abstractmethod
    def get_cache_config(self) -> dict[str, Any]:
        """
        Get provider-specific cache configuration for ChatModel.

        Returns:
            dict: Configuration to pass to ChatModel (e.g., extra_headers, model_kwargs)
        """
        pass

    @abstractmethod
    def extract_cache_tokens(self, response: Any) -> CacheTokens:
        """
        Extract cache token usage information from LLM response.

        Args:
            response: The response from the LLM (AIMessage or similar)

        Returns:
            CacheTokens: Container with cache token usage information
        """
        pass
