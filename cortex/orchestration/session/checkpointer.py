"""
Checkpointer for Cortex Agent Sessions.

Provides checkpoint-based persistence for LangGraph agents using either
PostgreSQL (AsyncPostgresSaver) or in-memory storage (MemorySaver).

Configuration is driven by environment variables:
    CORTEX_DATABASE_URL          - PostgreSQL connection string
    CORTEX_CHECKPOINT_ENABLED    - Explicit on/off switch (default: auto-detect)
    CORTEX_CHECKPOINT_USE_MEMORY - Use MemorySaver instead of PostgreSQL

Lifecycle:
    1. Call open_checkpointer_pool() at application startup
    2. Use get_checkpointer() to get the checkpointer for agents
    3. Call close_checkpointer_pool() at shutdown

Example:
    # Startup
    await open_checkpointer_pool(
        database_url="postgresql://user:pass@localhost/cortex"
    )

    # In request handler
    checkpointer = get_checkpointer()
    agent = Agent(name="assistant", checkpointer=checkpointer)
    result = await agent.run("Hello", thread_id="session-123")

    # Shutdown
    await close_checkpointer_pool()
"""

import asyncio
import logging
import os
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

# PostgreSQL connection string
CORTEX_DATABASE_URL = os.getenv("CORTEX_DATABASE_URL", "")

# Use in-memory saver instead of PostgreSQL (for local development)
CORTEX_CHECKPOINT_USE_MEMORY = (
    os.getenv("CORTEX_CHECKPOINT_USE_MEMORY", "").lower() == "true"
)


def is_checkpointing_enabled() -> bool:
    """
    Check whether checkpointing is enabled.

    Checkpointing is auto-enabled when CORTEX_DATABASE_URL is set.
    The CORTEX_CHECKPOINT_ENABLED env var can force the feature on or off.

    Returns:
        bool: True if checkpointing is enabled

    Example:
        >>> os.environ["CORTEX_DATABASE_URL"] = "postgresql://..."
        >>> is_checkpointing_enabled()
        True
    """
    explicit = os.getenv("CORTEX_CHECKPOINT_ENABLED", "").lower()
    if explicit == "true":
        return True
    if explicit == "false":
        return False
    # Auto-enable if database URL is set
    return bool(CORTEX_DATABASE_URL)


# ---------------------------------------------------------------------------
# Module-level singleton pool + checkpointer
# ---------------------------------------------------------------------------

_pool: Any | None = None  # AsyncConnectionPool
_checkpointer: BaseCheckpointSaver | None = None


