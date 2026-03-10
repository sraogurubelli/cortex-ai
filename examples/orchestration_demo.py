"""
Orchestration SDK Demo

Demonstrates the core features of the Cortex Orchestration SDK:
- Creating agents with tools
- Running agents (non-streaming and streaming)
- Token usage tracking
- Context injection
"""

import asyncio
from typing import Optional

from langchain_core.tools import tool
from pydantic import Field

from cortex.orchestration import (
    Agent,
    AgentConfig,
    ModelConfig,
    ToolRegistry,
    build_agent,
)


# =========================================================================
# Example Tools
# =========================================================================


@tool
def calculator(operation: str, a: float, b: float) -> str:
    """Perform basic arithmetic operations.

    Args:
        operation: The operation to perform (add, subtract, multiply, divide)
        a: First number
        b: Second number

    Returns:
        The result of the operation
    """
    operations = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "Error: Division by zero",
    }

    if operation not in operations:
        return f"Error: Unknown operation '{operation}'. Supported: {list(operations.keys())}"

    result = operations[operation](a, b)
    return str(result)


@tool
def get_user_info(user_id: str = Field(..., description="The user ID")) -> str:
    """Get information about a user.

    This tool demonstrates context injection - user_id can be injected
    from the agent's context instead of being provided by the LLM.

    Args:
        user_id: The user ID to look up

    Returns:
        User information
    """
    # In a real application, this would query a database
    users = {
        "user123": {"name": "Alice", "email": "alice@example.com", "role": "admin"},
        "user456": {"name": "Bob", "email": "bob@example.com", "role": "user"},
    }

    user = users.get(user_id, {"error": f"User {user_id} not found"})
    return str(user)


# =========================================================================
# Demo 1: Basic Agent Usage (High-level API)
# =========================================================================


async def demo_basic_agent():
    """Demonstrate basic agent usage with the high-level Agent class."""
    print("\n" + "=" * 60)
    print("Demo 1: Basic Agent Usage")
    print("=" * 60)

    # Create agent with tools
    agent = Agent(
        name="math_assistant",
        system_prompt="You are a helpful math assistant. Use tools to perform calculations.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[calculator],
    )

    # Run a simple query
    result = await agent.run("What is 15 multiplied by 7?")

    print(f"\nUser: What is 15 multiplied by 7?")
    print(f"Assistant: {result.response}")
    print(f"\nToken Usage: {result.token_usage}")


# =========================================================================
# Demo 2: Agent with Context Injection
# =========================================================================


async def demo_context_injection():
    """Demonstrate context injection for tools."""
    print("\n" + "=" * 60)
    print("Demo 2: Context Injection")
    print("=" * 60)

    # Create tool registry and register tools
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_user_info)

    # Set context that will be injected into tools
    # The user_id will be automatically injected into get_user_info tool
    registry.set_context(user_id="user123")

    # Create agent with registry
    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant with access to user information.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tool_registry=registry,
        tools=None,  # Use all tools from registry
    )

    # The LLM doesn't need to provide user_id - it's injected from context
    result = await agent.run("Can you get my user information?")

    print(f"\nUser: Can you get my user information?")
    print(f"Assistant: {result.response}")
    print(f"\nContext injected: user_id=user123")


# =========================================================================
# Demo 3: Streaming Agent
# =========================================================================


class SimpleStreamWriter:
    """Simple stream writer for demo purposes."""

    async def write_event(self, event_type: str, data) -> None:
        """Write an event to the stream."""
        print(f"[{event_type}] {data}")

    async def close(self) -> None:
        """Close the stream."""
        print("[Stream closed]")


async def demo_streaming():
    """Demonstrate streaming with the agent."""
    print("\n" + "=" * 60)
    print("Demo 3: Streaming Agent")
    print("=" * 60)

    agent = Agent(
        name="math_assistant",
        system_prompt="You are a helpful math assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[calculator],
    )

    writer = SimpleStreamWriter()

    print("\nUser: Calculate (10 + 5) * 3")
    print("\nStreaming response:")

    result = await agent.stream_to_writer(
        "Calculate (10 + 5) * 3",
        stream_writer=writer,
    )

    print(f"\nFinal response: {result.response}")
    print(f"Token usage: {result.token_usage}")


# =========================================================================
# Demo 4: Low-level API (AgentConfig + build_agent)
# =========================================================================


async def demo_low_level_api():
    """Demonstrate the low-level API for more control."""
    print("\n" + "=" * 60)
    print("Demo 4: Low-level API (AgentConfig + build_agent)")
    print("=" * 60)

    # Create tool registry
    registry = ToolRegistry()
    registry.register(calculator)

    # Create agent config
    config = AgentConfig(
        name="calculator",
        description="A calculator agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        system_prompt="You are a calculator. Use the calculator tool for all operations.",
        tools=["calculator"],  # Reference by name
    )

    # Build agent
    compiled_agent = build_agent(config, tool_registry=registry)

    # Run agent directly
    from langchain_core.messages import HumanMessage

    result = await compiled_agent.ainvoke(
        {"messages": [HumanMessage(content="What is 100 divided by 4?")]},
        config={"recursion_limit": 50, "configurable": {"thread_id": "demo"}},
    )

    messages = result.get("messages", [])
    final_message = messages[-1] if messages else None

    print(f"\nUser: What is 100 divided by 4?")
    print(f"Assistant: {final_message.content if final_message else 'No response'}")


# =========================================================================
# Demo 5: Multi-turn Conversation
# =========================================================================


async def demo_multi_turn():
    """Demonstrate multi-turn conversation with context."""
    print("\n" + "=" * 60)
    print("Demo 5: Multi-turn Conversation")
    print("=" * 60)

    agent = Agent(
        name="math_tutor",
        system_prompt="You are a friendly math tutor. Help students with calculations.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[calculator],
    )

    # First turn
    result1 = await agent.run("What is 25 + 17?", thread_id="student-session-1")
    print(f"\nTurn 1:")
    print(f"Student: What is 25 + 17?")
    print(f"Tutor: {result1.response}")

    # Second turn (same thread)
    result2 = await agent.run(
        "And if I multiply that by 2?",
        thread_id="student-session-1",
    )
    print(f"\nTurn 2:")
    print(f"Student: And if I multiply that by 2?")
    print(f"Tutor: {result2.response}")
    print(f"\nTotal tokens (turn 2): {result2.token_usage}")


# =========================================================================
# Main
# =========================================================================


async def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("Cortex Orchestration SDK - Examples")
    print("=" * 60)

    # Run demos
    await demo_basic_agent()
    await demo_context_injection()
    await demo_streaming()
    await demo_low_level_api()
    await demo_multi_turn()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
