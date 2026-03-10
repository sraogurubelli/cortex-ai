"""
Test script for middleware system.

Demonstrates:
1. Built-in middleware (logging, timing, error handling, rate limiting)
2. Custom middleware creation
3. Middleware chaining
4. Pre/post hooks for LLM and tool calls
5. Error interception
6. Metrics and statistics

Prerequisites:
    No extra dependencies needed

Run with:
    python examples/test_middleware.py
"""

import asyncio
import logging

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

from cortex.orchestration import Agent, ModelConfig
from cortex.orchestration.middleware import (
    BaseMiddleware,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    MiddlewareContext,
    RateLimitMiddleware,
    TimingMiddleware,
)

# Setup logging to see middleware output
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@tool
async def search(query: str) -> str:
    """Search for information."""
    await asyncio.sleep(0.1)  # Simulate API call
    return f"Found results for: {query}"


@tool
async def calculate(expression: str) -> str:
    """Calculate a math expression."""
    await asyncio.sleep(0.05)
    try:
        result = eval(expression)  # noqa: S307
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"


def demo_logging_middleware():
    """Demonstrate logging middleware."""
    print("=" * 70)
    print("Demo 1: Logging Middleware")
    print("=" * 70)

    middleware = LoggingMiddleware(
        log_level=logging.INFO,
        log_messages=True,
        log_tools=True,
        log_usage=True,
    )

    print("\n📊 Middleware configuration:")
    print(f"  Log level: INFO")
    print(f"  Log messages: {middleware.log_messages}")
    print(f"  Log tools: {middleware.log_tools}")
    print(f"  Log usage: {middleware.log_usage}")

    print("\n✓ LoggingMiddleware automatically logs:")
    print("  - LLM requests and responses")
    print("  - Tool calls and results")
    print("  - Token usage")
    print("  - Errors with context")


async def demo_timing_middleware():
    """Demonstrate timing middleware."""
    print("\n" + "=" * 70)
    print("Demo 2: Timing Middleware")
    print("=" * 70)

    timing_mw = TimingMiddleware()

    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[search, calculate],
        middleware=[timing_mw],
    )

    print("\n📊 Running agent with timing middleware...")

    # Make some calls
    await agent.run("Search for Python documentation")
    await agent.run("Calculate 2 + 2")

    # Get timing stats
    stats = timing_mw.get_stats()

    print("\n⏱️  Timing Statistics:")
    for operation, metrics in stats.items():
        print(f"\n  {operation}:")
        print(f"    Count: {metrics['count']}")
        print(f"    Min: {metrics['min']:.3f}s")
        print(f"    Max: {metrics['max']:.3f}s")
        print(f"    Avg: {metrics['avg']:.3f}s")
        print(f"    Total: {metrics['total']:.3f}s")

    print("\n✓ Timing middleware tracks execution duration!")


async def demo_error_handling_middleware():
    """Demonstrate error handling middleware."""
    print("\n" + "=" * 70)
    print("Demo 3: Error Handling Middleware")
    print("=" * 70)

    error_mw = ErrorHandlingMiddleware(
        track_errors=True,
        log_errors=True,
    )

    @tool
    async def failing_tool(input_str: str) -> str:
        """A tool that sometimes fails."""
        if "error" in input_str.lower():
            raise ValueError("Intentional error for demo")
        return "Success!"

    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[failing_tool],
        middleware=[error_mw],
    )

    print("\n📊 Running agent with error handling middleware...")

    # Successful call
    try:
        result = await agent.run("Call the tool with 'success'")
        print(f"  ✓ Success: {result.response[:50]}...")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # Failing call
    try:
        result = await agent.run("Call the tool with 'error'")
        print(f"  ✓ Success: {result.response[:50]}...")
    except Exception as e:
        print(f"  ✓ Error caught: {type(e).__name__}")

    # Get error stats
    stats = error_mw.get_error_stats()

    print("\n📊 Error Statistics:")
    for error_key, count in stats.items():
        print(f"  {error_key}: {count}")

    print("\n✓ Error handling middleware tracks and logs errors!")


