"""
Google (Gemini) caching strategy implementation.

This module implements the caching strategy for Google Gemini models,
supporting Google's context caching feature.

Google's context caching allows you to cache large context (system instructions,
documents, conversation history) for reuse across multiple requests.

See: https://ai.google.dev/gemini-api/docs/caching
"""

import logging
from typing import Any

from cortex.orchestration.caching.base import CachingStrategy, CacheTokens

logger = logging.getLogger(__name__)


class GoogleCachingStrategy(CachingStrategy):
    """
    Caching strategy implementation for Google Gemini models.

    Supports Google's context caching feature for Gemini 1.5 Pro and Flash models.

    Google's caching differs from Anthropic's:
    - Creates named cache entries with configurable TTL (up to 1 hour)
    - Cache is managed separately and referenced by name
    - Charges for cache storage time in addition to read/write

    Example:
        from cortex.orchestration import ModelConfig, Agent
        from cortex.orchestration.caching import GoogleCachingStrategy

        config = ModelConfig(
            model="gemini-1.5-pro",
            caching_strategy=GoogleCachingStrategy(),
        )
        agent = Agent(model=config, system_prompt="...")

    Note: LangChain's ChatGoogleGenerativeAI may require additional configuration
    for context caching. This strategy provides the foundation for future integration.
    """

    def __init__(self, enable_caching: bool = True):
        """
        Initialize Google caching strategy.

        Args:
            enable_caching: Whether to enable caching (default: True)
        """
        super().__init__("google")
        self.enable_caching = enable_caching

    def supports_caching(self, model_name: str) -> bool:
        """
        Check if the specific Gemini model supports context caching.

        Args:
            model_name: Name of the Gemini model

        Returns:
            bool: True if the model supports caching
        """
        if not self.enable_caching:
            logger.debug("Prompt caching disabled by configuration")
            return False

        # Normalize model name to lowercase for comparison
        model_name_lower = model_name.lower()

        # Models that support context caching (Gemini 1.5+)
        supported_patterns = [
            # Gemini 1.5 series
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro-001",
            "gemini-1.5-flash-001",
            "gemini-1.5-pro-002",
            "gemini-1.5-flash-002",
            # Future Gemini 2.0+ models (likely to support caching)
            "gemini-2.0",
            "gemini-2.5",
        ]

        # Check if model name contains any supported model pattern
        for pattern in supported_patterns:
            if pattern in model_name_lower:
                logger.debug(f"Model '{model_name}' supports context caching")
                return True

        logger.debug(f"Model '{model_name}' does not support context caching")
        return False

    def get_cache_config(self) -> dict[str, Any]:
        """
        Get provider-specific cache configuration for ChatGoogleGenerativeAI.

        For Google's context caching, configuration may include:
        - cached_content: Reference to pre-created cache
        - TTL settings for cache lifetime

        Returns:
            dict: Configuration to pass to ChatGoogleGenerativeAI

        Note: LangChain's ChatGoogleGenerativeAI integration with context caching
        may require additional setup. This method provides a foundation for
        future full integration.
        """
        # For now, return empty dict
        # When LangChain fully supports Google context caching in ChatGoogleGenerativeAI:
        # - Add cache creation logic
        # - Add cache reference parameters
        # - Add TTL configuration
        return {}

    def extract_cache_tokens(self, response: Any) -> CacheTokens:
        """
        Extract cache token usage from Google Gemini response.

        Args:
            response: The response from ChatGoogleGenerativeAI

        Returns:
            CacheTokens: Container with cache token usage information
        """
        cache_tokens = CacheTokens()

        try:
            # Try LangChain's standardized usage_metadata first
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                metadata = response.usage_metadata

                # Google may expose cache tokens in usage_metadata
                if isinstance(metadata, dict):
                    # Google uses different field names for cache metrics
                    cache_tokens.cache_read_tokens = metadata.get(
                        "cached_content_token_count", 0
                    )
                    # Google doesn't separately track cache writes in the same way
                    # Cache creation is a separate API call
                    return cache_tokens

            # Try response_metadata (Google-specific format)
            if (
                hasattr(response, "response_metadata")
                and response.response_metadata
            ):
                metadata = response.response_metadata

                # Check for usage information
                if "usage_metadata" in metadata:
                    usage = metadata["usage_metadata"]

                    # Extract cached content token count
                    cache_tokens.cache_read_tokens = usage.get(
                        "cached_content_token_count", 0
                    )

            return cache_tokens

        except Exception as e:
            logger.warning(f"Error extracting cache tokens from Google response: {e}")
            return cache_tokens

    # Future methods for full Google context caching integration:
    # def create_cache_entry(
    #     self,
    #     content: str,
    #     ttl_seconds: int = 3600,
    # ) -> str:
    #     """Create a named cache entry for reuse."""
    #     pass
    #
    # def create_system_message_with_cache(
    #     self,
    #     content: str,
    #     cache_name: str | None = None,
    # ) -> dict[str, Any]:
    #     """Create system message with Google cache reference."""
    #     pass
