"""
Google Vertex AI provider implementation for Cortex-AI.

Supports:
- Gemini models (gemini-pro, gemini-2.0-flash-exp, etc.)
- Claude on Vertex AI (via Anthropic SDK)
- Streaming responses
- Tool/function calling
"""

from typing import Any, AsyncIterator, Dict, List, Optional
import os
import structlog
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    Content,
    Part,
    Tool,
    FunctionDeclaration,
    GenerationConfig,
)

from .llm_provider import BaseLLMClient, LLMResponse

logger = structlog.get_logger(__name__)


class VertexAIClient(BaseLLMClient):
    """Google Vertex AI client implementation (Gemini models)."""

    def __init__(
        self,
        model: str,
        project_id: Optional[str] = None,
        region: str = "us-central1",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs
    ):
        """
        Initialize Vertex AI client.

        Args:
            model: Model name (e.g., 'gemini-2.0-flash-exp', 'gemini-pro')
            project_id: GCP project ID (defaults to GOOGLE_CLOUD_PROJECT env var)
            region: GCP region (defaults to 'us-central1')
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters
        """
        super().__init__(model, temperature, max_tokens, **kwargs)

        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            raise ValueError(
                "GCP project ID must be provided or set in GOOGLE_CLOUD_PROJECT environment variable"
            )

        self.region = region

        # Initialize Vertex AI
        vertexai.init(project=self.project_id, location=self.region)

        # Create generation config
        self.generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Initialize the model
        self.model_instance = GenerativeModel(
            model_name=model,
            generation_config=self.generation_config,
        )

        logger.info(
            "Initialized Vertex AI client",
            model=model,
            project_id=self.project_id,
            region=self.region,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _format_messages(
        self, messages: List[Dict[str, str]]
    ) -> List[Content]:
        """
        Format messages for Vertex AI API.

        Args:
            messages: List of messages with 'role' and 'content'

        Returns:
            Formatted messages as Content objects for Vertex AI
        """
        formatted_messages = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role")
            content_text = msg.get("content", "")

            # Extract system message separately
            if role == "system":
                system_instruction = content_text
                continue

            # Map roles to Vertex AI format
            if role == "user":
                vertex_role = "user"
            elif role == "assistant":
                vertex_role = "model"
            else:
                vertex_role = "user"  # Default to user

            # Create content with parts
            parts = [Part.from_text(content_text)]
            formatted_messages.append(Content(role=vertex_role, parts=parts))

        return formatted_messages, system_instruction

    def _format_tools(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Tool]]:
        """
        Format tools for Vertex AI API.

        Args:
            tools: List of tool definitions

        Returns:
            Formatted tools for Vertex AI API
        """
        if not tools:
            return None

        function_declarations = []
        for tool in tools:
            func_declaration = FunctionDeclaration(
                name=tool.get("name"),
                description=tool.get("description", ""),
                parameters=tool.get("parameters", {}),
            )
            function_declarations.append(func_declaration)

        return [Tool(function_declarations=function_declarations)]

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
            **kwargs: Additional parameters to pass to Vertex AI API

        Returns:
            LLMResponse with content and metadata
        """
        formatted_messages, system_instruction = self._format_messages(messages)

        # Update model with system instruction if provided
        if system_instruction:
            self.model_instance = GenerativeModel(
                model_name=self.model,
                generation_config=self.generation_config,
                system_instruction=system_instruction,
            )

        # Add tools if provided
        if tools:
            formatted_tools = self._format_tools(tools)
            self.model_instance = GenerativeModel(
                model_name=self.model,
                generation_config=self.generation_config,
                system_instruction=system_instruction,
                tools=formatted_tools,
            )

        logger.debug(
            "Creating Vertex AI completion",
            model=self.model,
            num_messages=len(formatted_messages),
            has_tools=bool(tools),
        )

        try:
            # Generate content asynchronously
            response = await self.model_instance.generate_content_async(
                contents=formatted_messages,
            )

            # Extract content
            content = response.text if response.text else ""

            # Extract tool calls if present
            tool_calls = []
            if response.candidates:
                for candidate in response.candidates:
                    if candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                tool_calls.append({
                                    "name": part.function_call.name,
                                    "arguments": dict(part.function_call.args),
                                })

            # Build usage info (Vertex AI provides token counts)
            usage = {}
            if hasattr(response, "usage_metadata"):
                usage = {
                    "input_tokens": response.usage_metadata.prompt_token_count,
                    "output_tokens": response.usage_metadata.candidates_token_count,
                    "total_tokens": response.usage_metadata.total_token_count,
                }

            # Get finish reason
            finish_reason = None
            if response.candidates:
                finish_reason = str(response.candidates[0].finish_reason)

            logger.info(
                "Vertex AI completion successful",
                model=self.model,
                usage=usage,
                finish_reason=finish_reason,
            )

            return LLMResponse(
                content=content,
                model=self.model,
                usage=usage,
                finish_reason=finish_reason,
                tool_calls=tool_calls if tool_calls else None,
            )

        except Exception as e:
            logger.error(
                "Vertex AI API error",
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
            **kwargs: Additional parameters to pass to Vertex AI API

        Yields:
            Content chunks as they arrive
        """
        formatted_messages, system_instruction = self._format_messages(messages)

        # Update model with system instruction if provided
        if system_instruction:
            self.model_instance = GenerativeModel(
                model_name=self.model,
                generation_config=self.generation_config,
                system_instruction=system_instruction,
            )

        # Add tools if provided
        if tools:
            formatted_tools = self._format_tools(tools)
            self.model_instance = GenerativeModel(
                model_name=self.model,
                generation_config=self.generation_config,
                system_instruction=system_instruction,
                tools=formatted_tools,
            )

        logger.debug(
            "Creating Vertex AI streaming completion",
            model=self.model,
            num_messages=len(formatted_messages),
        )

        try:
            # Stream content asynchronously
            response_stream = await self.model_instance.generate_content_async(
                contents=formatted_messages,
                stream=True,
            )

            async for chunk in response_stream:
                if chunk.text:
                    yield chunk.text

            logger.debug("Vertex AI streaming completed")

        except Exception as e:
            logger.error(
                "Vertex AI streaming error",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise

    async def close(self):
        """Close the Vertex AI client connection."""
        # Vertex AI SDK doesn't require explicit cleanup
        logger.debug("Closed Vertex AI client")
