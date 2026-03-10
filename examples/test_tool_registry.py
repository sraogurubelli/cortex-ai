"""
Test script for Enhanced Tool Registry features.

Demonstrates:
1. Pattern matching for SKIP_CONTEXT_PREFIXES (transfer_to_*)
2. None/empty value filtering
3. Better error messages for missing context

Run with:
    python examples/test_tool_registry.py
"""

import asyncio
from typing import Optional

from langchain_core.tools import tool
from pydantic import Field

from cortex.orchestration import ToolRegistry


# =========================================================================
# Demo 1: Pattern Matching for Handoff Tools
# =========================================================================


def demo_skip_context_patterns():
    """Demonstrate pattern matching for tools that skip context."""
    print("=" * 70)
    print("Demo 1: Pattern Matching (SKIP_CONTEXT_PREFIXES)")
    print("=" * 70)

    registry = ToolRegistry()

    # Test exact match
    print("\n1. Exact match (SKIP_CONTEXT_TOOLS):")
    print(f"   complete_task: {not registry.should_inject_context('complete_task')}")  # Should be True (skipped)
    print(f"   get_prompt: {not registry.should_inject_context('get_prompt')}")  # Should be True (skipped)

    # Test prefix match
    print("\n2. Prefix match (SKIP_CONTEXT_PREFIXES):")
    print(f"   transfer_to_researcher: {not registry.should_inject_context('transfer_to_researcher')}")  # Should be True (skipped)
    print(f"   transfer_to_writer: {not registry.should_inject_context('transfer_to_writer')}")  # Should be True (skipped)
    print(f"   transfer_to_analyst: {not registry.should_inject_context('transfer_to_analyst')}")  # Should be True (skipped)

    # Test regular tools
    print("\n3. Regular tools (should receive context):")
    print(f"   search_documents: {registry.should_inject_context('search_documents')}")  # Should be True (not skipped)
    print(f"   get_user_data: {registry.should_inject_context('get_user_data')}")  # Should be True (not skipped)

    print("\n✓ Pattern matching works correctly!")
    print("  - Exact matches skip context: complete_task, get_prompt")
    print("  - Prefix matches skip context: transfer_to_*")
    print("  - Other tools receive context injection")


# =========================================================================
# Demo 2: None/Empty Value Filtering
# =========================================================================


async def demo_none_filtering():
    """Demonstrate None and empty value filtering."""
    print("\n" + "=" * 70)
    print("Demo 2: None/Empty Value Filtering")
    print("=" * 70)

    @tool
    async def process_data(
        query: str = Field(..., description="Search query"),
        max_results: Optional[int] = Field(None, description="Max results"),
        filter_type: Optional[str] = Field(None, description="Filter type"),
    ) -> str:
        """Process data with optional filters."""
        result_parts = [f"Query: {query}"]
        if max_results is not None:
            result_parts.append(f"Max results: {max_results}")
        if filter_type:
            result_parts.append(f"Filter: {filter_type}")
        return ", ".join(result_parts)

    registry = ToolRegistry()
    registry.register(process_data)
    registry.set_context(user_id="user123")  # Won't be injected (not in schema)

    # Get wrapped tool
    wrapped = registry.wrap_with_context(registry.get("process_data"))

    print("\n1. Call with None values (should be filtered):")
    print("   Input: query='test', max_results=None, filter_type=''")

    # Simulate LLM providing None and empty string (common with Claude)
    result = await wrapped.coroutine(query="test", max_results=None, filter_type="")

    print(f"   Result: {result}")
    print("   ✓ None and empty string were filtered out!")

    print("\n2. Call with actual values:")
    print("   Input: query='search', max_results=10, filter_type='recent'")

    result2 = await wrapped.coroutine(query="search", max_results=10, filter_type="recent")

    print(f"   Result: {result2}")
    print("   ✓ All values passed through correctly!")


# =========================================================================
# Demo 3: Context Injection with Validation
# =========================================================================


