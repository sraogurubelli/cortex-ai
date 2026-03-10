"""
Advanced Features Demo

Comprehensive showcase of Cortex Orchestration SDK features:
- Prompt caching (Anthropic)
- Retry logic for tools
- Rate limiting
- Context injection
- Conversation debugging
- Token usage tracking
- Event suppression
"""

import asyncio
import os

from langchain_core.tools import tool
from pydantic import Field

from cortex.orchestration import Agent, ModelConfig, ToolRegistry, AnthropicCachingStrategy
from cortex.orchestration.debug import dump_conversation_history
from cortex.orchestration.utils import (
    RateLimiter,
    ToolRateLimiter,
    retry_on_failure,
    wrap_tool_with_rate_limit,
    wrap_tool_with_retry,
)


# =========================================================================
# Demo 1: Prompt Caching (Anthropic)
# =========================================================================


async def demo_prompt_caching():
    """Demonstrate Anthropic prompt caching for cost reduction."""
    print("\n" + "=" * 60)
    print("Demo 1: Prompt Caching (Anthropic)")
    print("=" * 60)

    # Create agent with caching enabled
    long_system_prompt = """You are an expert Python developer with deep knowledge of:
- Async/await patterns and asyncio
- Type hints and mypy
- Pytest and testing best practices
- FastAPI and modern web frameworks
- SQLAlchemy and database design
- Docker and containerization
- CI/CD pipelines and GitHub Actions
- Code quality tools (black, ruff, mypy)

Always provide detailed, production-ready code examples with proper error handling,
type hints, and comprehensive docstrings. Consider edge cases and follow Python
best practices (PEP 8, PEP 484, etc.).
"""

    agent = Agent(
        name="caching_demo",
        system_prompt=long_system_prompt,
        model=ModelConfig(
            model="claude-sonnet-4",
            caching_strategy=AnthropicCachingStrategy(),
        ),
    )

    print("\nFirst call - creating cache...")
    result1 = await agent.run("What is asyncio?", thread_id="cache-demo")

    print(f"\nToken usage (call 1):")
    for model, usage in result1.token_usage.items():
        print(f"  {model}:")
        print(f"    Prompt tokens: {usage.get('prompt_tokens', 0)}")
        print(f"    Cache creation: {usage.get('cache_creation_input_tokens', 0)}")
        print(f"    Cache read: {usage.get('cache_read_input_tokens', 0)}")

    print("\nSecond call - using cache...")
    result2 = await agent.run("What is FastAPI?", thread_id="cache-demo")

    print(f"\nToken usage (call 2):")
    for model, usage in result2.token_usage.items():
        print(f"  {model}:")
        print(f"    Prompt tokens: {usage.get('prompt_tokens', 0)}")
        print(f"    Cache creation: {usage.get('cache_creation_input_tokens', 0)}")
        print(f"    Cache read: {usage.get('cache_read_input_tokens', 0)}")

    print("\n✓ Cache should reduce prompt tokens on 2nd call!")
    print("✓ Typical savings: 90% cost reduction on cached content")


# =========================================================================
# Demo 2: Retry Logic
# =========================================================================


@tool
async def flaky_api_call(endpoint: str) -> str:
    """Simulates a flaky API that fails randomly."""
    import random

    if random.random() < 0.7:  # 70% failure rate
        raise Exception("API temporarily unavailable")
    return f"Success: Data from {endpoint}"


async def demo_retry_logic():
    """Demonstrate retry logic for unreliable tools."""
    print("\n" + "=" * 60)
    print("Demo 2: Retry Logic for Flaky Tools")
    print("=" * 60)

    # Wrap tool with retry logic
    retryable_api = wrap_tool_with_retry(
        flaky_api_call, max_retries=3, delay=0.5, backoff=2.0
    )

    agent = Agent(
        name="api_client",
        system_prompt="You call APIs. Use the flaky_api_call tool.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[retryable_api],
    )

    result = await agent.run("Call the /users endpoint")

    print(f"\nResult: {result.response}")
    print(f"(Tool was wrapped with retry logic - automatically retried on failures)")


# =========================================================================
# Demo 3: Rate Limiting
# =========================================================================


async def demo_rate_limiting():
    """Demonstrate rate limiting for tools."""
    print("\n" + "=" * 60)
    print("Demo 3: Rate Limiting")
    print("=" * 60)

    @tool
    async def expensive_api_call(query: str) -> str:
        """An expensive API with rate limits."""
        return f"Expensive result for: {query}"

    # Setup rate limiter: 3 calls per 10 seconds
    limiter = ToolRateLimiter(default_rate=3, default_per=10.0)
    limiter.set_limit("expensive_api_call", rate=3, per=10.0)

    # Wrap tool with rate limiting
    limited_api = wrap_tool_with_rate_limit(expensive_api_call, limiter)

    print("\nRate limit: 3 calls per 10 seconds")
    print("Calling tool 4 times (4th call will be delayed)...\n")

    # Test rate limiting
    for i in range(4):
        print(f"Call {i + 1}...", end=" ")
        # Manually call the tool's coroutine to test rate limiting
        try:
            await limited_api.coroutine(query=f"query{i}")
            print("✓ Success")
        except Exception as e:
            print(f"✗ Failed: {e}")

    print("\n(4th call was rate-limited)")


