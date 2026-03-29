# Cortex Orchestration SDK - Architecture Overview

**Status:** Production-ready (extracted from ml-infra)
**Framework:** LangGraph-based (zero autogen dependencies)
**Language:** Python 3.11+

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Design Patterns](#design-patterns)
4. [Data Flow](#data-flow)
5. [Key Features](#key-features)
6. [Extension Points](#extension-points)
7. [Comparison with ml-infra](#comparison-with-ml-infra)

---

## Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                       │
│                  (FastAPI, CLI, Scripts)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  High-level Agent API                       │
│           Agent class (run, stream, stream_to_writer)       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                 Configuration Layer                         │
│          AgentConfig, ModelConfig, ToolRegistry             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    Builder Layer                            │
│              build_agent() → CompiledStateGraph             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   LangGraph Core                            │
│        create_agent() → State Management + Execution        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  LLM Provider Layer                         │
│    LLMClient → OpenAI | Anthropic | Google | Gateway       │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
cortex/orchestration/
├── __init__.py              # Public API exports
├── agent.py                 # Agent, AgentResult (high-level API)
├── builder.py               # build_agent() function
├── config.py                # AgentConfig, ModelConfig
├── llm.py                   # LLMClient (provider abstraction)
├── streaming.py             # StreamHandler, EventType, PartManager
├── observability.py         # ModelUsageTracker, token tracking
└── tools.py                 # ToolRegistry, context injection
```

---

## Core Components

### 1. Agent (High-level API)

**Purpose:** Simplify agent lifecycle management

**Key Methods:**
- `run()` - Non-streaming execution, returns AgentResult
- `stream()` - Raw LangGraph event stream (AsyncIterator)
- `stream_to_writer()` - SSE streaming with usage tracking
- `run_streaming()` - Streaming with final result aggregation

**Responsibilities:**
- Build and cache compiled graph
- Manage checkpointer (default: MemorySaver)
- Track token usage across runs
- Extract final responses from message history

**Example:**
```python
agent = Agent(
    name="assistant",
    system_prompt="You are helpful.",
    model=ModelConfig(model="gpt-4o", use_gateway=False),
    tools=[calculator],
)
result = await agent.run("What is 2 + 2?")
print(result.response, result.token_usage)
```

---

### 2. AgentConfig & ModelConfig

**Purpose:** Declarative agent configuration

**AgentConfig:**
- Identity: `name`, `description`
- Behavior: `system_prompt`, `mode` (standard/architect)
- Tools: `tools` list (objects, names, or None for all)
- Multi-agent: `can_handoff_to` (for Swarm)
- Advanced: `middleware`, `checkpointer`, `suppress_events`

**ModelConfig:**
- Model: `model` (auto-infers provider from name)
- Provider: `provider` (openai, anthropic, anthropic_vertex, google)
- Settings: `temperature`, `max_tokens`
- Gateway: `use_gateway`, `gateway_url`, `tenant_id`, `source`, `product`
- Vertex AI: `project`, `location` (for anthropic_vertex)

**Auto-inference:**
```python
ModelConfig(model="gpt-4o")         # → provider="openai"
ModelConfig(model="claude-sonnet-4") # → provider="anthropic"
ModelConfig(model="gemini-2.0-flash") # → provider="google"
```

---

### 3. LLMClient (Provider Abstraction)

**Purpose:** Create LangChain chat models with unified API

**Supported Providers:**
1. **OpenAI** - `ChatOpenAI`
2. **Anthropic** - `ChatAnthropic` (direct API)
3. **Anthropic Vertex** - `ChatAnthropicVertex` (via Google Cloud)
4. **Google** - `ChatGoogleGenerativeAI`

**Gateway Mode:**
- Routes through centralized LLM Gateway
- Adds tracking headers: `X-Tenant-Id`, `X-Source`, `X-Product`
- Uses OpenAI-compatible HTTP endpoint
- Formats model as `online/{provider}/{model}`

**Example:**
```python
# Direct provider
client = LLMClient(ModelConfig(model="gpt-4o", use_gateway=False))
model = client.get_model()

# Via gateway
client = LLMClient(ModelConfig(
    model="gpt-4o",
    use_gateway=True,
    gateway_url="http://llm-gateway:50057/v1",
    tenant_id="tenant-123",
))
model = client.get_model()
```

---

### 4. ToolRegistry (Context Injection)

**Purpose:** Manage tools with automatic context injection

**Key Features:**
1. **Tool Registration:** Register BaseTool, callables, or names
2. **Context Management:** `set_context(user_id=..., session_id=...)`
3. **Schema Modification:** Strip context params from LLM-visible schema
4. **Runtime Injection:** Inject context at tool call time
5. **LLM Quirk Handling:** Filter None/empty values (Claude passes null)

**Context Injection Flow:**
```python
# Tool definition
@tool
def get_user_data(user_id: str, query: str) -> str:
    """Get user data."""
    ...

# Setup
registry = ToolRegistry()
registry.register(get_user_data)
registry.set_context(user_id="user123")

# LLM sees: get_user_data(query: str)
# Runtime calls: get_user_data(user_id="user123", query="...")
```

**Why This Matters:**
- **Security:** Sensitive IDs never exposed to LLM
- **Simplicity:** LLM doesn't need to track context
- **Flexibility:** Change context per request without re-building tools

---

### 5. StreamHandler (Event Processing)

**Purpose:** Convert LangGraph events to SSE format

**Event Types:**
- `assistant_message` - AI responses
- `assistant_thought` / `detailed_analysis` - Reasoning (mode-aware)
- `assistant_tool_request` - Tool invocations
- `assistant_tool_result` - Tool outputs
- `model_usage` - Token counts
- `error`, `done` - Lifecycle events

**Part Streaming:**
- Wraps thoughts/analysis in `part_start` / `part_delta` / `part_end`
- Enables incremental rendering in UIs

**Event Suppression:**
- `suppress_events={"tokens", "tool_request"}` to mute categories
- Per-agent suppression via `agent_suppress_events`

**Example:**
```python
handler = StreamHandler(
    stream_writer,
    mode="ARCHITECT",  # Use "detailed_analysis" instead of "thought"
    suppress_events={"tool_request"},  # Hide tool calls
)
async for event in compiled.astream_events(...):
    await handler.handle_event(event)
```

---

### 6. ModelUsageTracker (Observability)

**Purpose:** Track token consumption across LLM calls

**Recording Modes:**
1. **Explicit:** `record(model, prompt_tokens, completion_tokens)`
2. **Event-based:** `record_from_event(langgraph_event)`
3. **Message-based:** `record_from_messages(messages)`

**Cache Support:**
- Tracks Anthropic prompt caching: `cache_read`, `cache_creation`
- Nested under `"cache"` key in usage dict

**Output Format:**
```json
{
  "gpt-4o": {
    "prompt_tokens": 300,
    "completion_tokens": 150,
    "total_tokens": 450
  },
  "claude-sonnet-4": {
    "prompt_tokens": 500,
    "completion_tokens": 200,
    "total_tokens": 700,
    "cache": {
      "cache_read": 1000,
      "cache_creation": 0
    }
  }
}
```

---

## Design Patterns

### 1. **Lazy Initialization**

**Where:** `LLMClient._ensure_*()` methods

**Why:** Avoid import errors when provider packages aren't installed

```python
ChatOpenAI = None

def _ensure_openai():
    global ChatOpenAI
    if ChatOpenAI is None:
        from langchain_openai import ChatOpenAI as _ChatOpenAI
        ChatOpenAI = _ChatOpenAI
    return ChatOpenAI
```

### 2. **Builder Pattern**

**Where:** `build_agent()`, `Agent._build()`

**Why:** Separate configuration from construction

```python
config = AgentConfig(name="assistant", model=ModelConfig(...))
agent = build_agent(config, tool_registry=registry)
```

### 3. **Protocol-based Interfaces**

**Where:** `StreamWriterProtocol`

**Why:** Duck typing for flexibility (no framework coupling)

```python
class StreamWriterProtocol(Protocol):
    async def write_event(self, event_type: str, data: Any) -> None: ...
    async def close(self) -> None: ...
```

### 4. **Decorator Pattern**

**Where:** `ToolRegistry.wrap_with_context()`

**Why:** Extend tool behavior without modifying originals

```python
wrapped = registry.wrap_with_context(original_tool)
# wrapped filters None, injects context, calls original
```

### 5. **Strategy Pattern**

**Where:** `LLMClient._create_*_model()` methods

**Why:** Select provider algorithm at runtime

```python
if provider == "openai":
    return self._create_openai_model()
elif provider == "anthropic":
    return self._create_anthropic_model()
```

### 6. **Singleton Registry**

**Where:** `ToolRegistry` (class-level state)

**Why:** Share tools across agent instances

```python
registry = ToolRegistry.with_defaults()  # Returns fresh copy
```

---

## Data Flow

### 1. Non-Streaming Execution

```
User → Agent.run(message)
  ↓
Agent._build() → build_agent() → LangGraph create_agent()
  ↓
compiled.ainvoke({"messages": [HumanMessage(...)]})
  ↓
LangGraph executes: LLM → Tools → LLM → ...
  ↓
Result: {"messages": [HumanMessage, AIMessage, ToolMessage, ...]}
  ↓
ModelUsageTracker.record_from_messages(messages)
  ↓
AgentResult(response, messages, token_usage)
  ↓
User receives result
```

### 2. Streaming Execution

```
User → Agent.stream_to_writer(message, stream_writer)
  ↓
compiled.astream_events({"messages": [...]}, version="v2")
  ↓
For each event:
  ├─ ModelUsageTracker.record_from_event(event)
  └─ StreamHandler.handle_event(event)
       ↓
       Convert to SSE: on_chat_model_stream → assistant_message
       ↓
       stream_writer.write_event(event_type, data)
  ↓
Handler.close_active_part()
  ↓
Retrieve checkpointer state for final messages
  ↓
Send model_usage event
  ↓
AgentResult(response, messages, token_usage, error)
```

### 3. Tool Call with Context Injection

```
LLM returns tool_call: {"name": "get_user_data", "args": {"query": "..."}}
  ↓
LangGraph ToolNode invokes tool
  ↓
ToolRegistry.wrapped_tool is called
  ↓
wrapped_tool filters None/empty values from args
  ↓
wrapped_tool.inject_context(original_tool, filtered_args)
  ├─ Match context keys (user_id) to tool schema
  └─ Add: {"query": "...", "user_id": "user123"}
  ↓
Call original_tool(**injected_args)
  ↓
ToolMessage(content=result) added to state
```

---

## Key Features

### 1. **Multi-Provider Support**

| Provider | Use Case | Auth |
|----------|----------|------|
| OpenAI | GPT-4, o1 models | `OPENAI_API_KEY` |
| Anthropic | Claude models (direct API) | `ANTHROPIC_API_KEY` |
| Anthropic Vertex | Claude via Google Cloud | GCP credentials |
| Google | Gemini models | `GOOGLE_API_KEY` |
| Gateway | Centralized routing, cost control | Custom headers |

### 2. **Context Injection**

**Benefits:**
- Secure: LLM never sees `user_id`, `account_id`, etc.
- Flexible: Change context per request
- Simple: LLM focuses on business logic

**Limitations:**
- Tools must be in registry to get context
- Context keys must match tool parameter names exactly

### 3. **Token Tracking**

**Supports:**
- Per-model aggregation
- Anthropic prompt caching metrics
- Event-based (streaming) and message-based (post-hoc) recording

**Use Cases:**
- Cost attribution per tenant
- Model comparison (which model uses fewer tokens?)
- Cache effectiveness analysis

### 4. **Streaming**

**Two Modes:**
1. **Raw events:** `agent.stream()` → LangGraph events
2. **SSE formatted:** `agent.stream_to_writer()` → UI-ready events

**Event Suppression:**
- Global: `suppress_events={"tool_request"}`
- Per-agent: `agent_suppress_events={"researcher": {"tool_result"}}`

### 5. **Checkpointer Integration**

**Default:** `MemorySaver` (ephemeral, in-process dict)

**Why it exists:**
- Enables `aget_state()` to retrieve full message history
- Required for `AgentResult.messages` accuracy

**For production:**
- Use PostgresSaver for cross-request persistence
- Enables multi-turn conversations with `thread_id`

---

## Extension Points

### 1. **Custom Tools**

```python
from langchain_core.tools import tool

@tool
def my_custom_tool(query: str) -> str:
    """Custom tool description."""
    return f"Result for {query}"

registry = ToolRegistry()
registry.register(my_custom_tool)
```

### 2. **Custom Stream Writer**

```python
class MyStreamWriter:
    async def write_event(self, event_type: str, data) -> None:
        # Send to WebSocket, SSE, Kafka, etc.
        await my_transport.send(event_type, data)

    async def close(self) -> None:
        await my_transport.close()
```

### 3. **Custom Middleware**

```python
from langchain.agents import AgentMiddleware

class MyMiddleware(AgentMiddleware):
    async def on_tool_call(self, tool_name, args):
        # Intercept before tool execution
        ...
```

### 4. **Custom Checkpointer**

```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver(conn_string="postgresql://...")
agent = Agent(..., checkpointer=checkpointer)
```

---

## Comparison with ml-infra

### What We Kept ✅

| Component | Status | Notes |
|-----------|--------|-------|
| Agent class | ✅ Extracted | High-level API unchanged |
| LLMClient | ✅ Extracted | Gateway + direct providers |
| ToolRegistry | ✅ Extracted | Context injection pattern |
| StreamHandler | ✅ Extracted | SSE event conversion |
| ModelUsageTracker | ✅ Extracted | Token tracking + cache metrics |
| AgentConfig | ✅ Extracted | Declarative configuration |

### What We Removed ❌

| Component | Reason | Alternative |
|-----------|--------|-------------|
| Harness RBAC | Harness-specific | Use custom middleware |
| Feature flags | Harness-specific | Use env vars |
| Segment analytics | Harness-specific | Use custom tracking |
| Langfuse tracing | Optional dependency | Add as plugin |
| Harness context | Harness-specific | Use generic `context` dict |
| MCP Gateway | Not yet extracted | Phase 2 feature |
| Swarm | Not yet extracted | Phase 2 feature |

### What Changed 🔄

| Component | Change | Why |
|-----------|--------|-----|
| ModelConfig | `use_gateway=False` by default | Open source default (no gateway) |
| ToolRegistry | `with_defaults()` returns empty | No Harness-specific tools |
| Agent | No MCP loading | MCP extraction deferred |

### What's Missing 📋

1. **MCP Protocol Support** - Planned for Phase 2
2. **Multi-agent Swarm** - Planned for Phase 2
3. **Conversation Debugging** - Should add `conversation.py` as debug utility
4. **Default Tools** - No built-in tools (users register their own)

---

## Best Practices

### 1. **Use High-level API First**

```python
# ✅ Good: Simple and complete
agent = Agent(name="assistant", tools=[...])
result = await agent.run("...")

# ❌ Avoid: Unnecessary complexity
config = AgentConfig(...)
compiled = build_agent(config)
result = await compiled.ainvoke(...)
```

### 2. **Set Context Early**

```python
# ✅ Good: Set context before building agent
registry = ToolRegistry()
registry.set_context(user_id="user123")
agent = Agent(tool_registry=registry, ...)

# ❌ Avoid: Setting context after agent creation
agent = Agent(...)
agent.tool_registry.set_context(user_id="user123")  # Works but confusing
```

### 3. **Use Thread IDs for Conversations**

```python
# ✅ Good: Persistent thread ID
thread_id = "user123-session456"
result1 = await agent.run("First question", thread_id=thread_id)
result2 = await agent.run("Follow-up", thread_id=thread_id)

# ❌ Avoid: Auto-generated IDs lose context
result1 = await agent.run("First question")  # thread_id=uuid4()
result2 = await agent.run("Follow-up")       # Different thread_id
```

### 4. **Suppress Events for Clean UIs**

```python
# ✅ Good: Hide implementation details
agent = Agent(
    suppress_events={"tool_request", "tool_result"},  # Show only final answer
)

# ❌ Avoid: Overwhelming users with raw events
agent = Agent()  # Shows all tool calls, confusing for end users
```

---

## Performance Considerations

### 1. **Token Tracking Overhead**

- **Message-based:** Post-hoc extraction, no streaming overhead
- **Event-based:** Small overhead per event (~1ms)
- **Recommendation:** Use event-based for streaming, message-based for non-streaming

### 2. **Context Injection**

- Schema modification happens once per tool at wrap time
- Runtime injection is O(n) where n = context keys
- **Recommendation:** Keep context dict small (< 10 keys)

### 3. **Checkpointer Choice**

- `MemorySaver`: In-memory, fast, ephemeral
- `PostgresSaver`: Durable, ~10ms overhead per save
- **Recommendation:** Use MemorySaver for single-request, PostgresSaver for multi-turn

### 4. **Lazy Imports**

- Provider packages imported only when used
- Reduces startup time and memory
- **Recommendation:** Keep pattern for extensibility

---

## Security Considerations

### 1. **Context Injection**

**Secure:** Context params (user_id, account_id) are:
- Stripped from LLM-visible schema
- Injected server-side at runtime
- Never exposed to prompt injection attacks

### 2. **Gateway Headers**

**Secure:** Tracking headers (`X-Tenant-Id`) are:
- Set by server, not user input
- Used for attribution, not authorization
- Not visible to LLM

### 3. **API Keys**

**Secure:** API keys are:
- Read from environment variables
- Never logged or exposed in events
- Managed by provider SDKs (langchain-*)

### 4. **Tool Execution**

**Risk:** LLM controls tool calls

**Mitigations:**
- Validate tool inputs (use Pydantic schemas)
- Rate-limit expensive tools
- Sandbox file system tools
- Audit tool usage via observability

---

## Future Enhancements

### Phase 2 (Planned)

1. **MCP Protocol Support**
   - Extract `MCPLoader` and `MCPConfig`
   - Client for MCP gateway
   - Tool discovery and invocation

2. **Multi-agent Swarm**
   - Extract Swarm orchestrator
   - Agent handoffs
   - Task decomposition

3. **Conversation Debugging**
   - Add `debug.py` with conversation serialization
   - JSON dumps for inspection
   - Replay capabilities

4. **Knowledge Graph Integration**
   - Entity extraction
   - Relationship mapping
   - Graph-enhanced RAG

### Community Requests

- [ ] Streaming cancellation support
- [ ] Built-in retry logic for tool failures
- [ ] Agent-to-agent communication protocol
- [ ] OpenTelemetry tracing integration
- [ ] Custom prompt templates
- [ ] Tool result caching

---

## Conclusion

The Cortex Orchestration SDK is a **production-grade, LangGraph-based agent framework** with:

✅ **Clean architecture** - Layered, testable, extensible
✅ **Zero autogen dependencies** - Pure LangGraph
✅ **Battle-tested** - Extracted from ml-infra production code
✅ **Multi-provider** - OpenAI, Anthropic, Google, Gateway
✅ **Secure** - Context injection prevents prompt leakage
✅ **Observable** - Comprehensive token tracking
✅ **Flexible** - High-level and low-level APIs

**Ready for:** Agent orchestration, RAG integration, multi-agent systems, production deployments.

---

**Maintained by:** Cortex-AI Team
**License:** MIT
**Source:** Extracted from Harness ml-infra (orchestration_sdk)