async def demo_rate_limit_middleware():
    """Demonstrate rate limiting middleware."""
    print("\n" + "=" * 70)
    print("Demo 4: Rate Limiting Middleware")
    print("=" * 70)

    rate_limit_mw = RateLimitMiddleware(
        tool_limits={
            "expensive_api": (3, 10),  # 3 calls per 10 seconds
        },
        default_limit=(5, 10),  # 5 calls per 10 seconds default
    )

    @tool
    async def expensive_api(query: str) -> str:
        """An expensive API call."""
        return f"Expensive result for: {query}"

    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[expensive_api],
        middleware=[rate_limit_mw],
    )

    print("\n📊 Rate limits configured:")
    print("  expensive_api: 3 calls per 10 seconds")

    print("\n📊 Making calls...")

    # Make calls until rate limit
    for i in range(5):
        try:
            await agent.run(f"Call expensive_api with query {i}")
            print(f"  ✓ Call {i + 1} succeeded")
        except ValueError as e:
            print(f"  ✗ Call {i + 1} rate limited: {e}")
            break

    # Get usage stats
    stats = rate_limit_mw.get_usage_stats()

    print("\n📊 Rate Limit Usage:")
    for tool_name, metrics in stats.items():
        print(f"\n  {tool_name}:")
        print(f"    Calls in window: {metrics['calls_in_window']}/{metrics['limit']}")
        print(f"    Remaining: {metrics['remaining']}")

    print("\n✓ Rate limiting middleware prevents overuse!")


async def demo_custom_middleware():
    """Demonstrate creating custom middleware."""
    print("\n" + "=" * 70)
    print("Demo 5: Custom Middleware")
    print("=" * 70)

    class CustomMiddleware(BaseMiddleware):
        """Custom middleware that adds a system message."""

        async def before_llm_call(self, messages, context=None, **kwargs):
            # Add custom system message
            custom_msg = SystemMessage(
                content="Always respond in a concise, bullet-point format."
            )
            modified_messages = [custom_msg] + messages
            print(f"  ✓ Added custom system message")
            return modified_messages, kwargs

        async def after_llm_call(self, result, context=None, **kwargs):
            # Log response length
            response_len = len(str(result.content))
            print(f"  ✓ Response length: {response_len} chars")
            return result

        async def before_tool_call(self, tool_name, tool_input, context=None, **kwargs):
            # Validate tool input
            if not tool_input:
                raise ValueError(f"Tool {tool_name} requires input")
            print(f"  ✓ Validated tool input for {tool_name}")
            return tool_input, kwargs

        async def after_tool_call(self, tool_name, result, context=None, **kwargs):
            # Transform result
            transformed = f"[RESULT] {result}"
            print(f"  ✓ Transformed result from {tool_name}")
            return transformed

    custom_mw = CustomMiddleware()

    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[search],
        middleware=[custom_mw],
    )

    print("\n📊 Running agent with custom middleware...")
    result = await agent.run("What is Python?")

    print(f"\n  Final response: {result.response[:100]}...")

    print("\n✓ Custom middleware can modify requests and responses!")


async def demo_middleware_chaining():
    """Demonstrate chaining multiple middleware."""
    print("\n" + "=" * 70)
    print("Demo 6: Middleware Chaining")
    print("=" * 70)

    # Chain multiple middleware
    middleware = [
        LoggingMiddleware(log_level=logging.INFO),
        TimingMiddleware(),
        ErrorHandlingMiddleware(),
    ]

    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[search, calculate],
        middleware=middleware,
    )

    print("\n📊 Middleware chain:")
    for i, mw in enumerate(middleware, 1):
        print(f"  {i}. {mw.__class__.__name__}")

    print("\n📊 Execution order:")
    print("  Before hooks: 1 → 2 → 3 → LLM/Tool")
    print("  After hooks: LLM/Tool → 3 → 2 → 1")

    print("\n📊 Running agent with middleware chain...")
    result = await agent.run("Search for Python and calculate 2+2")

    # Get stats from timing middleware
    timing_stats = middleware[1].get_stats()

    print("\n⏱️  Combined Timing Stats:")
    for operation, metrics in timing_stats.items():
        print(f"  {operation}: {metrics['count']} calls, avg {metrics['avg']:.3f}s")

    print("\n✓ Middleware can be chained for combined functionality!")


