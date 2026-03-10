"""
Utility functions for orchestration.

Includes retry logic, rate limiting, and other helpers.
"""

import asyncio
import functools
import logging
import time
from collections import defaultdict
from typing import Any, Callable, TypeVar

from langchain_core.tools import BaseTool, StructuredTool

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =========================================================================
# Retry Logic
# =========================================================================


def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator to retry a function on failure with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier for exponential backoff
        exceptions: Tuple of exceptions to catch and retry

    Returns:
        Decorated function with retry logic

    Example:
        @retry_on_failure(max_retries=3, delay=1.0)
        async def flaky_api_call():
            # This will be retried up to 3 times
            result = await external_api.call()
            return result
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                current_delay = delay
                last_exception = None

                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt == max_retries:
                            logger.error(
                                f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                            )
                            raise

                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff

                raise last_exception

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                current_delay = delay
                last_exception = None

                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt == max_retries:
                            logger.error(
                                f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                            )
                            raise

                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff

                raise last_exception

            return sync_wrapper

    return decorator


def wrap_tool_with_retry(
    tool: BaseTool,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
) -> BaseTool:
    """
    Wrap a tool with retry logic.

    Args:
        tool: The tool to wrap
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier for exponential backoff

    Returns:
        Wrapped tool with retry logic

    Example:
        calculator = CalculatorTool()
        retryable_calculator = wrap_tool_with_retry(calculator, max_retries=3)
    """
    # Get the original function
    if tool.coroutine:
        original_fn = tool.coroutine
        is_async = True
    elif hasattr(tool, "func") and tool.func:
        original_fn = tool.func
        is_async = False
    else:
        # Can't wrap - return as-is
        return tool

    # Apply retry decorator
    retryable_fn = retry_on_failure(max_retries=max_retries, delay=delay, backoff=backoff)(
        original_fn
    )

    # Create new tool
    if is_async:
        return StructuredTool(
            name=tool.name,
            description=tool.description,
            coroutine=retryable_fn,
            args_schema=tool.args_schema if hasattr(tool, "args_schema") else None,
        )
    else:
        return StructuredTool(
            name=tool.name,
            description=tool.description,
            func=retryable_fn,
            args_schema=tool.args_schema if hasattr(tool, "args_schema") else None,
        )


# =========================================================================
# Rate Limiting
# =========================================================================


class RateLimiter:
    """
    Simple token bucket rate limiter.

    Example:
        # Allow 10 calls per minute
        limiter = RateLimiter(rate=10, per=60)

        async def call_api():
            await limiter.acquire()
            result = await api.call()
            return result
    """

    def __init__(self, rate: int, per: float = 1.0):
        """
        Initialize rate limiter.

        Args:
            rate: Number of tokens to generate
            per: Time period (seconds) over which tokens are generated
        """
        self.rate = rate
        self.per = per
        self.allowance = rate
        self.last_check = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """
        Acquire a token (wait if necessary).

        Blocks until a token is available.
        """
        async with self._lock:
            current = time.time()
            time_passed = current - self.last_check
            self.last_check = current

            # Add tokens based on time passed
            self.allowance += time_passed * (self.rate / self.per)

            # Cap at rate
            if self.allowance > self.rate:
                self.allowance = self.rate

            # Wait if no tokens available
            if self.allowance < 1.0:
                sleep_time = (1.0 - self.allowance) * (self.per / self.rate)
                await asyncio.sleep(sleep_time)
                self.allowance = 0.0
            else:
                self.allowance -= 1.0


class ToolRateLimiter:
    """
    Rate limiter for tools.

    Tracks rate limits per tool name.

    Example:
        limiter = ToolRateLimiter(default_rate=10, default_per=60)
        limiter.set_limit("expensive_tool", rate=5, per=60)

        # In tool execution
        await limiter.acquire("expensive_tool")
    """

    def __init__(self, default_rate: int = 60, default_per: float = 60.0):
        """
        Initialize tool rate limiter.

        Args:
            default_rate: Default rate for tools without specific limits
            default_per: Default time period for rate limit
        """
        self.default_rate = default_rate
        self.default_per = default_per
        self._limiters: dict[str, RateLimiter] = {}

    def set_limit(self, tool_name: str, rate: int, per: float = 1.0) -> None:
        """
        Set rate limit for a specific tool.

        Args:
            tool_name: Name of the tool
            rate: Number of calls allowed
            per: Time period (seconds)
        """
        self._limiters[tool_name] = RateLimiter(rate=rate, per=per)

    async def acquire(self, tool_name: str) -> None:
        """
        Acquire permission to execute a tool.

        Args:
            tool_name: Name of the tool to execute
        """
        if tool_name not in self._limiters:
            self._limiters[tool_name] = RateLimiter(
                rate=self.default_rate, per=self.default_per
            )

        await self._limiters[tool_name].acquire()


def wrap_tool_with_rate_limit(
    tool: BaseTool,
    limiter: ToolRateLimiter,
) -> BaseTool:
    """
    Wrap a tool with rate limiting.

    Args:
        tool: The tool to wrap
        limiter: The rate limiter to use

    Returns:
        Wrapped tool with rate limiting

    Example:
        limiter = ToolRateLimiter()
        limiter.set_limit("api_call", rate=10, per=60)

        api_tool = APITool()
        limited_api_tool = wrap_tool_with_rate_limit(api_tool, limiter)
    """
    # Get the original function
    if tool.coroutine:
        original_fn = tool.coroutine
        is_async = True
    elif hasattr(tool, "func") and tool.func:
        original_fn = tool.func
        is_async = False
    else:
        # Can't wrap - return as-is
        return tool

    # Create wrapper with rate limiting
    if is_async:

        async def rate_limited_async(*args, **kwargs):
            await limiter.acquire(tool.name)
            return await original_fn(*args, **kwargs)

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            coroutine=rate_limited_async,
            args_schema=tool.args_schema if hasattr(tool, "args_schema") else None,
        )
    else:

        def rate_limited_sync(*args, **kwargs):
            # For sync functions, we can't truly wait async,
            # so we log a warning instead
            logger.warning(
                f"Rate limiting for sync tool '{tool.name}' is not enforced. "
                f"Use async tools for rate limiting."
            )
            return original_fn(*args, **kwargs)

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            func=rate_limited_sync,
            args_schema=tool.args_schema if hasattr(tool, "args_schema") else None,
        )


# =========================================================================
# Tool Combinators
# =========================================================================


def combine_tool_wrappers(*wrappers: Callable[[BaseTool], BaseTool]) -> Callable[[BaseTool], BaseTool]:
    """
    Combine multiple tool wrappers into a single wrapper.

    Args:
        *wrappers: Tool wrapper functions to combine

    Returns:
        Combined wrapper function

    Example:
        # Apply retry + rate limiting + context injection
        combined = combine_tool_wrappers(
            lambda tool: wrap_tool_with_retry(tool, max_retries=3),
            lambda tool: wrap_tool_with_rate_limit(tool, limiter),
            lambda tool: registry.wrap_with_context(tool),
        )

        wrapped_tool = combined(original_tool)
    """

    def combined_wrapper(tool: BaseTool) -> BaseTool:
        result = tool
        for wrapper in wrappers:
            result = wrapper(result)
        return result

    return combined_wrapper