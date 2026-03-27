---
paths:
  - "cortex/orchestration/**/*.py"
  - "tests/orchestration/**/*.py"
  - "examples/*orchestration*.py"
---

# Orchestration Development Rules

**Auto-loads when:** Working with agent orchestration code

---

## Agent Initialization Pattern

```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="agent_name",
    description="Purpose of this agent",
    system_prompt="Detailed instructions for the agent...",
    model=ModelConfig(
        model="gpt-4o",  # or claude-sonnet-4, gemini-2.0-flash
        temperature=0.7,
        use_gateway=False,  # True for cost tracking
    ),
    tools=[tool1, tool2],  # Or None for all from registry
    tool_registry=registry,  # Pre-configured with context
    max_iterations=25,
)
```

---

## Async/Await Requirements

✅ **All agent operations MUST be async:**

```python
# ✅ Correct
result = await agent.run(query)
result = await agent.stream_to_writer(query, stream_writer=writer)

# ❌ Wrong - Missing await
result = agent.run(query)  # SyntaxError or runtime error
```

**Rule:** If you see `agent.run()` or any agent method call without `await`, it's a bug.

---

## Thread Management (Multi-turn Conversations)

✅ **Use `thread_id` for multi-turn conversations:**

```python
# ✅ Good - Context persists across turns
thread_id = f"{user_id}-{session_id}"  # Unique per user session
result = await agent.run(message, thread_id=thread_id)

# User can ask follow-up questions:
result = await agent.run("What about that?", thread_id=thread_id)
# Agent remembers previous context
```

❌ **Don't lose context:**

```python
# ❌ Bad - New thread every time (agent forgets previous messages)
result = await agent.run(message)  # No thread_id specified
```

**Rule:** Always use `thread_id` for chat-like interactions.

---

## Context Injection (Security)

✅ **Use `ToolRegistry.set_context()` for sensitive data:**

```python
from cortex.orchestration import ToolRegistry
from langchain_core.tools import tool
from pydantic import Field

@tool
def get_user_data(
    user_id: str = Field(..., description="User ID"),
    query: str = Field(..., description="Data to fetch"),
) -> str:
    """Get user data from database."""
    # user_id is injected by registry, NOT controlled by LLM
    return f"Data for {user_id}: {query}"

# Setup
registry = ToolRegistry()
registry.register(get_user_data)
registry.set_context(user_id=current_user.id)  # Injected automatically

agent = Agent(tool_registry=registry, tools=None)

# When agent calls get_user_data(query="preferences"):
# Runtime actually calls: get_user_data(user_id="user123", query="preferences")
# LLM schema only shows: get_user_data(query: str)
```

❌ **Never put sensitive data in system prompts:**

```python
# ❌ DANGEROUS - LLM can see and manipulate user_id
system_prompt = f"You are helping user {user_id}. Their role is {user_role}."

# ❌ DANGEROUS - Tool lets LLM control user_id
@tool
def get_user_data(user_id: str, query: str) -> str:
    """Get user data."""
    return database.query(user_id, query)
```

**Rule:** Use context injection for user_id, tenant_id, session_id, or any data the LLM should NOT control.

---

## Error Handling

✅ **All agent calls MUST have try/except:**

```python
import logging

logger = logging.getLogger(__name__)

try:
    result = await agent.run(query, thread_id=thread_id)
except ValueError as e:
    logger.error(f"Invalid input: {e}", exc_info=True)
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.error(
        f"Agent execution failed",
        exc_info=True,
        extra={"agent": agent.name, "query": query},
    )
    raise HTTPException(status_code=500, detail="Agent execution failed")
```

**Rule:** Always log errors with context (`agent.name`, `query`, `thread_id`).

---

## Tool Creation

✅ **Use LangChain `@tool` decorator:**

```python
from langchain_core.tools import tool
from pydantic import Field

@tool
def search_database(
    query: str = Field(..., description="Search query"),
    limit: int = Field(default=10, description="Max results"),
) -> str:
    """Search the knowledge base for relevant documents.

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        JSON string with search results
    """
    results = vector_store.similarity_search(query, k=limit)
    return json.dumps([r.dict() for r in results])
```

