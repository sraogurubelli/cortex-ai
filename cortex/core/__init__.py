"""
Cortex-AI Core: Agent orchestration and LLM integration.
"""

from .providers.llm_provider import (
    BaseLLMClient,
    LLMProvider,
    LLMProviderFactory,
    LLMResponse,
    Message,
)
from .providers.anthropic import AnthropicClient
from .providers.openai import OpenAIClient
from .providers.vertex_ai import VertexAIClient

from .agents.conversation_manager import (
    ConversationManager,
    Message as ConversationMessage,
    MessageRole,
    ToolCall,
    ToolResult,
)
from .agents.base_agent import BaseAgent, BaseTool
from .agents.unified_agent import UnifiedAgent, DEFAULT_SYSTEM_PROMPT

from .streaming.stream_writer import (
    StreamWriter,
    create_stream_writer,
    create_streaming_response,
)

__all__ = [
    # Providers
    "BaseLLMClient",
    "LLMProvider",
    "LLMProviderFactory",
    "LLMResponse",
    "Message",
    "AnthropicClient",
    "OpenAIClient",
    "VertexAIClient",
    # Conversation
    "ConversationManager",
    "ConversationMessage",
    "MessageRole",
    "ToolCall",
    "ToolResult",
    # Agents
    "BaseAgent",
    "BaseTool",
    "UnifiedAgent",
    "DEFAULT_SYSTEM_PROMPT",
    # Streaming
    "StreamWriter",
    "create_stream_writer",
    "create_streaming_response",
]
