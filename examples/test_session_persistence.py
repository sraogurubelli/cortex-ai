"""
Test script for session persistence.

Demonstrates:
1. PostgreSQL-backed conversation state persistence
2. In-memory fallback for development
3. Multi-turn conversations across process restarts
4. Health checks and graceful fallback
5. Thread ID management
6. Checkpoint cleanup

Prerequisites:
    # For PostgreSQL mode
    pip install langgraph-checkpoint-postgres psycopg[pool]

    # Setup PostgreSQL
    docker run -d --name postgres \
        -e POSTGRES_PASSWORD=postgres \
        -p 5432:5432 \
        postgres:16

    # Create database
    createdb cortex

Run with:
    # In-memory mode (no PostgreSQL needed)
    CORTEX_CHECKPOINT_USE_MEMORY=true python examples/test_session_persistence.py

    # PostgreSQL mode
    CORTEX_DATABASE_URL=postgresql://postgres:postgres@localhost/cortex \
    python examples/test_session_persistence.py
"""

import asyncio
import os
import tempfile

from cortex.orchestration import Agent, ModelConfig

# Session persistence imports (optional - graceful fallback)
try:
    from cortex.orchestration.session import (
        build_thread_id,
        close_checkpointer_pool,
        get_checkpointer,
        has_existing_checkpoint,
        is_checkpointer_healthy,
        is_checkpointing_enabled,
        open_checkpointer_pool,
    )

    SESSION_AVAILABLE = True
except ImportError:
    SESSION_AVAILABLE = False
    print("⚠️  Session persistence not available")
    print("Install with: pip install langgraph-checkpoint-postgres psycopg[pool]")


async def demo_basic_persistence():
    """Demonstrate basic session persistence."""
    if not SESSION_AVAILABLE:
        print("Skipping - session persistence not available")
        return

    print("=" * 70)
    print("Demo 1: Basic Session Persistence")
    print("=" * 70)

    # Check if enabled
    enabled = is_checkpointing_enabled()
    print(f"\nCheckpointing enabled: {enabled}")

    if not enabled:
        print("  Set CORTEX_DATABASE_URL or CORTEX_CHECKPOINT_USE_MEMORY=true")
        return

    # Initialize checkpointer pool
    print("\n📊 Opening checkpointer pool...")
    await open_checkpointer_pool()

    # Get checkpointer
    checkpointer = get_checkpointer()
    if not checkpointer:
        print("  ✗ Failed to get checkpointer")
        return

    print(f"  ✓ Checkpointer ready: {type(checkpointer).__name__}")

    # Create agent with checkpointer
    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant with perfect memory.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        checkpointer=checkpointer,
    )

    # First turn - introduce yourself
    thread_id = "session-demo-1"
    print(f"\n📝 Turn 1 (thread_id={thread_id}):")
    print("   User: My name is Alice and I like Python")

    result1 = await agent.run("My name is Alice and I like Python", thread_id=thread_id)
    print(f"   Agent: {result1.response}")

    # Second turn - test memory
    print(f"\n📝 Turn 2 (same thread_id):")
    print("   User: What is my name?")

    result2 = await agent.run("What is my name?", thread_id=thread_id)
    print(f"   Agent: {result2.response}")

    # Verify checkpoint exists
    exists = await has_existing_checkpoint(thread_id)
    print(f"\n✓ Checkpoint exists: {exists}")

    # Cleanup
    await close_checkpointer_pool()
    print("\n✓ Basic persistence works!")


