"""
Base Middleware Interface for Cortex Orchestration.

Defines the protocol for intercepting LLM and tool calls with pre/post hooks.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MiddlewareContext:
    """
    Context passed to middleware hooks.

    Contains information about the current execution context including
    agent name, thread ID, user context, and custom metadata.
    """

    agent_name: str
    """Name of the agent executing the call."""

    thread_id: str | None = None
    """Thread ID for conversation persistence."""

    user_id: str | None = None
    """User ID for multi-tenant applications."""

    session_id: str | None = None
    """Session ID for tracking user sessions."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Custom metadata for the execution context."""

    def __repr__(self) -> str:
        return (
            f"MiddlewareContext(agent={self.agent_name}, "
            f"thread={self.thread_id}, user={self.user_id})"
        )


class BaseMiddleware:
    """
    Base class for middleware components.

    Middleware can intercept and transform LLM calls, tool calls, and errors.
    Override the hooks you need - all hooks are optional.

    Hooks execution order:
        1. before_llm_call() - Before sending to LLM
        2. after_llm_call() - After receiving from LLM
        3. before_tool_call() - Before executing tool
        4. after_tool_call() - After tool execution
        5. on_error() - On any error

    Example:
        class CustomMiddleware(BaseMiddleware):
            async def before_llm_call(self, messages, **kwargs):
                # Add custom system message
                messages = [SystemMessage(content="Be concise")] + messages
                return messages, kwargs

            async def after_llm_call(self, result, **kwargs):
                # Log token usage
                logger.info(f"Used {result.usage} tokens")
                return result
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize middleware.

        Args:
            enabled: Whether the middleware is active (default: True)
        """
        self.enabled = enabled

    async def before_llm_call(
        self,
        messages: list[Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        """
        Hook called before LLM invocation.

        Use this to:
        - Modify or filter messages
        - Add system messages
        - Inject context
        - Validate input
        - Log requests

        Args:
            messages: List of messages to send to LLM
            context: Execution context
            **kwargs: Additional LLM parameters (temperature, max_tokens, etc.)

        Returns:
            Tuple of (modified_messages, modified_kwargs)

        Example:
            async def before_llm_call(self, messages, **kwargs):
                # Add custom system message
                system_msg = SystemMessage(content="Be helpful")
                return [system_msg] + messages, kwargs
        """
        return messages, kwargs

    async def after_llm_call(
        self,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Hook called after LLM returns.

        Use this to:
        - Transform response
        - Log responses
        - Track usage/costs
        - Cache results
        - Filter sensitive content

        Args:
            result: LLM response (AIMessage or similar)
            context: Execution context
            **kwargs: Original request parameters

        Returns:
            Modified result (or original if no changes)

        Example:
            async def after_llm_call(self, result, **kwargs):
                # Log token usage
                if hasattr(result, 'usage_metadata'):
                    logger.info(f"Tokens: {result.usage_metadata}")
                return result
        """
        return result

    async def before_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Hook called before tool execution.

        Use this to:
        - Validate tool input
        - Transform parameters
        - Check permissions
        - Log tool calls
        - Rate limit

        Args:
            tool_name: Name of the tool being called
            tool_input: Input parameters for the tool
            context: Execution context
            **kwargs: Additional metadata

        Returns:
            Tuple of (modified_tool_input, modified_kwargs)

        Example:
            async def before_tool_call(self, tool_name, tool_input, **kwargs):
                # Validate required parameter
                if 'user_id' not in tool_input:
                    raise ValueError(f"{tool_name} requires user_id")
                return tool_input, kwargs
        """
        return tool_input, kwargs

    async def after_tool_call(
        self,
        tool_name: str,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Hook called after tool execution.

        Use this to:
        - Transform tool output
        - Log results
        - Filter sensitive data
        - Cache results
        - Track metrics

        Args:
            tool_name: Name of the tool that was called
            result: Tool execution result
            context: Execution context
            **kwargs: Original tool input and metadata

        Returns:
            Modified result (or original if no changes)

        Example:
            async def after_tool_call(self, tool_name, result, **kwargs):
                # Log tool execution
                logger.info(f"Tool {tool_name} returned: {type(result)}")
                return result
        """
        return result

    async def on_error(
        self,
        error: Exception,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Hook called when an error occurs.

        Use this to:
        - Log errors with context
        - Send alerts
        - Transform errors
        - Retry logic
        - Fallback handling

        Args:
            error: The exception that occurred
            context: Execution context
            **kwargs: Additional error context (phase, tool_name, etc.)

        Raises:
            Exception: Re-raise the error or raise a different one

        Example:
            async def on_error(self, error, context, **kwargs):
                # Log with context
                logger.error(
                    f"Error in {context.agent_name}: {error}",
                    extra={"thread_id": context.thread_id}
                )
                # Re-raise
                raise error
        """
        pass  # Default: do nothing


class MiddlewareChain:
    """
    Chain multiple middleware components together.

    Executes middleware in order for pre-hooks (before_*) and in reverse
    order for post-hooks (after_*).

    Example:
        chain = MiddlewareChain([
            LoggingMiddleware(),
            TimingMiddleware(),
            RateLimitMiddleware(),
        ])

        # Execute before hooks
        messages, kwargs = await chain.before_llm_call(messages)

        # Execute after hooks
        result = await chain.after_llm_call(result)
    """

    def __init__(self, middleware: list[BaseMiddleware]):
        """
        Initialize middleware chain.

        Args:
            middleware: List of middleware instances (executed in order)
        """
        self.middleware = [m for m in middleware if m.enabled]

    async def before_llm_call(
        self,
        messages: list[Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Execute before_llm_call hooks in order."""
        for mw in self.middleware:
            try:
                messages, kwargs = await mw.before_llm_call(messages, context, **kwargs)
            except Exception as e:
                await self.on_error(e, context, phase="before_llm_call", middleware=mw)
                raise

        return messages, kwargs

    async def after_llm_call(
        self,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute after_llm_call hooks in reverse order."""
        for mw in reversed(self.middleware):
            try:
                result = await mw.after_llm_call(result, context, **kwargs)
            except Exception as e:
                await self.on_error(e, context, phase="after_llm_call", middleware=mw)
                raise

        return result

    async def before_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Execute before_tool_call hooks in order."""
        for mw in self.middleware:
            try:
                tool_input, kwargs = await mw.before_tool_call(
                    tool_name, tool_input, context, **kwargs
                )
            except Exception as e:
                await self.on_error(
                    e, context, phase="before_tool_call", tool_name=tool_name, middleware=mw
                )
                raise

        return tool_input, kwargs

    async def after_tool_call(
        self,
        tool_name: str,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute after_tool_call hooks in reverse order."""
        for mw in reversed(self.middleware):
            try:
                result = await mw.after_tool_call(tool_name, result, context, **kwargs)
            except Exception as e:
                await self.on_error(
                    e, context, phase="after_tool_call", tool_name=tool_name, middleware=mw
                )
                raise

        return result

    async def on_error(
        self,
        error: Exception,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> None:
        """Execute on_error hooks for all middleware."""
        for mw in self.middleware:
            try:
                await mw.on_error(error, context, **kwargs)
            except Exception as e:
                # Don't let error handlers crash
                logger.error(
                    f"Error in middleware {mw.__class__.__name__}.on_error: {e}",
                    exc_info=True,
                )
