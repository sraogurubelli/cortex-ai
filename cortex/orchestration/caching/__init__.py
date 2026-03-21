"""
Prompt Caching for LLM Providers

Supports provider-specific prompt caching to reduce costs and latency.

Supported Providers:
- Anthropic (Claude): Full support with prompt caching API
- Google (Gemini): Context caching for Gemini 1.5+ models
- OpenAI: Placeholder (not yet supported by OpenAI API as of Jan 2025)

Usage:
    from cortex.orchestration import ModelConfig
    from cortex.orchestration.caching import CachingStrategyFactory

    # Auto-detect caching strategy from provider/model
    strategy = CachingStrategyFactory.create_strategy(
        provider="anthropic",
        model="claude-sonnet-4"
    )

    config = ModelConfig(
        model="claude-sonnet-4",
        caching_strategy=strategy
    )
"""

from cortex.orchestration.caching.base import CachingStrategy, CacheTokens
from cortex.orchestration.caching.anthropic import AnthropicCachingStrategy
from cortex.orchestration.caching.google import GoogleCachingStrategy
from cortex.orchestration.caching.openai import OpenAICachingStrategy
from cortex.orchestration.caching.no_caching import NoCachingStrategy
from cortex.orchestration.caching.factory import CachingStrategyFactory

__all__ = [
    "CachingStrategy",
    "CacheTokens",
    "AnthropicCachingStrategy",
    "GoogleCachingStrategy",
    "OpenAICachingStrategy",
    "NoCachingStrategy",
    "CachingStrategyFactory",
]
