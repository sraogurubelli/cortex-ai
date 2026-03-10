"""
Unified Agent Demo for Cortex-AI

Demonstrates:
- UnifiedAgent with tool calling
- Custom tool implementation
- Multi-turn conversations with tools
- Strategic planning for complex tasks
"""

import asyncio
import os
import json
from typing import Any, Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from cortex.core import LLMProviderFactory
from cortex.core.agents import UnifiedAgent, BaseTool


# Example Tool: Calculator
class CalculatorTool(BaseTool):
    """Simple calculator tool for mathematical operations."""

    def __init__(self):
        super().__init__(
            name="calculator",
            description="Perform mathematical calculations. Supports basic operations: add, subtract, multiply, divide."
        )

    async def execute(self, operation: str, a: float, b: float) -> Dict[str, Any]:
        """Execute a calculation."""
        operations = {
            "add": lambda x, y: x + y,
            "subtract": lambda x, y: x - y,
            "multiply": lambda x, y: x * y,
            "divide": lambda x, y: x / y if y != 0 else "Error: Division by zero",
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        result = operations[operation](a, b)
        return {
            "operation": operation,
            "operands": [a, b],
            "result": result,
        }

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for the calculator tool."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "The mathematical operation to perform",
                    },
                    "a": {
                        "type": "number",
                        "description": "First operand",
                    },
                    "b": {
                        "type": "number",
                        "description": "Second operand",
                    },
                },
                "required": ["operation", "a", "b"],
            },
        }


# Example Tool: Weather (simulated)
class WeatherTool(BaseTool):
    """Simulated weather tool."""

    def __init__(self):
        super().__init__(
            name="get_weather",
            description="Get current weather for a location (simulated data)"
        )

    async def execute(self, location: str) -> Dict[str, Any]:
        """Get weather for a location (simulated)."""
        # Simulated weather data
        weather_data = {
            "San Francisco": {"temp": 65, "condition": "Partly Cloudy", "humidity": 75},
            "New York": {"temp": 72, "condition": "Sunny", "humidity": 60},
            "London": {"temp": 55, "condition": "Rainy", "humidity": 85},
            "Tokyo": {"temp": 70, "condition": "Clear", "humidity": 65},
        }

        if location in weather_data:
            return {
                "location": location,
                **weather_data[location]
            }
        else:
            return {
                "location": location,
                "temp": 68,
                "condition": "Unknown",
                "humidity": 70,
                "note": "Using default values for unknown location"
            }

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for the weather tool."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name to get weather for",
                    },
                },
                "required": ["location"],
            },
        }


# Example Tool: Search (simulated)
class SearchTool(BaseTool):
    """Simulated search tool."""

    def __init__(self):
        super().__init__(
            name="search",
            description="Search for information (simulated)"
        )

    async def execute(self, query: str) -> Dict[str, Any]:
        """Search for information (simulated)."""
        # Simulated search results
        results = {
            "AI": "Artificial Intelligence is the simulation of human intelligence by machines.",
            "Python": "Python is a high-level, interpreted programming language.",
            "FastAPI": "FastAPI is a modern, fast web framework for building APIs with Python.",
            "Machine Learning": "Machine Learning is a subset of AI that enables systems to learn from data.",
        }

        # Find matching result
        for key, value in results.items():
            if key.lower() in query.lower():
                return {
                    "query": query,
                    "result": value,
                    "source": "Knowledge Base"
                }

        return {
            "query": query,
            "result": "No specific information found for this query.",
            "source": "Default"
        }

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for the search tool."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        }


