---
paths:
  - "cortex/memory/**/*.py"
  - "tests/memory/**/*.py"
---

# Memory & Checkpointing Rules

**Auto-loads when:** Working with memory middleware or session persistence

---

## Memory Patterns

### Session Persistence (PostgreSQL)

```python
from cortex.memory import PostgresSaver
from cortex.orchestration import Agent, ModelConfig

# ✅ Setup checkpointer
checkpointer = PostgresSaver(
    connection_string="postgresql://user:pass@localhost/cortex"
)

# ✅ Create agent with persistence
agent = Agent(
    name="assistant",
    model=ModelConfig(model="gpt-4o"),
    checkpointer=checkpointer,
)

# ✅ Use consistent thread_id for session
thread_id = f"user-{user_id}-session-{session_id}"
result = await agent.run(message, thread_id=thread_id)

# Conversation history is automatically saved
# Next call with same thread_id restores full context
```

**Rule:** Always use consistent `thread_id` format for session tracking.

---

## Memory Middleware

### Custom Memory Middleware

```python
from cortex.memory import BaseMemoryMiddleware
from typing import Any, Dict

class UserContextMiddleware(BaseMemoryMiddleware):
    """Inject user context into conversations."""

    async def before_run(
        self,
        messages: list[dict],
        thread_id: str,
        metadata: dict,
    ) -> tuple[list[dict], dict]:
        """Called before agent execution.

        Args:
            messages: Conversation messages
            thread_id: Session identifier
            metadata: Additional metadata

        Returns:
            Modified messages and metadata
        """
        # Fetch user preferences
        user_id = metadata.get("user_id")
        if user_id:
            preferences = await self.fetch_user_preferences(user_id)
            metadata["user_preferences"] = preferences

            # Optionally inject system message
            system_msg = {
                "role": "system",
                "content": f"User preferences: {preferences}",
            }
            messages = [system_msg] + messages

        return messages, metadata

    async def after_run(
        self,
        result: Any,
        thread_id: str,
        metadata: dict,
    ) -> Any:
        """Called after agent execution."""
        # Log interaction
        await self.log_interaction(
            thread_id=thread_id,
            query=metadata.get("query"),
            response=result.response,
            tokens=result.token_usage,
        )
        return result

    async def fetch_user_preferences(self, user_id: str) -> dict:
        """Fetch user preferences from database."""
        # Implementation
        return {}

    async def log_interaction(self, **kwargs):
        """Log interaction to analytics."""
        # Implementation
        pass


# ✅ Use middleware
agent = Agent(
    name="assistant",
    model=ModelConfig(model="gpt-4o"),
    middleware=[UserContextMiddleware()],
)
```

---

## Conversation History Management

### Retrieve History

```python
from cortex.memory import PostgresSaver

checkpointer = PostgresSaver(...)

# ✅ Get conversation history
history = await checkpointer.get_messages(thread_id="user-123-session-456")

for msg in history:
    print(f"{msg['role']}: {msg['content'][:100]}...")
```

### Clear History

```python
# ✅ Clear specific thread
await checkpointer.clear_thread(thread_id="user-123-session-456")

# ✅ Clear all threads for user
user_threads = await checkpointer.list_threads(user_id="user-123")
for thread_id in user_threads:
    await checkpointer.clear_thread(thread_id)
```

### Prune Old History

```python
from datetime import datetime, timedelta

# ✅ Delete threads older than 30 days
cutoff_date = datetime.now() - timedelta(days=30)
await checkpointer.prune_threads(older_than=cutoff_date)
```

---

## Memory Configuration

### PostgresSaver Options

```python
from cortex.memory import PostgresSaver

checkpointer = PostgresSaver(
    connection_string="postgresql://user:pass@localhost/cortex",
    table_name="checkpoints",  # Default table name
    serde="json",  # Serialization format (json, pickle)
    max_history=50,  # Max messages to keep per thread
    auto_prune=True,  # Auto-delete old threads
    prune_after_days=30,  # Days before auto-prune
)
```

---

## Testing Memory

### Test Persistence