async def open_checkpointer_pool(
    database_url: str | None = None,
    use_memory: bool | None = None,
) -> None:
    """
    Open the shared connection pool and create the checkpoint saver.

    This must be called **once** at application startup (e.g. in FastAPI
    lifespan). It is a no-op if checkpointing is disabled or already initialized.

    For PostgreSQL mode, this also runs checkpointer.setup() to create/migrate
    the checkpoint tables (idempotent).

    Args:
        database_url: PostgreSQL connection string (overrides env var)
        use_memory: Force in-memory saver (overrides env var)

    Example:
        # Startup - PostgreSQL mode
        await open_checkpointer_pool(
            database_url="postgresql://user:pass@localhost/cortex"
        )

        # Startup - In-memory mode (development)
        await open_checkpointer_pool(use_memory=True)
    """
    global _pool, _checkpointer

    if not is_checkpointing_enabled():
        logger.info("Checkpointing is disabled - skipping pool creation")
        return

    if _checkpointer is not None:
        logger.debug("Checkpointer already initialized - skipping")
        return

    # Determine mode
    use_memory_saver = (
        use_memory if use_memory is not None else CORTEX_CHECKPOINT_USE_MEMORY
    )

    # ----- In-memory saver (local dev) -----
    if use_memory_saver:
        logger.info("Using in-memory checkpoint saver (development mode)")
        _checkpointer = MemorySaver()
        return

    # ----- PostgreSQL saver (production) -----
    db_url = database_url or CORTEX_DATABASE_URL
    if not db_url:
        logger.error(
            "CORTEX_CHECKPOINT_ENABLED is true but CORTEX_DATABASE_URL is not set - "
            "cannot create checkpointer pool"
        )
        return

    logger.info("Opening checkpoint connection pool (PostgreSQL mode)")

    try:
        # Import PostgreSQL dependencies (optional)
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg_pool import AsyncConnectionPool
        except ImportError as e:
            logger.error(
                f"PostgreSQL dependencies not installed: {e}. "
                "Install with: pip install langgraph-checkpoint-postgres psycopg[pool]"
            )
            return

        # Create connection pool
        _pool = AsyncConnectionPool(
            conninfo=db_url,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        await _pool.open()

        # Create checkpointer
        _checkpointer = AsyncPostgresSaver(conn=_pool)

        # Create/migrate tables (idempotent)
        await _checkpointer.setup()

        logger.info("Checkpoint pool and tables ready")

    except Exception as e:
        logger.error(
            f"Failed to connect to checkpoint database: {e}. "
            "Continuing without checkpointing.",
            exc_info=True,
        )
        _checkpointer = None
        if _pool is not None:
            try:
                await _pool.close()
            except Exception:
                pass
            _pool = None


async def close_checkpointer_pool() -> None:
    """
    Close the shared connection pool.

    Call this at application shutdown (e.g. after the yield in FastAPI lifespan).
    Safe to call even if the pool was never opened.

    Example:
        # FastAPI lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await open_checkpointer_pool()
            yield
            await close_checkpointer_pool()
    """
    global _pool, _checkpointer

    _checkpointer = None

    if _pool is not None:
        logger.info("Closing checkpoint connection pool")
        await _pool.close()
        _pool = None


def get_checkpointer() -> BaseCheckpointSaver | None:
    """
    Return the singleton checkpoint saver.

    Returns None if checkpointing is disabled or not yet initialized.

    This is the function to call on every request to get the checkpointer
    for use with Agent.

    Returns:
        BaseCheckpointSaver | None: Checkpointer instance or None

    Example:
        checkpointer = get_checkpointer()
        if checkpointer:
            agent = Agent(name="assistant", checkpointer=checkpointer)
        else:
            # No persistence - use ephemeral MemorySaver
            agent = Agent(name="assistant")
    """
    return _checkpointer


async def is_checkpointer_healthy() -> bool:
    """
    Verify the checkpointer's database connection is alive.

    - MemorySaver: Always returns True (no I/O)
    - AsyncPostgresSaver: Executes SELECT 1 with 2-second timeout

    Use this before compiling agents to detect database issues early
    and fall back gracefully.

    Returns:
        bool: True if checkpointer is healthy, False otherwise

    Example:
        if not await is_checkpointer_healthy():
            logger.warning("Checkpointer unhealthy - using ephemeral state")
            checkpointer = None
        else:
            checkpointer = get_checkpointer()
    """
    if _checkpointer is None:
        return False

    # MemorySaver is always healthy (no I/O)
    if isinstance(_checkpointer, MemorySaver):
        return True

    # PostgreSQL health check
    if _pool is None:
        return False

    try:

        async def _ping():
            async with _pool.connection() as conn:
                await conn.execute("SELECT 1")

        await asyncio.wait_for(_ping(), timeout=2.0)
        return True

    except Exception as e:
        logger.error(
            f"Checkpointer DB health check failed: {e}. "
            "Requests will fall back to ephemeral state.",
            exc_info=True,
        )
        return False


async def has_existing_checkpoint(thread_id: str) -> bool:
    """
    Check whether a checkpoint already exists for the given thread_id.

    Use this to decide whether to pass only the new user message (checkpoint
    has history) or the full conversation history (first turn / no checkpoint).

    Args:
        thread_id: Thread identifier to check

    Returns:
        bool: True if checkpoint exists, False otherwise (including when
              checkpointing is disabled)

    Example:
        thread_id = "session-123"

        if await has_existing_checkpoint(thread_id):
            # Checkpoint exists - only send new message
            result = await agent.run(new_message, thread_id=thread_id)
        else:
            # First turn - send full context
            result = await agent.run(
                new_message,
                messages=context_messages,
                thread_id=thread_id,
            )
    """
    if _checkpointer is None:
        return False

    try:
        config = {"configurable": {"thread_id": thread_id}}
        existing = await _checkpointer.aget_tuple(config)
        return existing is not None
    except Exception as e:
        logger.warning(f"Failed to look up checkpoint for {thread_id}: {e}")
        return False


def build_thread_id(agent_name: str, conversation_id: str) -> str:
    """
    Build a composite thread_id for checkpoint storage.

    Format: <agent_name>:<conversation_id>

    This allows multiple agents to share the same conversation_id space
    without collisions.

    Args:
        agent_name: Name of the agent (e.g. "assistant", "researcher")
        conversation_id: Unique conversation identifier (e.g. "user-123-session-1")

    Returns:
        str: Composite thread identifier

    Example:
        >>> build_thread_id("assistant", "session-123")
        'assistant:session-123'

        # Use with Agent
        thread_id = build_thread_id("assistant", user_session_id)
        result = await agent.run("Hello", thread_id=thread_id)
    """
    return f"{agent_name}:{conversation_id}"


async def cleanup_old_checkpoints(days: int = 30) -> int:
    """
    Delete checkpoints older than the specified number of days.

    This is a maintenance operation to prevent unbounded growth of checkpoint
    data. Call this periodically (e.g. daily cron job) to clean up old sessions.

    Args:
        days: Delete checkpoints older than this many days (default: 30)

    Returns:
        int: Number of checkpoints deleted, or 0 if operation failed

    Example:
        # Daily cleanup job
        deleted = await cleanup_old_checkpoints(days=30)
        logger.info(f"Deleted {deleted} old checkpoints")
    """
    if _checkpointer is None:
        logger.warning("Checkpointer not initialized - cannot clean up")
        return 0

    if isinstance(_checkpointer, MemorySaver):
        logger.debug("MemorySaver does not persist - skipping cleanup")
        return 0

    if _pool is None:
        logger.warning("Connection pool not available - cannot clean up")
        return 0

    try:
        # Execute cleanup query
        async with _pool.connection() as conn:
            result = await conn.execute(
                """
                DELETE FROM checkpoints
                WHERE created_at < NOW() - INTERVAL '%s days'
                RETURNING thread_id
                """,
                (days,),
            )
            deleted_count = result.rowcount if hasattr(result, "rowcount") else 0

        logger.info(f"Deleted {deleted_count} checkpoints older than {days} days")
        return deleted_count

    except Exception as e:
        logger.error(f"Failed to cleanup old checkpoints: {e}", exc_info=True)
        return 0