async def basic_tool_calling_demo():
    """Demonstrate basic tool calling with UnifiedAgent."""
    print("🤖 Cortex-AI Unified Agent - Basic Tool Calling Demo\n")
    print("="*60)

    # Create LLM client
    llm_client = LLMProviderFactory.create(
        provider="anthropic",
        model="claude-sonnet-4",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    # Create tools
    tools = [
        CalculatorTool(),
        WeatherTool(),
    ]

    # Create unified agent
    agent = UnifiedAgent(
        llm_client=llm_client,
        tools=tools,
        agent_name="demo-agent",
    )

    # Test queries that require tools
    test_queries = [
        "What is 15 multiplied by 7?",
        "What's the weather like in San Francisco?",
        "Calculate 100 divided by 4, then tell me the weather in New York.",
    ]

    for query in test_queries:
        print(f"\n👤 User: {query}")
        print("-"*60)

        response = await agent.run(query)

        print(f"🤖 Agent: {response}")
        print("="*60)

    await agent.close()


async def multi_turn_conversation_demo():
    """Demonstrate multi-turn conversation with context."""
    print("\n\n🌊 Cortex-AI Unified Agent - Multi-Turn Conversation Demo\n")
    print("="*60)

    # Create LLM client
    llm_client = LLMProviderFactory.create(
        provider="anthropic",
        model="claude-sonnet-4",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    # Create tools
    tools = [
        CalculatorTool(),
        SearchTool(),
    ]

    # Create unified agent
    agent = UnifiedAgent(
        llm_client=llm_client,
        tools=tools,
        agent_name="conversation-agent",
    )

    # Simulate a multi-turn conversation
    conversation = [
        "Search for information about AI",
        "Now calculate 25 + 17",
        "What did you just tell me about AI? Be brief.",
    ]

    for turn, query in enumerate(conversation, 1):
        print(f"\n[Turn {turn}] 👤 User: {query}")
        print("-"*60)

        response = await agent.run(query)

        print(f"[Turn {turn}] 🤖 Agent: {response}")
        print("="*60)

    # Show conversation history
    print("\n📜 Conversation History:")
    history = agent.get_conversation_history()
    for i, msg in enumerate(history, 1):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            content_preview = content[:100] + "..." if len(content) > 100 else content
            print(f"  {i}. [{role.upper()}]: {content_preview}")

    await agent.close()


async def complex_task_demo():
    """Demonstrate complex task handling with strategic planning."""
    print("\n\n🧠 Cortex-AI Unified Agent - Complex Task Demo\n")
    print("="*60)

    # Create LLM client
    llm_client = LLMProviderFactory.create(
        provider="anthropic",
        model="claude-sonnet-4",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    # Create tools
    tools = [
        CalculatorTool(),
        WeatherTool(),
        SearchTool(),
    ]

    # Create unified agent
    agent = UnifiedAgent(
        llm_client=llm_client,
        tools=tools,
        agent_name="complex-agent",
        additional_context="You are helping with travel planning and calculations.",
    )

    # Complex multi-step query
    query = (
        "I'm planning a trip to Tokyo. First, tell me what the weather is like there. "
        "Then, if I have a budget of $2000 and daily expenses are $150, "
        "calculate how many days I can stay."
    )

    print(f"👤 User: {query}\n")
    print("-"*60)

    response = await agent.run(query)

    print(f"\n🤖 Agent: {response}")
    print("="*60)

    await agent.close()


async def dynamic_tool_management_demo():
    """Demonstrate adding/removing tools dynamically."""
    print("\n\n🔧 Cortex-AI Unified Agent - Dynamic Tool Management Demo\n")
    print("="*60)

    # Create LLM client
    llm_client = LLMProviderFactory.create(
        provider="anthropic",
        model="claude-sonnet-4",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    # Create agent with just calculator
    agent = UnifiedAgent(
        llm_client=llm_client,
        tools=[CalculatorTool()],
        agent_name="dynamic-agent",
    )

    print(f"📋 Initial tools: {agent.list_tools()}\n")

    # Try using calculator
    print("👤 User: What is 20 plus 30?")
    response = await agent.run("What is 20 plus 30?")
    print(f"🤖 Agent: {response}\n")

    # Add weather tool
    print("🔧 Adding weather tool...")
    await agent.add_tool(WeatherTool())
    print(f"📋 Updated tools: {agent.list_tools()}\n")

    # Now try using weather
    print("👤 User: What's the weather in London?")
    response = await agent.run("What's the weather in London?")
    print(f"🤖 Agent: {response}\n")

    await agent.close()


async def main():
    """Run all demos."""
    # Demo 1: Basic tool calling
    await basic_tool_calling_demo()

    # Demo 2: Multi-turn conversation
    await multi_turn_conversation_demo()

    # Demo 3: Complex task
    await complex_task_demo()

    # Demo 4: Dynamic tool management
    await dynamic_tool_management_demo()


if __name__ == "__main__":
    asyncio.run(main())
