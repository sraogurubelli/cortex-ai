"""
Test script for HTTP request logging.

Demonstrates how to debug LLM provider calls by logging all HTTP requests/responses.
Useful for debugging API issues, tracking latency, or understanding what's being sent.

Run with:
    # Enable via environment variable
    CORTEX_HTTP_DEBUG=1 python examples/test_http_logging.py

    # Or programmatically
    python examples/test_http_logging.py
"""

import asyncio
import logging
import os

from cortex.orchestration import Agent, ModelConfig, enable_http_logging, http_logging_context


async def demo_programmatic_logging():
    """Demonstrate enabling HTTP logging programmatically."""
    print("=" * 70)
    print("Demo 1: Programmatic HTTP Logging")
    print("=" * 70)

    # Enable HTTP logging before making LLM calls
    enable_http_logging(level=logging.INFO)  # INFO shows URLs/status, DEBUG shows bodies

    print("\nHTTP logging enabled. Making LLM call...")
    print("Watch the logs below:\n")

    agent = Agent(
        name="test",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("What is 2 + 2?")

    print(f"\n" + "-" * 70)
    print(f"Response: {result.response}")
    print("-" * 70)

    # Disable logging
    from cortex.orchestration import disable_http_logging

    disable_http_logging()
    print("\nHTTP logging disabled")


async def demo_context_manager():
    """Demonstrate using context manager for scoped logging."""
    print("\n" + "=" * 70)
    print("Demo 2: Context Manager (Scoped Logging)")
    print("=" * 70)

    agent = Agent(
        name="test",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    print("\nBefore context: No HTTP logging")
    # This call won't be logged
    # (commented out to avoid extra API calls)
    # await agent.run("Silent call")

    print("\nInside context: HTTP logging active")
    with http_logging_context(level=logging.INFO):
        # This call WILL be logged
        result = await agent.run("What is Python?")

    print(f"\n" + "-" * 70)
    print(f"Response: {result.response[:100]}...")
    print("-" * 70)

    print("\nAfter context: HTTP logging automatically disabled")


async def demo_detailed_logging():
    """Demonstrate DEBUG level logging with request/response bodies."""
    print("\n" + "=" * 70)
    print("Demo 3: Detailed Logging (DEBUG level)")
    print("=" * 70)

    print("\nEnabling DEBUG level logging (shows request/response bodies)...")

    with http_logging_context(level=logging.DEBUG):
        agent = Agent(
            name="test",
            system_prompt="You are concise.",
            model=ModelConfig(model="gpt-4o", use_gateway=False),
        )

        result = await agent.run("Say hello")

    print(f"\n" + "-" * 70)
    print(f"Response: {result.response}")
    print("-" * 70)


async def demo_file_logging():
    """Demonstrate logging to a file."""
    print("\n" + "=" * 70)
    print("Demo 4: Logging to File")
    print("=" * 70)

    log_file = "/tmp/cortex_http_debug.log"
    print(f"\nLogging HTTP requests to: {log_file}")

    from cortex.orchestration import enable_http_logging, disable_http_logging

    enable_http_logging(
        level=logging.DEBUG, log_to_console=True, log_to_file=log_file
    )

    agent = Agent(
        name="test",
        system_prompt="You are helpful.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("What is AI?")

    disable_http_logging()

    print(f"\n" + "-" * 70)
    print(f"Response: {result.response[:100]}...")
    print("-" * 70)

    # Show file contents
    print(f"\nLog file contents (last 20 lines):")
    with open(log_file) as f:
        lines = f.readlines()
        for line in lines[-20:]:
            print(f"  {line.rstrip()}")


async def main():
    # Check if auto-enabled via environment variable
    if os.environ.get("CORTEX_HTTP_DEBUG"):
        print("=" * 70)
        print("HTTP logging auto-enabled via CORTEX_HTTP_DEBUG environment variable")
        print("=" * 70)

        agent = Agent(
            name="test",
            system_prompt="You are helpful.",
            model=ModelConfig(model="gpt-4o", use_gateway=False),
        )

        print("\nMaking LLM call with auto-enabled logging...\n")
        result = await agent.run("Hello!")

        print(f"\n" + "-" * 70)
        print(f"Response: {result.response}")
        print("-" * 70)

    else:
        # Run all demos
        await demo_programmatic_logging()
        await demo_context_manager()
        await demo_detailed_logging()
        await demo_file_logging()

    print("\n" + "=" * 70)
    print("HTTP Logging Demo Complete!")
    print("=" * 70)
    print("\nKey takeaways:")
    print("  1. Use enable_http_logging() to debug LLM API calls")
    print("  2. Use http_logging_context() for scoped logging")
    print("  3. Set CORTEX_HTTP_DEBUG=1 environment variable for auto-enable")
    print("  4. INFO level shows URLs/status, DEBUG shows bodies")
    print("  5. Automatically redacts Authorization headers for security")


if __name__ == "__main__":
    asyncio.run(main())
