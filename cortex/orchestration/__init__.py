"""
Cortex Orchestration SDK

LangGraph-based agent orchestration for Cortex-AI.

Features:
- Single and multi-agent orchestration
- LLM provider abstraction (OpenAI, Anthropic, Google)
- Tool registry and management
- Streaming and observability
- Token usage tracking
- Prompt caching (Anthropic)
- MCP protocol support (optional)
- Retry logic and rate limiting
"""

from .agent import Agent, AgentResult
from .builder import build_agent
from .caching import AnthropicCachingStrategy, CacheTokens, CachingStrategy
from .compression import (
    CompressionConfig,
    compress_conversation_history,
    estimate_tokens,
    should_compress,
)
from .config import AgentConfig, ModelConfig
from .http_logging import (
    disable_http_logging,
    enable_http_logging,
    http_logging_context,
    is_http_logging_enabled,
)
from .observability.telemetry import (
    get_tracer,
    initialize_telemetry,
    is_telemetry_enabled,
    shutdown_telemetry,
)
from .llm import LLMClient
from .middleware import (
    BaseMiddleware,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    MemoryMiddleware,
    MessageTrimmingMiddleware,
    MiddlewareContext,
    RateLimitMiddleware,
    TimingMiddleware,
    create_summarization_middleware,
)
from .observability.conversation import (
    dump_conversation_history,
    serialize_message,
    serialize_messages,
)
from .observability.monitor import SwarmMonitor

# Optional: Session persistence (requires PostgreSQL)
try:
    from .session import (
        build_thread_id,
        close_checkpointer_pool,
        get_checkpointer,
        has_existing_checkpoint,
        is_checkpointer_healthy,
        is_checkpointing_enabled,
        open_checkpointer_pool,
    )

    _SESSION_AVAILABLE = True
except ImportError:
    _SESSION_AVAILABLE = False
    build_thread_id = None
    close_checkpointer_pool = None
    get_checkpointer = None
    has_existing_checkpoint = None
    is_checkpointer_healthy = None
    is_checkpointing_enabled = None
    open_checkpointer_pool = None
from .observability import ModelUsage, ModelUsageTracker, resolve_model_name
from .streaming import EventType, StreamHandler, StreamWriterProtocol
from .swarm import Swarm, create_handoff_tool
from .tools import ToolRegistry
from .local_tool import create_local_tool, create_tools, local_tool
from .messages import dicts_to_messages, messages_to_dicts
from .context import (
    clear_request_context,
    get_agent_name,
    get_conversation_id,
    get_model_name,
    get_principal_id,
    get_project_id,
    get_request_id,
    get_stream_writer,
    get_tenant_id,
    request_context,
    set_agent_name,
    set_conversation_id,
    set_model_name,
    set_principal_id,
    set_project_id,
    set_request_id,
    set_stream_writer,
    set_tenant_id,
)
from .validation import (
    format_schema_path,
    get_schema_requirements,
    parse_json,
    parse_yaml,
    resolve_content_from_path,
    validate_json_file,
    validate_json_schema,
    validate_yaml_schema,
)

# Optional imports (may fail if dependencies not installed)
try:
    from .mcp import (
        HTTPMCPConfig,
        MCPAuth,
        MCPConfig,
        MCPLoader,
        MCPServerRegistry,
        MCPTransport,
        SSEMCPConfig,
        STDIOMCPConfig,
        mcp_server_registry,
    )

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    HTTPMCPConfig = None
    MCPAuth = None
    MCPConfig = None
    MCPLoader = None
    MCPServerRegistry = None
    MCPTransport = None
    SSEMCPConfig = None
    STDIOMCPConfig = None
    mcp_server_registry = None

__all__ = [
    # High-level Agent
    "Agent",
    "AgentResult",
    # Configuration
    "AgentConfig",
    "ModelConfig",
    # Builder
    "build_agent",
    # LLM
    "LLMClient",
    # Caching
    "CachingStrategy",
    "CacheTokens",
    "AnthropicCachingStrategy",
    # Compression
    "CompressionConfig",
    "compress_conversation_history",
    "estimate_tokens",
    "should_compress",
    # Middleware
    "BaseMiddleware",
    "MiddlewareContext",
    "LoggingMiddleware",
    "TimingMiddleware",
    "ErrorHandlingMiddleware",
    "RateLimitMiddleware",
    "MemoryMiddleware",
    "MessageTrimmingMiddleware",
    "create_summarization_middleware",
    # Streaming
    "StreamHandler",
    "EventType",
    "StreamWriterProtocol",
    # Observability
    "ModelUsageTracker",
    "ModelUsage",
    "resolve_model_name",
    # HTTP Logging
    "enable_http_logging",
    "disable_http_logging",
    "is_http_logging_enabled",
    "http_logging_context",
    # OpenTelemetry
    "initialize_telemetry",
    "get_tracer",
    "is_telemetry_enabled",
    "shutdown_telemetry",
    # Session Persistence (optional)
    "open_checkpointer_pool",
    "close_checkpointer_pool",
    "get_checkpointer",
    "is_checkpointer_healthy",
    "is_checkpointing_enabled",
    "has_existing_checkpoint",
    "build_thread_id",
    # Validation
    "resolve_content_from_path",
    "validate_json_schema",
    "validate_yaml_schema",
    "validate_json_file",
    "parse_yaml",
    "parse_json",
    "format_schema_path",
    "get_schema_requirements",
    # Observability
    "serialize_message",
    "serialize_messages",
    "dump_conversation_history",
    "SwarmMonitor",
    # Tools
    "ToolRegistry",
    "local_tool",
    "create_local_tool",
    "create_tools",
    # Request Context
    "request_context",
    "get_tenant_id",
    "set_tenant_id",
    "get_project_id",
    "set_project_id",
    "get_principal_id",
    "set_principal_id",
    "get_conversation_id",
    "set_conversation_id",
    "get_stream_writer",
    "set_stream_writer",
    "get_request_id",
    "set_request_id",
    "get_agent_name",
    "set_agent_name",
    "get_model_name",
    "set_model_name",
    "clear_request_context",
    # Message conversion
    "dicts_to_messages",
    "messages_to_dicts",
    # Multi-agent
    "Swarm",
    "create_handoff_tool",
    # MCP (optional)
    "MCPConfig",
    "HTTPMCPConfig",
    "SSEMCPConfig",
    "STDIOMCPConfig",
    "MCPTransport",
    "MCPAuth",
    "MCPLoader",
    "MCPServerRegistry",
    "mcp_server_registry",
]