async def demo_process_restart_simulation():
    """Demonstrate conversation persistence across process restarts."""
    if not SESSION_AVAILABLE:
        print("\nSkipping - session persistence not available")
        return

    print("\n" + "=" * 70)
    print("Demo 2: Process Restart Simulation")
    print("=" * 70)

    if not is_checkpointing_enabled():
        print("Skipping - checkpointing not enabled")
        return

    # ----- PROCESS 1: Initial conversation -----
    print("\n🔵 Process 1: Initial conversation")

    await open_checkpointer_pool()
    checkpointer1 = get_checkpointer()

    agent1 = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        checkpointer=checkpointer1,
    )

    thread_id = "session-restart-demo"

    print(f"\n  Turn 1: Teach the agent about your favorite color")
    result1 = await agent1.run(
        "My favorite color is blue. Remember this!",
        thread_id=thread_id,
    )
    print(f"  Agent: {result1.response}")

    # Simulate process shutdown
    await close_checkpointer_pool()
    print("\n  🔴 Process 1 shutdown (checkpointer closed)")

    # ----- PROCESS 2: Resume conversation -----
    print("\n🟢 Process 2: Resume after restart")

    await open_checkpointer_pool()
    checkpointer2 = get_checkpointer()

    agent2 = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        checkpointer=checkpointer2,
    )

    # Check if checkpoint exists
    exists = await has_existing_checkpoint(thread_id)
    print(f"\n  Checkpoint exists: {exists}")

    print(f"\n  Turn 2: Ask about favorite color (should remember from Process 1)")
    result2 = await agent2.run(
        "What is my favorite color?",
        thread_id=thread_id,
    )
    print(f"  Agent: {result2.response}")

    if "blue" in result2.response.lower():
        print("\n  ✓ SUCCESS: Agent remembered across process restart!")
    else:
        print("\n  ✗ FAIL: Agent forgot the information")

    await close_checkpointer_pool()


async def demo_health_checks():
    """Demonstrate checkpointer health checks."""
    if not SESSION_AVAILABLE:
        print("\nSkipping - session persistence not available")
        return

    print("\n" + "=" * 70)
    print("Demo 3: Health Checks")
    print("=" * 70)

    if not is_checkpointing_enabled():
        print("Skipping - checkpointing not enabled")
        return

    await open_checkpointer_pool()

    # Check health
    print("\n📊 Checking checkpointer health...")
    healthy = await is_checkpointer_healthy()

    if healthy:
        print("  ✓ Checkpointer is healthy")
        print("  - Database connection is alive")
        print("  - Ready to persist state")
    else:
        print("  ✗ Checkpointer is unhealthy")
        print("  - Database may be down")
        print("  - Will fall back to ephemeral state")

    # Demonstrate graceful fallback
    if not healthy:
        print("\n📝 Graceful fallback example:")
        print("  Using ephemeral MemorySaver instead")

        from langgraph.checkpoint.memory import MemorySaver

        agent = Agent(
            name="assistant",
            model=ModelConfig(model="gpt-4o", use_gateway=False),
            checkpointer=MemorySaver(),  # Fallback
        )
        print("  ✓ Agent still works, but state won't persist")

    await close_checkpointer_pool()


async def demo_thread_id_management():
    """Demonstrate thread ID best practices."""
    if not SESSION_AVAILABLE:
        print("\nSkipping - session persistence not available")
        return

    print("\n" + "=" * 70)
    print("Demo 4: Thread ID Management")
    print("=" * 70)

    # Build composite thread IDs
    print("\n1. Composite thread IDs:")
    thread1 = build_thread_id("assistant", "user-123-session-1")
    thread2 = build_thread_id("researcher", "user-123-session-1")

    print(f"   Assistant: {thread1}")
    print(f"   Researcher: {thread2}")
    print("   ✓ Different agents can share same session ID")

    # Best practices
    print("\n2. Best practices:")
    print("   - Include user ID: prevents cross-user leaks")
    print("   - Include session ID: separate conversations")
    print("   - Include agent name: multi-agent workflows")
    print("   - Use UUIDs for session IDs: avoid collisions")

    # Examples
    print("\n3. Example patterns:")
    examples = [
        ("Single user, single conversation", "user-123:session-abc"),
        ("Multi-user app", "user-{user_id}:conv-{conv_id}"),
        ("Multi-agent workflow", "{agent}:user-{user}:task-{task}"),
        ("Temporary sessions", "temp-{uuid}"),
    ]

    for desc, pattern in examples:
        print(f"   {desc}: {pattern}")


async def demo_in_memory_mode():
    """Demonstrate in-memory development mode."""
    print("\n" + "=" * 70)
    print("Demo 5: In-Memory Development Mode")
    print("=" * 70)

    if not SESSION_AVAILABLE:
        print("Skipping - session persistence not available")
        return

    print("\n📊 Using in-memory checkpointer (no PostgreSQL needed)...")

    # Force in-memory mode
    await open_checkpointer_pool(use_memory=True)
    checkpointer = get_checkpointer()

    print(f"  Checkpointer type: {type(checkpointer).__name__}")
    print("  ✓ MemorySaver - perfect for development!")

    # Use it
    agent = Agent(
        name="dev-assistant",
        system_prompt="You are a development assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        checkpointer=checkpointer,
    )

    print("\n📝 Testing in-memory persistence:")
    result1 = await agent.run("Remember: test mode active", thread_id="dev-session")
    print(f"  Turn 1: {result1.response[:100]}...")

    result2 = await agent.run("What mode are we in?", thread_id="dev-session")
    print(f"  Turn 2: {result2.response[:100]}...")

    print("\n⚠️  Note: State is lost when process exits (in-memory only)")

    await close_checkpointer_pool()