async def demo_middleware_context():
    """Demonstrate middleware context."""
    print("\n" + "=" * 70)
    print("Demo 7: Middleware Context")
    print("=" * 70)

    class ContextAwareMiddleware(BaseMiddleware):
        """Middleware that uses context."""

        async def before_llm_call(self, messages, context=None, **kwargs):
            if context:
                print(f"\n  Context info:")
                print(f"    Agent: {context.agent_name}")
                print(f"    Thread: {context.thread_id}")
                print(f"    User: {context.user_id}")
                print(f"    Session: {context.session_id}")

            return messages, kwargs

    middleware = [ContextAwareMiddleware()]

    agent = Agent(
        name="context-demo-agent",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        middleware=middleware,
        context={
            "user_id": "user-123",
            "session_id": "session-456",
        },
    )

    print("\n📊 Running agent with context-aware middleware...")
    result = await agent.run("Hello", thread_id="thread-789")

    print("\n✓ Middleware receives rich context about execution!")


async def main():
    """Run all middleware demos."""
    print("\n" + "=" * 70)
    print("Cortex Orchestration SDK - Middleware System")
    print("=" * 70)

    demo_logging_middleware()
    await demo_timing_middleware()
    await demo_error_handling_middleware()
    await demo_rate_limit_middleware()
    await demo_custom_middleware()
    await demo_middleware_chaining()
    await demo_middleware_context()

    print("\n" + "=" * 70)
    print("All Middleware Demos Complete!")
    print("=" * 70)

    print("\n✨ Key Features Demonstrated:")
    print("  1. LoggingMiddleware - Automatic logging of LLM/tool calls")
    print("  2. TimingMiddleware - Execution time tracking")
    print("  3. ErrorHandlingMiddleware - Error tracking and logging")
    print("  4. RateLimitMiddleware - Tool call rate limiting")
    print("  5. Custom middleware - Create your own hooks")
    print("  6. Middleware chaining - Combine multiple middleware")
    print("  7. Context awareness - Access execution context")

    print("\n🎯 Use Cases:")
    print("  - Logging and debugging (track all LLM and tool interactions)")
    print("  - Performance monitoring (identify slow operations)")
    print("  - Error handling (centralized error logging and tracking)")
    print("  - Rate limiting (prevent API quota exhaustion)")
    print("  - Access control (validate permissions before tool calls)")
    print("  - Caching (cache LLM responses or tool results)")
    print("  - Metrics (track usage for billing/analytics)")

    print("\n💡 Best Practices:")
    print("  1. Chain middleware in logical order")
    print("  2. Keep middleware focused (single responsibility)")
    print("  3. Use context for multi-tenant apps")
    print("  4. Handle errors gracefully in middleware")
    print("  5. Disable middleware in production if not needed")

    print("\n🔧 Advanced Patterns:")
    print("  Caching:")
    print("    - Implement after_llm_call to cache responses")
    print("    - Check cache in before_llm_call to skip LLM")
    print("  Access Control:")
    print("    - Check permissions in before_tool_call")
    print("    - Raise exception if access denied")
    print("  Transformation:")
    print("    - Modify messages in before_llm_call (add context)")
    print("    - Filter results in after_llm_call (remove sensitive data)")


if __name__ == "__main__":
    asyncio.run(main())
