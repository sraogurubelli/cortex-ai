"""
Built-in Middleware Components.

Provides common middleware implementations:
- LoggingMiddleware: Log all LLM and tool calls
- TimingMiddleware: Track execution time
- ErrorHandlingMiddleware: Enhanced error logging
- RateLimitMiddleware: Rate limiting for tool calls
"""

import logging
import time
from collections import defaultdict
from typing import Any

from cortex.orchestration.middleware.base import BaseMiddleware, MiddlewareContext

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware for logging LLM and tool calls.

    Logs:
    - LLM requests and responses
    - Tool calls and results
    - Token usage
    - Errors with context

    Example:
        middleware = [LoggingMiddleware(log_level=logging.INFO)]
        agent = Agent(name="assistant", middleware=middleware)
    """

    def __init__(
        self,
        log_level: int = logging.DEBUG,
        log_messages: bool = True,
        log_tools: bool = True,
        log_usage: bool = True,
        enabled: bool = True,
    ):
        """
        Initialize logging middleware.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_messages: Log LLM messages (default: True)
            log_tools: Log tool calls (default: True)
            log_usage: Log token usage (default: True)
            enabled: Whether middleware is active (default: True)
        """
        super().__init__(enabled=enabled)
        self.log_level = log_level
        self.log_messages = log_messages
        self.log_tools = log_tools
        self.log_usage = log_usage

    async def before_llm_call(
        self,
        messages: list[Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Log LLM request."""
        if not self.log_messages:
            return messages, kwargs

        agent_name = context.agent_name if context else "unknown"
        message_count = len(messages)

        logger.log(
            self.log_level,
            f"[{agent_name}] LLM call: {message_count} messages",
            extra={
                "agent": agent_name,
                "thread_id": context.thread_id if context else None,
                "message_count": message_count,
            },
        )

        return messages, kwargs

    async def after_llm_call(
        self,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Log LLM response and usage."""
        if not self.log_messages and not self.log_usage:
            return result

        agent_name = context.agent_name if context else "unknown"

        # Log response
        if self.log_messages:
            response_preview = str(result.content)[:100] if hasattr(result, "content") else str(result)[:100]
            logger.log(
                self.log_level,
                f"[{agent_name}] LLM response: {response_preview}...",
                extra={"agent": agent_name},
            )

        # Log usage
        if self.log_usage and hasattr(result, "usage_metadata"):
            usage = result.usage_metadata
            logger.log(
                self.log_level,
                f"[{agent_name}] Token usage: {usage}",
                extra={
                    "agent": agent_name,
                    "usage": usage,
                },
            )

        return result

    async def before_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Log tool call."""
        if not self.log_tools:
            return tool_input, kwargs

        agent_name = context.agent_name if context else "unknown"

        logger.log(
            self.log_level,
            f"[{agent_name}] Tool call: {tool_name}({list(tool_input.keys())})",
            extra={
                "agent": agent_name,
                "tool": tool_name,
                "input_keys": list(tool_input.keys()),
            },
        )

        return tool_input, kwargs

    async def after_tool_call(
        self,
        tool_name: str,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Log tool result."""
        if not self.log_tools:
            return result

        agent_name = context.agent_name if context else "unknown"
        result_preview = str(result)[:100]

        logger.log(
            self.log_level,
            f"[{agent_name}] Tool result: {tool_name} → {result_preview}...",
            extra={
                "agent": agent_name,
                "tool": tool_name,
            },
        )

        return result

    async def on_error(
        self,
        error: Exception,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> None:
        """Log errors with context."""
        agent_name = context.agent_name if context else "unknown"
        phase = kwargs.get("phase", "unknown")
        tool_name = kwargs.get("tool_name")

        log_msg = f"[{agent_name}] Error in {phase}"
        if tool_name:
            log_msg += f" (tool={tool_name})"
        log_msg += f": {error}"

        logger.error(
            log_msg,
            extra={
                "agent": agent_name,
                "phase": phase,
                "tool": tool_name,
                "error_type": type(error).__name__,
            },
            exc_info=True,
        )


class TimingMiddleware(BaseMiddleware):
    """
    Middleware for tracking execution time.

    Tracks:
    - LLM call duration
    - Tool call duration
    - Total execution time

    Example:
        middleware = [TimingMiddleware()]
        agent = Agent(name="assistant", middleware=middleware)

        # View timing stats
        print(middleware[0].get_stats())
    """

    def __init__(self, enabled: bool = True):
        """Initialize timing middleware."""
        super().__init__(enabled=enabled)
        self._llm_start_times: dict[str, float] = {}
        self._tool_start_times: dict[str, float] = {}
        self._stats: dict[str, list[float]] = defaultdict(list)

    async def before_llm_call(
        self,
        messages: list[Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Start LLM timer."""
        key = id(messages)
        self._llm_start_times[key] = time.time()
        return messages, kwargs

    async def after_llm_call(
        self,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Stop LLM timer and record duration."""
        key = id(kwargs.get("original_messages"))
        if key in self._llm_start_times:
            duration = time.time() - self._llm_start_times.pop(key)
            self._stats["llm_calls"].append(duration)

            agent_name = context.agent_name if context else "unknown"
            logger.debug(f"[{agent_name}] LLM call took {duration:.3f}s")

        return result

    async def before_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Start tool timer."""
        key = f"{tool_name}:{id(tool_input)}"
        self._tool_start_times[key] = time.time()
        return tool_input, kwargs

    async def after_tool_call(
        self,
        tool_name: str,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Stop tool timer and record duration."""
        key = f"{tool_name}:{id(kwargs.get('original_input', {}))}"
        if key in self._tool_start_times:
            duration = time.time() - self._tool_start_times.pop(key)
            self._stats[f"tool:{tool_name}"].append(duration)
            self._stats["all_tools"].append(duration)

            agent_name = context.agent_name if context else "unknown"
            logger.debug(f"[{agent_name}] Tool {tool_name} took {duration:.3f}s")

        return result

    def get_stats(self) -> dict[str, dict[str, float]]:
        """
        Get timing statistics.

        Returns:
            Dict with min/max/avg/total for each operation type

        Example:
            >>> stats = middleware.get_stats()
            >>> print(stats["llm_calls"])
            {'count': 10, 'min': 0.5, 'max': 2.3, 'avg': 1.2, 'total': 12.0}
        """
        result = {}

        for operation, durations in self._stats.items():
            if not durations:
                continue

            result[operation] = {
                "count": len(durations),
                "min": min(durations),
                "max": max(durations),
                "avg": sum(durations) / len(durations),
                "total": sum(durations),
            }

        return result

    def reset_stats(self) -> None:
        """Reset all timing statistics."""
        self._stats.clear()


class ErrorHandlingMiddleware(BaseMiddleware):
    """
    Middleware for enhanced error handling.

    Features:
    - Categorize errors by type
    - Track error counts
    - Optional retry logic
    - Error reporting

    Example:
        middleware = [ErrorHandlingMiddleware(track_errors=True)]
        agent = Agent(name="assistant", middleware=middleware)

        # View error stats
        print(middleware[0].get_error_stats())
    """

    def __init__(
        self,
        track_errors: bool = True,
        log_errors: bool = True,
        enabled: bool = True,
    ):
        """
        Initialize error handling middleware.

        Args:
            track_errors: Track error counts by type (default: True)
            log_errors: Log errors with context (default: True)
            enabled: Whether middleware is active (default: True)
        """
        super().__init__(enabled=enabled)
        self.track_errors = track_errors
        self.log_errors = log_errors
        self._error_counts: dict[str, int] = defaultdict(int)

    async def on_error(
        self,
        error: Exception,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle errors with tracking and logging."""
        error_type = type(error).__name__
        phase = kwargs.get("phase", "unknown")
        agent_name = context.agent_name if context else "unknown"

        # Track error
        if self.track_errors:
            key = f"{error_type}:{phase}"
            self._error_counts[key] += 1

        # Log error
        if self.log_errors:
            tool_name = kwargs.get("tool_name")
            log_context = {
                "agent": agent_name,
                "phase": phase,
                "error_type": error_type,
            }
            if tool_name:
                log_context["tool"] = tool_name
            if context:
                log_context["thread_id"] = context.thread_id

            logger.error(
                f"[{agent_name}] {error_type} in {phase}: {error}",
                extra=log_context,
                exc_info=False,  # Don't duplicate stack trace
            )

    def get_error_stats(self) -> dict[str, int]:
        """
        Get error statistics.

        Returns:
            Dict mapping error type:phase to count

        Example:
            >>> stats = middleware.get_error_stats()
            >>> print(stats)
            {'ValueError:before_tool_call': 3, 'TimeoutError:after_llm_call': 1}
        """
        return dict(self._error_counts)

    def reset_stats(self) -> None:
        """Reset error statistics."""
        self._error_counts.clear()


class RateLimitMiddleware(BaseMiddleware):
    """
    Middleware for rate limiting tool calls.

    Implements token bucket algorithm per tool with configurable rates.

    Example:
        # Limit to 10 calls per minute for expensive tools
        middleware = [
            RateLimitMiddleware(
                tool_limits={"expensive_api": (10, 60)},  # (calls, seconds)
            )
        ]
        agent = Agent(name="assistant", middleware=middleware)
    """

    def __init__(
        self,
        tool_limits: dict[str, tuple[int, float]] | None = None,
        default_limit: tuple[int, float] | None = None,
        enabled: bool = True,
    ):
        """
        Initialize rate limit middleware.

        Args:
            tool_limits: Dict mapping tool_name to (max_calls, time_window_seconds)
            default_limit: Default limit for tools not in tool_limits
            enabled: Whether middleware is active (default: True)

        Example:
            RateLimitMiddleware(
                tool_limits={
                    "api_call": (100, 60),  # 100 calls per minute
                    "db_query": (1000, 60),  # 1000 calls per minute
                },
                default_limit=(10, 60),  # 10 calls per minute default
            )
        """
        super().__init__(enabled=enabled)
        self.tool_limits = tool_limits or {}
        self.default_limit = default_limit
        self._call_times: dict[str, list[float]] = defaultdict(list)

    async def before_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Check rate limit before tool call."""
        # Get limit for this tool
        limit = self.tool_limits.get(tool_name, self.default_limit)
        if limit is None:
            return tool_input, kwargs

        max_calls, time_window = limit
        now = time.time()

        # Clean old timestamps
        cutoff = now - time_window
        self._call_times[tool_name] = [
            t for t in self._call_times[tool_name] if t > cutoff
        ]

        # Check if limit exceeded
        if len(self._call_times[tool_name]) >= max_calls:
            agent_name = context.agent_name if context else "unknown"
            raise ValueError(
                f"Rate limit exceeded for tool '{tool_name}': "
                f"{max_calls} calls per {time_window}s. "
                f"Try again in {cutoff - self._call_times[tool_name][0]:.1f}s"
            )

        # Record this call
        self._call_times[tool_name].append(now)

        return tool_input, kwargs

    def get_usage_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get current rate limit usage.

        Returns:
            Dict mapping tool_name to usage stats

        Example:
            >>> stats = middleware.get_usage_stats()
            >>> print(stats["api_call"])
            {'calls_in_window': 45, 'limit': 100, 'window': 60, 'remaining': 55}
        """
        now = time.time()
        result = {}

        for tool_name, call_times in self._call_times.items():
            limit = self.tool_limits.get(tool_name, self.default_limit)
            if limit is None:
                continue

            max_calls, time_window = limit
            cutoff = now - time_window

            # Count recent calls
            recent_calls = [t for t in call_times if t > cutoff]

            result[tool_name] = {
                "calls_in_window": len(recent_calls),
                "limit": max_calls,
                "window": time_window,
                "remaining": max(0, max_calls - len(recent_calls)),
            }

        return result
