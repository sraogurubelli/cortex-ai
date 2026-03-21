"""
No-caching strategy implementation.

This module provides a fallback strategy for providers that don't support
prompt caching or when caching is disabled.
"""

import logging
from typing import Any

from cortex.orchestration.caching.base import CachingStrategy, CacheTokens

logger = logging.getLogger(__name__)


class NoCachingStrategy(CachingStrategy):
    """
    Fallback caching strategy that doesn't perform any caching.

    This strategy is used for:
    - Providers that don't support prompt caching (e.g., OpenAI as of Jan 2025)
    - When caching is explicitly disabled
    - When model doesn't support caching

    Example:
        from cortex.orchestration import ModelConfig, Agent
        from cortex.orchestration.caching import NoCachingStrategy

        config = ModelConfig(
            model="gpt-4o",
            caching_strategy=NoCachingStrategy(),
        )
        agent = Agent(model=config, system_prompt="...")
    """

    def __init__(self, provider_name: str = "unknown"):
        """
        Initialize no-caching strategy.

        Args:
            provider_name: Name of the provider (for logging purposes)
        """
        super().__init__(provider_name)
        logger.debug(f"Initialized NoCachingStrategy for provider: {provider_name}")

    def supports_caching(self, model_name: str) -> bool:
        """
        This strategy doesn't support caching.

        Args:
            model_name: Name of the model (ignored)

        Returns:
            bool: Always False (no caching support)
        """
        return False

    def get_cache_config(self) -> dict[str, Any]:
        """
        Get cache configuration (empty for no-caching).

        Returns:
            dict: Empty dictionary (no configuration needed)
        """
        return {}

    def extract_cache_tokens(self, response: Any) -> CacheTokens:
        """
        Extract cache tokens (always zero for no-caching strategy).

        Args:
            response: The response from the LLM

        Returns:
            CacheTokens: Empty cache tokens (all zeros)
        """
        return CacheTokens()
