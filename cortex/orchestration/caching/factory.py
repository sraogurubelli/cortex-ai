"""
Caching strategy factory for automatic provider detection and strategy creation.

This module provides a factory that automatically selects the appropriate
caching strategy based on the provider and model capabilities.
"""

import logging
from typing import Any

from cortex.orchestration.caching.base import CachingStrategy
from cortex.orchestration.caching.anthropic import AnthropicCachingStrategy
from cortex.orchestration.caching.google import GoogleCachingStrategy
from cortex.orchestration.caching.no_caching import NoCachingStrategy

logger = logging.getLogger(__name__)


class CachingStrategyFactory:
    """
    Factory for creating provider-specific caching strategies.

    Automatically detects the provider type and model capabilities to
    return the most appropriate caching strategy.

    Example:
        from cortex.orchestration.caching import CachingStrategyFactory

        # Auto-detect strategy
        strategy = CachingStrategyFactory.create_strategy(
            provider="anthropic",
            model="claude-sonnet-4"
        )

        # Use with ModelConfig
        from cortex.orchestration import ModelConfig
        config = ModelConfig(
            model="claude-sonnet-4",
            caching_strategy=CachingStrategyFactory.create_strategy(
                provider="anthropic",
                model="claude-sonnet-4"
            )
        )
    """

    # Registry of provider names to strategy classes
    _provider_strategies: dict[str, type[CachingStrategy]] = {
        "anthropic": AnthropicCachingStrategy,
        "anthropic_vertex": AnthropicCachingStrategy,  # Vertex AI uses Anthropic models
        "google": GoogleCachingStrategy,  # Google Gemini context caching
    }

    @classmethod
    def create_strategy(
        cls,
        provider: str | None,
        model: str,
        enable_caching: bool = True,
    ) -> CachingStrategy:
        """
        Create the appropriate caching strategy for the given provider and model.

        Args:
            provider: Provider name (e.g., "anthropic", "openai", "google")
                     If None, attempts to infer from model name
            model: Model name (e.g., "claude-sonnet-4", "gpt-4o")
            enable_caching: Whether to enable caching (default: True)

        Returns:
            CachingStrategy: The appropriate caching strategy instance

        Example:
            >>> strategy = CachingStrategyFactory.create_strategy(
            ...     provider="anthropic",
            ...     model="claude-sonnet-4"
            ... )
            >>> strategy.supports_caching("claude-sonnet-4")
            True
        """
        # If caching is disabled globally, return no-caching strategy
        if not enable_caching:
            logger.debug("Caching disabled globally, using NoCachingStrategy")
            return NoCachingStrategy(provider or "unknown")

        # Infer provider from model if not provided
        if provider is None:
            provider = cls._infer_provider(model)
            logger.debug(f"Inferred provider '{provider}' from model '{model}'")

        # Get the strategy class for the provider
        strategy_class = cls._provider_strategies.get(provider)

        if strategy_class is None:
            logger.debug(
                f"No caching strategy available for provider '{provider}', "
                f"using NoCachingStrategy"
            )
            return NoCachingStrategy(provider)

        try:
            # Create the strategy instance
            strategy = strategy_class(enable_caching=enable_caching)

            # Validate that the strategy actually supports caching for this model
            if not strategy.supports_caching(model):
                logger.debug(
                    f"Model '{model}' doesn't support caching for provider '{provider}', "
                    f"falling back to NoCachingStrategy"
                )
                return NoCachingStrategy(provider)

            logger.debug(
                f"Created {strategy_class.__name__} for provider '{provider}', model '{model}'"
            )
            return strategy

        except Exception as e:
            logger.error(
                f"Failed to create caching strategy for provider '{provider}': {e}",
                exc_info=True,
            )
            logger.debug(f"Falling back to NoCachingStrategy for provider '{provider}'")
            return NoCachingStrategy(provider)

    @classmethod
    def _infer_provider(cls, model: str) -> str:
        """
        Infer provider from model name prefix.

        Args:
            model: Model name

        Returns:
            str: Inferred provider name or "unknown"
        """
        model_lower = model.lower()

        # Provider inference patterns
        if model_lower.startswith("claude-"):
            return "anthropic"
        elif model_lower.startswith(("gpt-", "o1-", "o3-")):
            return "openai"
        elif model_lower.startswith("gemini-"):
            return "google"

        logger.warning(f"Could not infer provider from model name '{model}'")
        return "unknown"

    @classmethod
    def register_strategy(cls, provider: str, strategy_class: type[CachingStrategy]):
        """
        Register a custom caching strategy for a provider.

        This allows extending the factory with custom strategies.

        Args:
            provider: Provider name
            strategy_class: CachingStrategy subclass

        Example:
            >>> class CustomCachingStrategy(CachingStrategy):
            ...     pass
            >>> CachingStrategyFactory.register_strategy("custom", CustomCachingStrategy)
        """
        cls._provider_strategies[provider] = strategy_class
        logger.info(f"Registered {strategy_class.__name__} for provider '{provider}'")