**Requirements:**
- Descriptive docstring (LLM uses this to decide when to call)
- `Field()` with descriptions for all parameters
- Return type annotation
- Return serializable data (str, dict, list)

---

## Model Configuration

✅ **Default model: `gpt-4o`**

```python
# ✅ Production default
ModelConfig(model="gpt-4o", temperature=0.7)

# ✅ Claude for reasoning tasks
ModelConfig(model="claude-sonnet-4", temperature=0.7)

# ✅ Gemini for speed
ModelConfig(model="gemini-2.0-flash", temperature=0.7)

# ✅ Use gateway for cost tracking
ModelConfig(
    model="gpt-4o",
    use_gateway=True,
    gateway_url="http://llm-gateway:50057/v1",
    tenant_id="tenant-123",
)
```

**Rule:** Always specify model explicitly (don't rely on defaults).

---

## Performance Monitoring

✅ **Log token usage:**

```python
result = await agent.run(query)

logger.info(
    "Agent execution completed",
    extra={
        "agent": agent.name,
        "thread_id": thread_id,
        "tokens": result.token_usage,  # {"gpt-4o": {"prompt": 100, "completion": 50}}
        "duration_ms": result.duration_ms,
        "message_count": len(result.messages),
    }
)
```

**Metrics to track:**
- Token usage per model
- Execution duration
- Number of tool calls
- Error rate

---

## Testing Agents

✅ **Use `pytest-asyncio`:**

```python
import pytest
from cortex.orchestration import Agent, ModelConfig

@pytest.mark.asyncio
async def test_agent_basic_execution():
    """Test agent can execute simple query."""
    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("Say hello")

    assert result.response is not None
    assert "hello" in result.response.lower()
    assert "gpt-4o" in result.token_usage

@pytest.mark.asyncio
async def test_agent_with_tools():
    """Test agent can use tools."""
    @tool
    def calculator(operation: str, a: float, b: float) -> str:
        """Perform math operations."""
        ops = {"add": lambda x, y: x + y}
        return str(ops[operation](a, b))

    agent = Agent(
        name="math_agent",
        tools=[calculator],
    )

    result = await agent.run("What is 5 + 7?")

    assert "12" in result.response
```

---

## Common Mistakes

### ❌ Mistake 1: Forgetting await

```python
# ❌ Wrong
result = agent.run(query)  # Returns coroutine, not result

# ✅ Correct
result = await agent.run(query)
```

### ❌ Mistake 2: Not using thread_id

```python
# ❌ Wrong - Agent forgets context
await agent.run("Who won the game?")
await agent.run("When did they win?")  # Agent doesn't remember "Who"

# ✅ Correct - Agent remembers
await agent.run("Who won the game?", thread_id="session-123")
await agent.run("When did they win?", thread_id="session-123")
```

### ❌ Mistake 3: Exposing sensitive data

```python
# ❌ Wrong - LLM can see user_id
@tool
def get_data(user_id: str, query: str) -> str:
    return database.fetch(user_id, query)

# ✅ Correct - user_id injected via registry
registry.set_context(user_id="user123")
```

### ❌ Mistake 4: No error handling

```python
# ❌ Wrong - Unhandled exceptions crash app
result = await agent.run(query)

# ✅ Correct - Graceful error handling
try:
    result = await agent.run(query)
except Exception as e:
    logger.error(f"Agent error: {e}", exc_info=True)
    return default_response
```

---

## Best Practices Summary

✅ **Do:**
- Use `await` for all agent operations
- Set `thread_id` for multi-turn conversations
- Use `ToolRegistry.set_context()` for sensitive data
- Include proper error handling with logging
- Monitor token usage for cost optimization
- Add type hints to all functions
- Write tests for agent behavior

❌ **Don't:**
- Block on `agent.run()` without `await`
- Put `user_id` or sensitive data in system prompts
- Create new `thread_id` for every message
- Ignore error handling
- Skip token usage logging
- Forget to specify model explicitly

---

## Reference Files

- [Agent Implementation](../../cortex/orchestration/agent.py)
- [ModelConfig](../../cortex/orchestration/config.py)
- [ToolRegistry](../../cortex/orchestration/tools/registry.py)
- [Architecture Docs](../../docs/ORCHESTRATION_ARCHITECTURE.md)
- [Quick Start](../../docs/QUICK_START.md)
