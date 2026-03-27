---
name: orchestration-dev
description: Agent development patterns for cortex-ai orchestration. Auto-activates when creating or modifying agents.
paths:
  - "cortex/orchestration/**/*.py"
  - "tests/orchestration/**/*.py"
  - "examples/*orchestration*.py"
allowed-tools: Read, Grep, Glob, Edit
model: sonnet
effort: medium
---

# Orchestration Agent Development

## Purpose

This skill provides patterns and best practices for developing orchestration agents in cortex-ai.

## When to Use This Skill

**Auto-activates when:**
- Creating new Agent classes
- Modifying existing agents in `cortex/orchestration/`
- Adding tools to agents
- Debugging agent execution
- Writing tests for agents

**Manual invoke:** `/orchestration-dev`

---

## Agent Creation Workflow

### Step 1: Define Your Agent

```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="my_agent",
    description="What this agent does",
    system_prompt="""
You are a helpful assistant specialized in [domain].

Your responsibilities:
- [Responsibility 1]
- [Responsibility 2]

Guidelines:
- [Guideline 1]
- [Guideline 2]
    """,
    model=ModelConfig(
        model="gpt-4o",  # or claude-sonnet-4, gemini-2.0-flash
        temperature=0.7,
        use_gateway=False,  # or True for cost tracking
    ),
)
```

### Step 2: Add Tools (If Needed)

```python
from langchain_core.tools import tool
from pydantic import Field

@tool
def search_database(
    query: str = Field(..., description="Search query"),
) -> str:
    """Search the knowledge base."""
    # Implementation
    return results
```

### Step 3: Configure Context Injection (Security)

```python
from cortex.orchestration import ToolRegistry

# Setup registry with secure context
registry = ToolRegistry()
registry.register(search_database)
registry.set_context(user_id="user123")  # LLM never sees this

agent = Agent(
    name="assistant",
    tool_registry=registry,
    tools=None,  # Use all from registry
)
```

### Step 4: Execute Agent

```python
# Single turn
result = await agent.run("What is the weather?")

# Multi-turn conversation
thread_id = f"{user_id}-{session_id}"
result = await agent.run("Follow-up question", thread_id=thread_id)
```

### Step 5: Handle Streaming (Optional)

```python
from cortex.orchestration import SimpleStreamWriter

writer = SimpleStreamWriter()

result = await agent.stream_to_writer(
    "Tell me a story",
    stream_writer=writer,
)
```

---

## Best Practices

### ✅ Do

- Use async/await for all agent operations
- Set thread_id for multi-turn conversations
- Use ToolRegistry.set_context() for sensitive data
- Include proper error handling
- Monitor token usage for cost optimization
- Add type hints to all functions

### ❌ Don't

- Block on agent.run() without await
- Put user_id or sensitive data in system prompts
- Create new thread for every message (loses context)
- Ignore error handling
- Skip token usage logging

---

## Common Patterns

### Pattern 1: Request/Response Agent

```python
async def handle_request(request: ChatRequest) -> ChatResponse:
    agent = Agent(
        name="assistant",
        model=ModelConfig(model="gpt-4o"),
    )

    try:
        result = await agent.run(
            request.message,
            thread_id=request.session_id,
        )

        return ChatResponse(
            message=result.response,
            tokens=result.token_usage,
        )
    except Exception as e:
        logger.error(f"Agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Agent error")
```

### Pattern 2: Tool-Enabled Agent

```python
@tool
def calculator(operation: str, a: float, b: float) -> str:
    """Perform math operations."""
    ops = {"add": lambda x, y: x + y, "multiply": lambda x, y: x * y}
    return str(ops[operation](a, b))

agent = Agent(
    name="math_assistant",
    system_prompt="Use the calculator tool for math.",
    tools=[calculator],
)

result = await agent.run("What is 15 times 7?")
# Agent will use calculator tool
```

### Pattern 3: Context-Aware Agent

```python
@tool
def get_user_preferences(
    user_id: str = Field(..., description="User ID"),
    setting: str = Field(..., description="Setting name"),
) -> str:
    """Get user preferences."""
    # user_id injected by registry, not controlled by LLM
    return f"User {user_id} prefers {setting}"

registry = ToolRegistry()
registry.register(get_user_preferences)
registry.set_context(user_id=current_user.id)

agent = Agent(tool_registry=registry, tools=None)
result = await agent.run("What are my preferences?")
```

---

## Testing

### Unit Test Example

```python
import pytest
from cortex.orchestration import Agent, ModelConfig

@pytest.mark.asyncio
async def test_agent_basic_execution():
    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("Say hello")

    assert result.response is not None
    assert len(result.messages) > 0
    assert "gpt-4o" in result.token_usage

@pytest.mark.asyncio
async def test_agent_with_tools():
    @tool
    def test_tool(query: str) -> str:
        """Test tool."""
        return f"Result: {query}"

    agent = Agent(
        name="tool_agent",
        tools=[test_tool],
    )

    result = await agent.run("Use the test tool with 'hello'")

    assert "Result: hello" in result.response
```

---

## Troubleshooting

**Q: Agent not calling tools?**
A: Check tool docstrings are descriptive. LLM uses docstrings to decide when to call.

**Q: Token usage very high?**
A: Monitor system_prompt length. Use concise prompts. Enable prompt caching.

**Q: Conversation losing context?**
A: Ensure thread_id is consistent across turns. Check checkpointer configuration.

**Q: Async errors?**
A: All agent methods are async. Always use `await agent.run()`.

---

## Reference Files

- [Agent Implementation](../../../cortex/orchestration/agent.py)
- [ModelConfig](../../../cortex/orchestration/config.py)
- [ToolRegistry](../../../cortex/orchestration/tools/registry.py)
- [Architecture Docs](../../../docs/ORCHESTRATION_ARCHITECTURE.md)
- [Quick Start](../../../docs/QUICK_START.md)

---

**Need more help?** Check `.claude/rules/orchestration.md` for detailed guidelines.
