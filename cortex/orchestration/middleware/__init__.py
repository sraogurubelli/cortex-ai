"""
Middleware System for Cortex Orchestration.

Provides extensible middleware for intercepting and transforming LLM and tool calls:
- Pre/post hooks for LLM calls
- Pre/post hooks for tool calls
- Middleware chaining
- Built-in middleware (logging, timing, error handling, rate limiting)

Usage:
    from cortex.orchestration.middleware import (
        LoggingMiddleware,
        TimingMiddleware,
        ErrorHandlingMiddleware,
    )

    # Create middleware instances
    middleware = [
        LoggingMiddleware(),
        TimingMiddleware(),
        ErrorHandlingMiddleware(),
    ]

    # Pass to Agent
    agent = Agent(
        name="assistant",
        model=ModelConfig(model="gpt-4o"),
        middleware=middleware,
    )

Custom Middleware:
    from cortex.orchestration.middleware import BaseMiddleware

    class CustomMiddleware(BaseMiddleware):
        async def before_llm_call(self, messages, **kwargs):
            # Modify messages before LLM call
            return messages, kwargs

        async def after_llm_call(self, result, **kwargs):
            # Transform result after LLM call
            return result

        async def before_tool_call(self, tool_name, tool_input, **kwargs):
            # Validate/transform tool input
            return tool_input, kwargs

        async def after_tool_call(self, tool_name, result, **kwargs):
            # Transform tool output
            return result

        async def on_error(self, error, context, **kwargs):
            # Handle errors
            raise error
"""

from cortex.orchestration.middleware.base import BaseMiddleware, MiddlewareContext
from cortex.orchestration.middleware.built_in import (
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    TimingMiddleware,
)
from cortex.orchestration.middleware.memory import MemoryMiddleware

__all__ = [
    "BaseMiddleware",
    "MiddlewareContext",
    "LoggingMiddleware",
    "TimingMiddleware",
    "ErrorHandlingMiddleware",
    "RateLimitMiddleware",
    "MemoryMiddleware",
]