```python
import pytest
from cortex.memory import PostgresSaver
from cortex.orchestration import Agent, ModelConfig

@pytest.mark.asyncio
async def test_conversation_persistence():
    """Test that conversation history persists across runs."""
    checkpointer = PostgresSaver(connection_string="postgresql://...")

    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o"),
        checkpointer=checkpointer,
    )

    thread_id = "test-thread-123"

    # First message
    result1 = await agent.run("My name is John", thread_id=thread_id)

    # Second message (should remember name)
    result2 = await agent.run("What is my name?", thread_id=thread_id)

    # Agent should remember the name
    assert "john" in result2.response.lower()

    # Cleanup
    await checkpointer.clear_thread(thread_id)

@pytest.mark.asyncio
async def test_thread_isolation():
    """Test that different threads don't share history."""
    checkpointer = PostgresSaver(connection_string="postgresql://...")

    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o"),
        checkpointer=checkpointer,
    )

    # Thread 1
    await agent.run("My name is John", thread_id="thread-1")

    # Thread 2 (different conversation)
    result = await agent.run("What is my name?", thread_id="thread-2")

    # Should not know the name from thread-1
    assert "john" not in result.response.lower()

    # Cleanup
    await checkpointer.clear_thread("thread-1")
    await checkpointer.clear_thread("thread-2")
```

---

## Performance Considerations

### Connection Pooling

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ✅ Use connection pool
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/cortex",
    pool_size=20,  # Max connections
    max_overflow=10,  # Extra connections when pool full
    pool_pre_ping=True,  # Test connections before use
)

SessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Use in checkpointer
checkpointer = PostgresSaver(engine=engine)
```

### Lazy Loading

```python
# ✅ Only load recent messages
checkpointer = PostgresSaver(
    connection_string="...",
    max_history=50,  # Only keep last 50 messages
)

# Or load on-demand
history = await checkpointer.get_messages(
    thread_id="...",
    limit=20,  # Only load last 20 messages
)
```

---

## Monitoring

### Log Memory Operations

```python
import logging
import time

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMemoryMiddleware):
    """Log all memory operations."""

    async def before_run(self, messages, thread_id, metadata):
        logger.info(
            "Loading conversation history",
            extra={
                "thread_id": thread_id,
                "message_count": len(messages),
            },
        )
        return messages, metadata

    async def after_run(self, result, thread_id, metadata):
        logger.info(
            "Saved conversation state",
            extra={
                "thread_id": thread_id,
                "tokens": result.token_usage,
            },
        )
        return result
```

### Metrics to Track

```python
metrics = {
    "thread_id": thread_id,
    "history_size": len(history),
    "load_time_ms": load_duration,
    "save_time_ms": save_duration,
    "total_tokens": sum_tokens(history),
}

logger.info("Memory operation completed", extra=metrics)
```

---

## Common Issues

### Issue 1: Thread ID Collisions

**Problem:** Different users sharing same thread_id.

**Solution:** Include user_id in thread_id format:

```python
# ✅ Correct - Unique per user and session
thread_id = f"user-{user_id}-session-{session_id}"

# ❌ Wrong - Can collide across users
thread_id = f"session-{session_id}"
```

### Issue 2: Memory Bloat

**Problem:** Threads grow too large (token limit exceeded).

**Solutions:**
1. Set `max_history` limit
2. Implement sliding window
3. Summarize old messages

```python
# ✅ Limit history size
checkpointer = PostgresSaver(max_history=50)

# ✅ Summarize old messages (advanced)
if len(history) > 50:
    old_messages = history[:-20]  # Keep last 20
    summary = await summarizer.summarize(old_messages)
    history = [{"role": "system", "content": summary}] + history[-20:]
```

### Issue 3: Slow Loading

**Problem:** Loading history takes > 500ms.

**Solutions:**
1. Add database indexes
2. Use connection pooling
3. Implement caching layer
4. Limit history size

```python
# ✅ Create index
await checkpointer.create_indexes()

# ✅ Cache recent threads
from functools import lru_cache

@lru_cache(maxsize=100)
async def get_cached_history(thread_id: str):
    return await checkpointer.get_messages(thread_id)
```

---

## Best Practices Summary

✅ **Do:**
- Use consistent thread_id format (include user_id)
- Set max_history to prevent bloat
- Use connection pooling for PostgreSQL
- Monitor load/save performance
- Test thread isolation
- Implement auto-pruning of old threads
- Add indexes for fast queries

❌ **Don't:**
- Share thread_ids across users
- Let threads grow unbounded
- Forget to clean up test threads
- Skip monitoring memory operations
- Ignore connection pool limits
- Store sensitive data in checkpoints (encrypt if needed)

---

## Reference Files

- [PostgresSaver](../../cortex/memory/postgres_saver.py)
- [Memory Middleware](../../cortex/memory/middleware.py)
- [Memory Strategy Docs](../../docs/MEMORY_STRATEGY.md)
- [Memory Implementation](../../docs/MEMORY_MIDDLEWARE_IMPLEMENTATION.md)
