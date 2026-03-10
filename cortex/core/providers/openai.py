"""
OpenAI (GPT) provider implementation for Cortex-AI.

Supports:
- GPT-4, GPT-3.5 models
- o1, o3 reasoning models
- Streaming responses
- Tool/function calling
"""

from typing import Any, AsyncIterator, Dict, List, Optional
import os
import structlog
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from .llm_provider import BaseLLMClient, LLMResponse

logger = structlog.get_logger(__name__)


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT client implementation."""

    # Models that don't support temperature parameter
    NO_TEMPERATURE_MODELS = {"gpt-5", "o1", "o3"}

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ):
        """
        Initialize OpenAI client.

        Args:
            model: Model name (e.g., 'gpt-4o', 'gpt-3.5-turbo', 'o1')
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters
        """
        super().__init__(model, temperature, max_tokens, **kwargs)

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key must be provided or set in OPENAI_API_KEY environment variable"
            )

        self.client = AsyncOpenAI(api_key=self.api_key)

        # Check if model supports temperature
        self.supports_temperature = not any(
            model.startswith(prefix) for prefix in self.NO_TEMPERATURE_MODELS
        )

        logger.info(
            "Initialized OpenAI client",
            model=model,
            temperature=temperature if self.supports_temperature else "N/A",
            max_tokens=max_tokens,
        )

    def _format_messages(
        self, messages: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Format messages for OpenAI API.

        Args:
            messages: List of messages with 'role' and 'content'

        Returns:
            Formatted messages for OpenAI API
        """
        formatted_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            formatted_msg = {"role": role, "content": content}

            # Add tool calls/results if present
            if "tool_calls" in msg:
                formatted_msg["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg:
                formatted_msg["tool_call_id"] = msg["tool_call_id"]
                formatted_msg["role"] = "tool"  # OpenAI uses 'tool' role for tool responses

            formatted_messages.append(formatted_msg)

        return formatted_messages

    def _format_tools(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Format tools for OpenAI API.

        Args:
            tools: List of tool definitions

        Returns:
            Formatted tools for OpenAI API
        """
        if not tools:
            return None

        formatted_tools = []
        for tool in tools:
            formatted_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            }
            formatted_tools.append(formatted_tool)

        return formatted_tools

    async def create(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Create a completion from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool/function definitions
            **kwargs: Additional parameters to pass to OpenAI API

        Returns:
            LLMResponse with content and metadata
        """
        formatted_messages = self._format_messages(messages)

        # Build API request parameters
        request_params = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        # Only add temperature for models that support it
        if self.supports_temperature:
            request_params["temperature"] = kwargs.get("temperature", self.temperature)

        if tools:
            request_params["tools"] = self._format_tools(tools)
            # Enable parallel tool calling by default
            request_params["parallel_tool_calls"] = kwargs.get("parallel_tool_calls", True)

        logger.debug(
            "Creating OpenAI completion",
            model=self.model,
            num_messages=len(formatted_messages),
            has_tools=bool(tools),
        )

        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                **request_params
            )

            # Extract content and tool calls
            message = response.choices[0].message
            content = message.content or ""
            tool_calls = []

            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })

            # Build usage info
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            logger.info(
                "OpenAI completion successful",
                model=self.model,
                usage=usage,
                finish_reason=response.choices[0].finish_reason,
            )

            return LLMResponse(
                content=content,
                model=self.model,
                usage=usage,
                finish_reason=response.choices[0].finish_reason,
                tool_calls=tool_calls if tool_calls else None,
                response_id=response.id,
            )

        except Exception as e:
            logger.error(
                "OpenAI API error",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise

    async def create_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Create a streaming completion from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool/function definitions
            **kwargs: Additional parameters to pass to OpenAI API

        Yields:
            Content chunks as they arrive
        """
        formatted_messages = self._format_messages(messages)

        # Build API request parameters
        request_params = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": True,
        }

        # Only add temperature for models that support it
        if self.supports_temperature:
            request_params["temperature"] = kwargs.get("temperature", self.temperature)

        if tools:
            request_params["tools"] = self._format_tools(tools)
            request_params["parallel_tool_calls"] = kwargs.get("parallel_tool_calls", True)

        logger.debug(
            "Creating OpenAI streaming completion",
            model=self.model,
            num_messages=len(formatted_messages),
        )

        try:
            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content

            logger.debug("OpenAI streaming completed")

        except Exception as e:
            logger.error(
                "OpenAI streaming error",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise

    async def close(self):
        """Close the OpenAI client connection."""
        await self.client.close()
        logger.debug("Closed OpenAI client")
