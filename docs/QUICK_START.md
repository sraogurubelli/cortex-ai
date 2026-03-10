# Cortex Orchestration SDK - Quick Start

**5-minute guide to building AI agents with Cortex-AI**

---

## Installation

```bash
cd cortex-ai
pip install -r requirements.txt
```

**Set API keys:**
```bash
export OPENAI_API_KEY="sk-..."          # For OpenAI models
export ANTHROPIC_API_KEY="sk-ant-..."  # For Claude models
export GOOGLE_API_KEY="..."            # For Gemini (optional)
```

---

## Basic Usage

### 1. Simple Agent (No Tools)

```python
import asyncio
from cortex.orchestration import Agent, ModelConfig

async def main():
    # Create agent
    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    # Run query
    result = await agent.run("What is the capital of France?")

    print(result.response)
    print(result.token_usage)

asyncio.run(main())
```

**Output:**
```
The capital of France is Paris.
{'gpt-4o': {'prompt_tokens': 25, 'completion_tokens': 8, 'total_tokens': 33}}
```

---

### 2. Agent with Tools

```python
from langchain_core.tools import tool
from cortex.orchestration import Agent, ModelConfig

@tool
def calculator(operation: str, a: float, b: float) -> str:
    """Perform basic math operations.

    Args:
        operation: add, subtract, multiply, or divide
        a: First number
        b: Second number
    """
    ops = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "Error",
    }
    return str(ops[operation](a, b))

async def main():
    agent = Agent(
        name="math_assistant",
        system_prompt="You are a math assistant. Use the calculator tool.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[calculator],
    )

    result = await agent.run("What is 15 multiplied by 7?")
    print(result.response)

asyncio.run(main())
```

**Output:**
```
15 multiplied by 7 equals 105.
```

---

### 3. Context Injection (Secure Tool Calls)

**Problem:** You don't want the LLM to see or control `user_id`

**Solution:** Context injection

```python
from langchain_core.tools import tool
from pydantic import Field
from cortex.orchestration import Agent, ModelConfig, ToolRegistry

@tool
def get_user_data(
    user_id: str = Field(..., description="User ID"),
    query: str = Field(..., description="Data to fetch"),
) -> str:
    """Get user data from database."""
    # user_id is injected, not provided by LLM
    return f"Data for {user_id}: {query} = ..."

async def main():
    # Setup registry with context
    registry = ToolRegistry()
    registry.register(get_user_data)
    registry.set_context(user_id="user123")  # Injected automatically

    # Create agent
    agent = Agent(
        name="assistant",
        tool_registry=registry,
        tools=None,  # Use all from registry
    )

    # LLM only sees: get_user_data(query: str)
    # Runtime calls: get_user_data(user_id="user123", query="...")
    result = await agent.run("Get my account balance")
    print(result.response)

asyncio.run(main())
```

**Key Point:** The LLM schema hides `user_id`, but it's injected at runtime. Secure! 🔒

---

### 4. Streaming (SSE)

```python
from cortex.orchestration import Agent, ModelConfig

class SimpleStreamWriter:
    """Example SSE writer."""

    async def write_event(self, event_type: str, data) -> None:
        print(f"[{event_type}] {data}")

    async def close(self) -> None:
        pass

async def main():
    agent = Agent(
        name="assistant",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    writer = SimpleStreamWriter()

    result = await agent.stream_to_writer(
        "Tell me a joke",
        stream_writer=writer,
    )

    print(f"\nFinal: {result.response}")
    print(f"Tokens: {result.token_usage}")

asyncio.run(main())
```

**Output:**
```
[assistant_message] Why don't scientists trust atoms?
[assistant_message]  Because they make up everything!
[model_usage] {'gpt-4o': {'prompt_tokens': 12, 'completion_tokens': 15, 'total_tokens': 27}}

Final: Why don't scientists trust atoms? Because they make up everything!
Tokens: {'gpt-4o': {'prompt_tokens': 12, 'completion_tokens': 15, 'total_tokens': 27}}
```

---

### 5. Multi-turn Conversation

```python
async def main():
    agent = Agent(name="tutor", system_prompt="You are a math tutor.")

    # Turn 1
    r1 = await agent.run("What is 25 + 17?", thread_id="session-1")
    print(f"Q1: What is 25 + 17?\nA1: {r1.response}\n")

    # Turn 2 (same thread - agent remembers context)
    r2 = await agent.run("And if I multiply that by 2?", thread_id="session-1")
    print(f"Q2: And if I multiply that by 2?\nA2: {r2.response}")

asyncio.run(main())
```