# =========================================================================
# Demo 4: Context Injection
# =========================================================================


async def demo_context_injection():
    """Demonstrate context injection for security."""
    print("\n" + "=" * 60)
    print("Demo 4: Context Injection (Security)")
    print("=" * 60)

    @tool
    async def get_user_balance(
        user_id: str = Field(..., description="User ID (injected)"),
        currency: str = Field("USD", description="Currency code"),
    ) -> str:
        """Get user's account balance."""
        # user_id is injected, not provided by LLM
        balances = {
            "user123": {"USD": 1250.50, "EUR": 1100.30},
            "user456": {"USD": 850.20, "EUR": 750.10},
        }
        balance = balances.get(user_id, {}).get(currency, 0.0)
        return f"Balance for {user_id}: {balance} {currency}"

    # Setup registry with context
    registry = ToolRegistry()
    registry.register(get_user_balance)
    registry.set_context(user_id="user123")  # Injected automatically!

    agent = Agent(
        name="banking_assistant",
        system_prompt="You help users check their balance.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tool_registry=registry,
        tools=None,  # Use all from registry
    )

    # LLM doesn't see or provide user_id - it's injected!
    result = await agent.run("What's my balance in USD?")

    print(f"\nUser: What's my balance in USD?")
    print(f"Assistant: {result.response}")
    print(f"\n✓ user_id='user123' was injected automatically")
    print(f"✓ LLM never saw the user_id parameter!")


# =========================================================================
# Demo 5: Conversation Debugging
# =========================================================================


async def demo_conversation_debugging():
    """Demonstrate conversation history dumping."""
    print("\n" + "=" * 60)
    print("Demo 5: Conversation Debugging")
    print("=" * 60)

    # Enable dumping
    os.environ["DUMP_CONVERSATION_HISTORY"] = "1"

    agent = Agent(
        name="assistant",
        system_prompt="You are helpful.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("What is 2 + 2?")

    # Dump conversation
    file_path = dump_conversation_history(
        result.messages,
        metadata={
            "model": "gpt-4o",
            "token_usage": result.token_usage,
            "query": "What is 2 + 2?",
        },
    )

    print(f"\nConversation dumped to: {file_path}")
    print(f"Message count: {len(result.messages)}")
    print(f"\n✓ Full conversation history saved for debugging")

    # Cleanup
    os.environ.pop("DUMP_CONVERSATION_HISTORY", None)


# =========================================================================
# Demo 6: Token Usage Tracking
# =========================================================================


async def demo_token_tracking():
    """Demonstrate comprehensive token usage tracking."""
    print("\n" + "=" * 60)
    print("Demo 6: Token Usage Tracking")
    print("=" * 60)

    agent = Agent(
        name="assistant",
        system_prompt="You are helpful.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    # Multi-turn conversation
    result1 = await agent.run("What is Python?", thread_id="tracking-demo")
    result2 = await agent.run(
        "And what is async/await?", thread_id="tracking-demo"
    )

    print(f"\nTurn 1 tokens: {result1.token_usage}")
    print(f"Turn 2 tokens: {result2.token_usage}")

    # Calculate total
    total_prompt = sum(
        usage.get("prompt_tokens", 0) for usage in result2.token_usage.values()
    )
    total_completion = sum(
        usage.get("completion_tokens", 0) for usage in result2.token_usage.values()
    )
    total = total_prompt + total_completion

    print(f"\nTotal tokens (both turns): {total}")
    print(f"  - Prompt: {total_prompt}")
    print(f"  - Completion: {total_completion}")


# =========================================================================
# Demo 7: Event Suppression
# =========================================================================


class QuietStreamWriter:
    """Stream writer that prints events."""

    async def write_event(self, event_type: str, data) -> None:
        print(f"  [{event_type}]", end=" ")

    async def close(self) -> None:
        print()


async def demo_event_suppression():
    """Demonstrate event suppression for clean UIs."""
    print("\n" + "=" * 60)
    print("Demo 7: Event Suppression")
    print("=" * 60)

    from langchain_core.tools import tool

    @tool
    async def calculate(expression: str) -> str:
        """Evaluate a math expression."""
        return str(eval(expression))

    # Agent with all events
    print("\n1. With all events (default):")
    agent1 = Agent(
        name="calculator",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[calculate],
    )

    writer1 = QuietStreamWriter()
    await agent1.stream_to_writer("What is 15 * 7?", stream_writer=writer1)

    # Agent with tool events suppressed
    print("\n2. With tool events suppressed:")
    agent2 = Agent(
        name="calculator",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[calculate],
        suppress_events={"tool_request", "tool_result"},  # Hide tool calls
    )

    writer2 = QuietStreamWriter()
    await agent2.stream_to_writer("What is 15 * 7?", stream_writer=writer2)

    print("\n\n✓ Tool events hidden from end-users!")


# =========================================================================
# Main
# =========================================================================


async def main():
    """Run all advanced feature demos."""
    print("\n" + "=" * 60)
    print("Cortex Orchestration SDK - Advanced Features")
    print("=" * 60)

    await demo_prompt_caching()
    await demo_retry_logic()
    await demo_rate_limiting()
    await demo_context_injection()
    await demo_conversation_debugging()
    await demo_token_tracking()
    await demo_event_suppression()

    print("\n" + "=" * 60)
    print("All advanced feature demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
