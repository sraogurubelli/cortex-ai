"""
Anthropic (Claude) provider implementation for Cortex-AI.

Supports:
- Claude Sonnet, Opus, and Haiku models
- Prompt caching for cost optimization
- Streaming responses
- Tool/function calling
"""

from typing import Any, AsyncIterator, Dict, List, Optional
import os
import structlog
from anthropic import AsyncAnthropic
from anthropic.types import Message as AnthropicMessage, MessageStreamEvent

from .llm_provider import BaseLLMClient, LLMResponse

logger = structlog.get_logger(__name__)


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client implementation."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        enable_caching: bool = True,
        **kwargs
    ):
        """
        Initialize Anthropic client.

        Args:
            model: Model name (e.g., 'claude-sonnet-4', 'claude-opus-4')
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            enable_caching: Enable prompt caching for repeated context
            **kwargs: Additional parameters (e.g., betas, output_config for effort)
        """
        super().__init__(model, temperature, max_tokens, **kwargs)

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key must be provided or set in ANTHROPIC_API_KEY environment variable"
            )

        self.client = AsyncAnthropic(api_key=self.api_key)
        self.enable_caching = enable_caching

        # Extract beta features and output config
        self.betas = kwargs.get("betas", [])
        self.output_config = kwargs.get("output_config")

        logger.info(
            "Initialized Anthropic client",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_caching=enable_caching,
        )

    def _prepare_messages(
        self, messages: List[Dict[str, str]], enable_caching: bool = False
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        Prepare messages for Anthropic API format.

        Extracts system message and formats user/assistant messages.
        Optionally adds cache_control for prompt caching.

        Args:
            messages: List of messages with 'role' and 'content'
            enable_caching: Whether to enable prompt caching on last user message

        Returns:
            Tuple of (system_prompt, formatted_messages)
        """
        system_prompt = ""
        formatted_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
            elif role in ("user", "assistant"):
                formatted_msg = {"role": role, "content": content}

                # Add tool calls/results if present
                if "tool_calls" in msg:
                    formatted_msg["tool_calls"] = msg["tool_calls"]
                if "tool_call_id" in msg:
                    formatted_msg["tool_call_id"] = msg["tool_call_id"]

                formatted_messages.append(formatted_msg)

        # Enable prompt caching on the last user message for long contexts
        if enable_caching and formatted_messages and self.enable_caching:
            last_user_idx = None
            for i in range(len(formatted_messages) - 1, -1, -1):
                if formatted_messages[i]["role"] == "user":
                    last_user_idx = i
                    break

            if last_user_idx is not None:
                # Add cache_control to mark this content for caching
                formatted_messages[last_user_idx]["cache_control"] = {"type": "ephemeral"}
                logger.debug(
                    "Enabled prompt caching on message",
                    index=last_user_idx
                )

        return system_prompt, formatted_messages

    def _format_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """
        Format tools for Anthropic API.

        Args:
            tools: List of tool definitions

        Returns:
            Formatted tools for Anthropic API
        """
        if not tools:
            return None

        formatted_tools = []
        for tool in tools:
            formatted_tool = {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", tool.get("input_schema", {})),
            }
            formatted_tools.append(formatted_tool)

        return formatted_tools

    async def create(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        enable_caching: bool = True,
        **kwargs
    ) -> LLMResponse:
        """
        Create a completion from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool/function definitions
            enable_caching: Enable prompt caching for this request
            **kwargs: Additional parameters to pass to Anthropic API

        Returns:
            LLMResponse with content and metadata
        """
        system_prompt, formatted_messages = self._prepare_messages(
            messages, enable_caching=enable_caching
        )

        # Build API request parameters
        request_params = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if tools:
            request_params["tools"] = self._format_tools(tools)

        # Add beta features if specified
        if self.betas:
            request_params["betas"] = self.betas

        # Add output config (e.g., for effort parameter)
        if self.output_config:
            request_params["output_config"] = self.output_config

        logger.debug(
            "Creating Anthropic completion",
            model=self.model,
            num_messages=len(formatted_messages),
            has_tools=bool(tools),
            enable_caching=enable_caching,
        )

        try:
            response: AnthropicMessage = await self.client.messages.create(**request_params)

            # Extract content
            content = ""
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    })

            # Build usage info
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

            # Include cache metrics if available
            if hasattr(response.usage, "cache_creation_input_tokens"):
                usage["cache_creation_input_tokens"] = response.usage.cache_creation_input_tokens
            if hasattr(response.usage, "cache_read_input_tokens"):
                usage["cache_read_input_tokens"] = response.usage.cache_read_input_tokens

            logger.info(
                "Anthropic completion successful",
                model=self.model,
                usage=usage,
                finish_reason=response.stop_reason,
            )

            return LLMResponse(
                content=content,
                model=self.model,
                usage=usage,
                finish_reason=response.stop_reason,
                tool_calls=tool_calls if tool_calls else None,
                response_id=response.id,
            )

        except Exception as e:
            logger.error(
                "Anthropic API error",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise

    async def create_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        enable_caching: bool = True,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Create a streaming completion from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool/function definitions
            enable_caching: Enable prompt caching for this request
            **kwargs: Additional parameters to pass to Anthropic API

        Yields:
            Content chunks as they arrive
        """
        system_prompt, formatted_messages = self._prepare_messages(
            messages, enable_caching=enable_caching
        )

        # Build API request parameters
        request_params = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": True,
        }

        if system_prompt:
            request_params["system"] = system_prompt

        if tools:
            request_params["tools"] = self._format_tools(tools)

        # Add beta features if specified
        if self.betas:
            request_params["betas"] = self.betas

        # Add output config
        if self.output_config:
            request_params["output_config"] = self.output_config

        logger.debug(
            "Creating Anthropic streaming completion",
            model=self.model,
            num_messages=len(formatted_messages),
        )

        try:
            async with self.client.messages.stream(**request_params) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield event.delta.text
                    elif event.type == "message_stop":
                        # Stream completed
                        logger.debug("Streaming completed")
                        break

        except Exception as e:
            logger.error(
                "Anthropic streaming error",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise

    async def close(self):
        """Close the Anthropic client connection."""
        await self.client.close()
        logger.debug("Closed Anthropic client")