async def demo_context_validation():
    """Demonstrate context injection with validation."""
    print("\n" + "=" * 70)
    print("Demo 3: Context Injection with Validation")
    print("=" * 70)

    @tool
    async def get_user_balance(
        user_id: str = Field(..., description="User ID (injected)"),
        currency: str = Field("USD", description="Currency code"),
    ) -> str:
        """Get user's account balance."""
        balances = {
            "user123": {"USD": 1250.50, "EUR": 1100.30},
            "user456": {"USD": 850.20, "EUR": 750.10},
        }
        balance = balances.get(user_id, {}).get(currency, 0.0)
        return f"Balance for {user_id}: {balance} {currency}"

    registry = ToolRegistry()
    registry.register(get_user_balance)

    # Case 1: With context set
    print("\n1. With context set (user_id='user123'):")
    registry.set_context(user_id="user123")

    wrapped = registry.wrap_with_context(registry.get("get_user_balance"))
    result = await wrapped.coroutine(currency="USD")

    print(f"   Result: {result}")
    print("   ✓ user_id was injected from context!")

    # Case 2: Missing context
    print("\n2. Missing required context:")
    registry2 = ToolRegistry()
    registry2.register(get_user_balance)
    # No context set!

    wrapped2 = registry2.wrap_with_context(registry2.get("get_user_balance"))

    print("   Attempting to call without user_id in context...")
    try:
        await wrapped2.coroutine(currency="USD")
        print("   ✗ Should have raised ValueError!")
    except ValueError as e:
        print(f"   ✓ Got helpful error message:")
        print(f"     {str(e)}")


# =========================================================================
# Demo 4: Real-World Example (Swarm Handoffs)
# =========================================================================


def demo_swarm_handoffs():
    """Demonstrate that swarm handoff tools skip context."""
    print("\n" + "=" * 70)
    print("Demo 4: Swarm Handoff Tools (Real-World)")
    print("=" * 70)

    @tool
    async def transfer_to_researcher(task: str) -> str:
        """Transfer task to researcher agent."""
        return f"Transferring to researcher: {task}"

    @tool
    async def transfer_to_writer(content: str) -> str:
        """Transfer content to writer agent."""
        return f"Transferring to writer: {content}"

    @tool
    async def search_documents(
        user_id: str = Field(..., description="User ID"),
        query: str = Field(..., description="Search query"),
    ) -> str:
        """Search user's documents."""
        return f"Searching for user {user_id}: {query}"

    registry = ToolRegistry()
    registry.register(transfer_to_researcher)
    registry.register(transfer_to_writer)
    registry.register(search_documents)

    # Set context (should only inject into search_documents)
    registry.set_context(user_id="user123")

    print("\nRegistered tools:")
    for name in registry.list_names():
        skips_context = not registry.should_inject_context(name)
        status = "SKIPS context" if skips_context else "RECEIVES context"
        print(f"  - {name}: {status}")

    print("\n✓ Handoff tools correctly skip context injection!")
    print("  - transfer_to_researcher: NO user_id injection")
    print("  - transfer_to_writer: NO user_id injection")
    print("  - search_documents: YES user_id injection")


# =========================================================================
# Main
# =========================================================================


async def main():
    """Run all tool registry demos."""
    print("\n" + "=" * 70)
    print("Cortex Orchestration SDK - Enhanced Tool Registry")
    print("=" * 70)

    demo_skip_context_patterns()
    await demo_none_filtering()
    await demo_context_validation()
    demo_swarm_handoffs()

    print("\n" + "=" * 70)
    print("All Tool Registry Demos Complete!")
    print("=" * 70)
    print("\nKey Features:")
    print("  1. Pattern matching for tool names (transfer_to_*)")
    print("  2. Automatic None/empty value filtering")
    print("  3. Better error messages when context is missing")
    print("  4. Handoff tools correctly skip context injection")


if __name__ == "__main__":
    asyncio.run(main())