**Output:**
```
Q1: What is 25 + 17?
A1: 25 + 17 = 42

Q2: And if I multiply that by 2?
A2: 42 multiplied by 2 equals 84.
```

**Key:** Same `thread_id` preserves conversation context.

---

## Choosing a Model

### Direct Providers (Default)

```python
ModelConfig(model="gpt-4o", use_gateway=False)          # OpenAI
ModelConfig(model="claude-sonnet-4", use_gateway=False) # Anthropic
ModelConfig(model="gemini-2.0-flash", use_gateway=False) # Google
```

**Auto-detection:** Provider is inferred from model name prefix.

### Via LLM Gateway (Optional)

```python
ModelConfig(
    model="gpt-4o",
    use_gateway=True,
    gateway_url="http://llm-gateway:50057/v1",
    tenant_id="tenant-123",
)
```

**Benefits:** Cost tracking, centralized control, rate limiting.

---

## Configuration Options

### AgentConfig

```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    # Identity
    name="assistant",
    description="General purpose assistant",
    system_prompt="You are helpful...",

    # Model
    model=ModelConfig(model="gpt-4o", temperature=0.7),

    # Tools
    tools=[tool1, tool2],  # Or None for all from registry
    tool_registry=my_registry,  # Optional pre-configured registry

    # Context
    context={"user_id": "user123"},  # Injected into tools

    # Streaming
    mode="standard",  # or "architect" (changes event types)
    suppress_events={"tool_request"},  # Hide tool calls from stream

    # Advanced
    max_iterations=25,
    checkpointer=None,  # Or PostgresSaver for persistence
    middleware=[],  # Custom middleware
)
```

### ModelConfig

```python
ModelConfig(
    # Model selection
    model="gpt-4o",               # Required
    provider="openai",            # Auto-inferred if not set

    # Generation
    temperature=0.7,              # 0-1
    max_tokens=None,              # Optional limit

    # Gateway (optional)
    use_gateway=False,            # Default: direct provider
    gateway_url=None,             # HTTP endpoint
    tenant_id=None,               # For tracking
    source=None,                  # Request source
    product=None,                 # Product identifier

    # Vertex AI (for anthropic_vertex)
    project=None,                 # GCP project
    location=None,                # GCP region
)
```

---

## Common Patterns

### Pattern 1: Secure Tool Context

```python
# ✅ Good: Context injected server-side
registry = ToolRegistry()
registry.set_context(user_id=request.user_id)
agent = Agent(tool_registry=registry, ...)

# ❌ Bad: LLM controls user_id
# Never put user_id in the prompt!
```

### Pattern 2: Event Suppression

```python
# ✅ For end users: Hide implementation details
agent = Agent(suppress_events={"tool_request", "tool_result"})

# ✅ For developers: Show everything
agent = Agent(suppress_events=set())
```

### Pattern 3: Thread Management

```python
# ✅ Persistent conversations
thread_id = f"{user_id}-{session_id}"
result = await agent.run(message, thread_id=thread_id)

# ❌ Lost context
result = await agent.run(message)  # New thread each time
```

---

## Debugging

### Enable Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("cortex.orchestration")
logger.setLevel(logging.DEBUG)
```

### Inspect Messages

```python
result = await agent.run("...")

for msg in result.messages:
    print(f"{msg.type}: {msg.content}")
```

### Token Usage

```python
result = await agent.run("...")

print(result.token_usage)
# {'gpt-4o': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}
```

---

## Next Steps

1. **Read examples:** [`examples/orchestration_demo.py`](../examples/orchestration_demo.py)
2. **Architecture:** [`docs/ORCHESTRATION_ARCHITECTURE.md`](ORCHESTRATION_ARCHITECTURE.md)
3. **Build your tools:** See [LangChain Tool docs](https://python.langchain.com/docs/modules/tools/)
4. **Deploy:** Integrate with FastAPI (see [`cortex/api/`](../cortex/api/))

---

## FAQ

**Q: Can I use multiple models in one agent?**
A: No, one agent = one model. For multi-model, use multiple agents.

**Q: How do I persist conversations?**
A: Use PostgresSaver checkpointer and consistent thread_ids.

**Q: Can the LLM call tools in parallel?**
A: Yes, LangGraph supports parallel tool execution.

**Q: How do I add custom middleware?**
A: Pass `middleware=[MyMiddleware()]` to Agent constructor.

**Q: What if I need MCP tools?**
A: MCP support is planned for Phase 2. Track issue #XYZ.

---

**Need help?** Open an issue on GitHub or check the full [architecture docs](ORCHESTRATION_ARCHITECTURE.md).
