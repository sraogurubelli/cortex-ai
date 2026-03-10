"""
Anthropic-specific caching strategy implementation.

This module implements the caching strategy for Anthropic Claude models,
handling the provider-specific cache control and token tracking.

For LangChain's ChatAnthropic, caching is enabled by passing cache_control
blocks in the message content. See:
https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
"""

import logging
from typing import Any

from cortex.orchestration.caching.base import CachingStrategy, CacheTokens

logger = logging.getLogger(__name__)


class AnthropicCachingStrategy(CachingStrategy):
    """
    Caching strategy implementation for Anthropic Claude models.

    Supports Anthropic's prompt caching feature with automatic cache control
    for system messages and recent conversation history.

    Example usage:
        from cortex.orchestration import ModelConfig, Agent
        from cortex.orchestration.caching import AnthropicCachingStrategy

        config = ModelConfig(
            model="claude-sonnet-4",
            caching_strategy=AnthropicCachingStrategy(),
        )
        agent = Agent(model=config, system_prompt="...")
    """

    def __init__(self, enable_caching: bool = True):
        """
        Initialize Anthropic caching strategy.

        Args:
            enable_caching: Whether to enable caching (default: True)
        """
        super().__init__("anthropic")
        self.enable_caching = enable_caching

    def supports_caching(self, model_name: str) -> bool:
        """
        Check if the specific model supports prompt caching based on model name.

        Args:
            model_name: Name of the Claude model

        Returns:
            bool: True if the model supports caching
        """
        if not self.enable_caching:
            logger.debug("Prompt caching disabled by configuration")
            return False

        # Normalize model name to lowercase for comparison
        model_name_lower = model_name.lower()

        # Models that support prompt caching (based on official Anthropic documentation)
        supported_patterns = [
            # Claude 4.6 series
            "claude-opus-4-6",
            "claude-4-6-opus",
            "claude-sonnet-4-6",
            "claude-4-6-sonnet",
            # Claude 4.5 series
            "claude-opus-4-5",
            "claude-4-5-opus",
            "claude-sonnet-4-5",
            "claude-4-5-sonnet",
            "claude-haiku-4-5",
            "claude-4-5-haiku",
            # Claude 4 series
            "claude-4",
            "claude-sonnet-4",
            "claude-4-sonnet",
            "claude-4.0-sonnet",
            "claude-opus-4",
            "claude-4-opus",
            # Claude 3.7 series
            "claude-sonnet-3.7",
            "claude-3.7-sonnet",
            "claude-3-7-sonnet",
            # Claude 3.5 series
            "claude-3-5-sonnet",
            "claude-3.5-sonnet",
            "claude-haiku-3.5",
            "claude-3-5-haiku",
            "claude-3.5-haiku",
            # Claude 3 series
            "claude-3-haiku",
            "claude-3.0-haiku",
            "claude-3-opus",
            "claude-3.0-opus",
            # Vertex AI model names (with @ notation)
            "claude-opus-4-6@",
            "claude-sonnet-4-6@",
            "claude-opus-4-5@",
            "claude-sonnet-4-5@",
            "claude-haiku-4-5@",
            "claude-opus-4@",
            "claude-sonnet-4@",
            "claude-sonnet-3.7@",
            "claude-3-5-sonnet@",
            "claude-3-haiku@",
            "claude-3-opus@",
            "claude-haiku-3.5@",
        ]

        # Check if model name contains any supported model pattern
        for pattern in supported_patterns:
            if pattern in model_name_lower:
                logger.debug(f"Model '{model_name}' supports prompt caching")
                return True

        logger.debug(f"Model '{model_name}' does not support prompt caching")
        return False

    def get_cache_config(self) -> dict[str, Any]:
        """
        Get provider-specific cache configuration for ChatAnthropic.

        For Anthropic, caching is controlled via the message content blocks.
        LangChain's ChatAnthropic automatically handles cache control when
        messages have the appropriate structure.

        Returns:
            dict: Empty dict (caching is handled at message level, not model level)
        """
        # For LangChain's ChatAnthropic, cache control is added per-message
        # via the content blocks, not as a model-level configuration.
        # Return empty dict as no model-level config is needed.
        return {}

    def extract_cache_tokens(self, response: Any) -> CacheTokens:
        """
        Extract cache token usage from Anthropic LLM response.

        For LangChain's ChatAnthropic, usage information is available in:
        - response.response_metadata["usage"]
        - response.usage_metadata (LangChain's standardized format)

        Args:
            response: AIMessage or similar response object from ChatAnthropic

        Returns:
            CacheTokens: Container with cache token usage information
        """
        cache_tokens = CacheTokens()

        try:
            # Try LangChain's standardized usage_metadata first
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                metadata = response.usage_metadata

                # LangChain may expose cache tokens in usage_metadata
                if isinstance(metadata, dict):
                    cache_tokens.cache_read_tokens = metadata.get(
                        "cache_read_input_tokens", 0
                    )
                    cache_tokens.cache_creation_input_tokens = metadata.get(
                        "cache_creation_input_tokens", 0
                    )
                    return cache_tokens

            # Try response_metadata (Anthropic-specific format)
            if (
                hasattr(response, "response_metadata")
                and response.response_metadata
            ):
                metadata = response.response_metadata

                # Check for usage information
                if "usage" in metadata:
                    usage = metadata["usage"]

                    # Extract cache read tokens
                    cache_tokens.cache_read_tokens = usage.get(
                        "cache_read_input_tokens", 0
                    )

                    # Extract cache creation tokens
                    cache_tokens.cache_creation_input_tokens = usage.get(
                        "cache_creation_input_tokens", 0
                    )

            return cache_tokens

        except Exception as e:
            logger.warning(f"Error extracting cache tokens: {e}")
            return cache_tokens

    def create_system_message_with_cache(self, content: str) -> dict[str, Any]:
        """
        Create a system message with cache control enabled.

        For Anthropic, system messages can be cached by adding cache_control
        blocks to the content.

        Args:
            content: The system message content

        Returns:
            dict: Message dict with cache control
        """
        return {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }

    def add_cache_breakpoint_to_message(
        self, message: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Add cache breakpoint to a user/assistant message.

        This marks the message as a cache boundary, allowing subsequent
        messages to benefit from the cached prefix.

        Args:
            message: Message dict to add cache control to

        Returns:
            dict: Modified message with cache control
        """
        if not isinstance(message, dict):
            return message

        # If content is a string, convert to content blocks
        if isinstance(message.get("content"), str):
            message["content"] = [
                {
                    "type": "text",
                    "text": message["content"],
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        # If content is already a list of blocks, add cache_control to last block
        elif isinstance(message.get("content"), list) and message["content"]:
            last_block = message["content"][-1]
            if isinstance(last_block, dict) and "text" in last_block:
                last_block["cache_control"] = {"type": "ephemeral"}

        return message