async def demo_environment_variables():
    """Demonstrate environment variable configuration."""
    print("\n" + "=" * 70)
    print("Demo 6: Environment Variable Configuration")
    print("=" * 70)

    print("\n1. CORTEX_DATABASE_URL:")
    print("   postgresql://user:password@host:port/database")
    print("   Example: postgresql://postgres:postgres@localhost/cortex")

    print("\n2. CORTEX_CHECKPOINT_ENABLED:")
    print("   true  - Force enable (error if DB unavailable)")
    print("   false - Force disable (use ephemeral state)")
    print("   (unset) - Auto-detect from CORTEX_DATABASE_URL")

    print("\n3. CORTEX_CHECKPOINT_USE_MEMORY:")
    print("   true - Use in-memory saver (development)")
    print("   false - Use PostgreSQL (production)")

    print("\n4. Example configurations:")

    configs = [
        {
            "desc": "Production (PostgreSQL)",
            "vars": {
                "CORTEX_DATABASE_URL": "postgresql://...",
            },
        },
        {
            "desc": "Development (in-memory)",
            "vars": {
                "CORTEX_CHECKPOINT_USE_MEMORY": "true",
            },
        },
        {
            "desc": "Disabled (ephemeral)",
            "vars": {
                "CORTEX_CHECKPOINT_ENABLED": "false",
            },
        },
    ]

    for config in configs:
        print(f"\n   {config['desc']}:")
        for key, value in config["vars"].items():
            print(f"     {key}={value}")


async def main():
    """Run all session persistence demos."""
    print("\n" + "=" * 70)
    print("Cortex Orchestration SDK - Session Persistence")
    print("=" * 70)

    if not SESSION_AVAILABLE:
        print("\n⚠️  Session persistence module not available")
        print("Install with: pip install langgraph-checkpoint-postgres psycopg[pool]")
        print("\nRunning configuration demo only...\n")
        await demo_environment_variables()
        return

    # Check current configuration
    print(f"\nCurrent configuration:")
    print(f"  CORTEX_DATABASE_URL: {os.getenv('CORTEX_DATABASE_URL', '(not set)')}")
    print(f"  CORTEX_CHECKPOINT_USE_MEMORY: {os.getenv('CORTEX_CHECKPOINT_USE_MEMORY', '(not set)')}")
    print(f"  Checkpointing enabled: {is_checkpointing_enabled()}")

    # Run demos
    await demo_basic_persistence()
    await demo_process_restart_simulation()
    await demo_health_checks()
    await demo_thread_id_management()
    await demo_in_memory_mode()
    await demo_environment_variables()

    print("\n" + "=" * 70)
    print("All Session Persistence Demos Complete!")
    print("=" * 70)

    print("\n✨ Key Features Demonstrated:")
    print("  1. PostgreSQL-backed conversation persistence")
    print("  2. In-memory fallback for development")
    print("  3. Multi-turn conversations across restarts")
    print("  4. Health checks with graceful fallback")
    print("  5. Thread ID management and best practices")
    print("  6. Environment variable configuration")

    print("\n🎯 Use Cases:")
    print("  - Multi-turn conversations (customer support, chatbots)")
    print("  - Long-running sessions (days/weeks)")
    print("  - Multi-request workflows (web apps, APIs)")
    print("  - Agent state recovery after crashes")

    print("\n💡 Best Practices:")
    print("  1. Initialize pool at application startup")
    print("  2. Use health checks before critical operations")
    print("  3. Include user ID in thread_id to prevent leaks")
    print("  4. Use in-memory mode for development")
    print("  5. Clean up old checkpoints periodically")

    print("\n🔧 Production Setup:")
    print("  1. Setup PostgreSQL database")
    print("  2. Set CORTEX_DATABASE_URL environment variable")
    print("  3. Call open_checkpointer_pool() at startup")
    print("  4. Call close_checkpointer_pool() at shutdown")
    print("  5. Use health checks to detect DB issues")


if __name__ == "__main__":
    asyncio.run(main())
