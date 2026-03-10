"""
Session Persistence for Cortex Orchestration.

Provides checkpoint-based persistence for LangGraph agents, enabling
multi-turn conversations that persist across process restarts and requests.

Features:
- PostgreSQL-backed state persistence (AsyncPostgresSaver)
- In-memory fallback for development (MemorySaver)
- Automatic checkpoint health checks
- Thread ID management
- Connection pooling

Usage:
    # Initialize at application startup
    from cortex.orchestration.session import open_checkpointer_pool
    await open_checkpointer_pool(database_url="postgresql://...")

    # Get checkpointer for use with Agent
    from cortex.orchestration.session import get_checkpointer
    checkpointer = get_checkpointer()

    agent = Agent(
        name="assistant",
        model=ModelConfig(model="gpt-4o"),
        checkpointer=checkpointer,  # Enable persistence
    )

    # Conversations persist across requests
    result1 = await agent.run("What is Python?", thread_id="session-123")
    result2 = await agent.run("Tell me more", thread_id="session-123")

    # Shutdown at application exit
    from cortex.orchestration.session import close_checkpointer_pool
    await close_checkpointer_pool()

Environment Variables:
    CORTEX_DATABASE_URL: PostgreSQL connection string
    CORTEX_CHECKPOINT_ENABLED: Force enable/disable checkpointing (true/false)
    CORTEX_CHECKPOINT_USE_MEMORY: Use in-memory saver instead of PostgreSQL
"""

from cortex.orchestration.session.checkpointer import (
    build_thread_id,
    close_checkpointer_pool,
    get_checkpointer,
    has_existing_checkpoint,
    is_checkpointer_healthy,
    is_checkpointing_enabled,
    open_checkpointer_pool,
)

__all__ = [
    "open_checkpointer_pool",
    "close_checkpointer_pool",
    "get_checkpointer",
    "is_checkpointer_healthy",
    "is_checkpointing_enabled",
    "has_existing_checkpoint",
    "build_thread_id",
]
