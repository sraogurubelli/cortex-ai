# Cortex-AI Development Guide

**Production AI orchestration platform with multi-agent support**

@../README.md
@../CONTRIBUTING.md

---

## Quick Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Type check
mypy cortex/

# Start API server
uvicorn cortex.api.app:app --reload --port 8000

# Run examples
python examples/orchestration_demo.py
```

---

## Project Structure

```
cortex/
├── orchestration/  # Multi-agent orchestration (Agent, ModelConfig, LangGraph)
├── api/            # FastAPI Chat API with SSE streaming
├── rag/            # GraphRAG, vector stores, embeddings
├── memory/         # Memory middleware, checkpointing
├── tools/          # MCP integration and tool registry
├── platform/       # Platform features
└── skills/         # Global skills (future)
```

---

## Development Rules

See `.claude/rules/` for detailed, path-specific guidelines:
- **orchestration.md** - Agent development patterns (async/await, tools, context injection)
- **api.md** - API endpoint conventions (FastAPI, SSE, error handling)
- **rag.md** - RAG query optimization (GraphRAG, embeddings, retrieval)
- **memory.md** - Memory middleware patterns (checkpointing, session persistence)
- **testing.md** - Test requirements (pytest-asyncio, mocking, coverage)

**How it works:** These rules auto-load when you work with matching files. For example, editing `cortex/orchestration/agent.py` automatically loads `orchestration.md` guidelines.

---

## Tech Stack

- **Python:** 3.11+ (specified in pyproject.toml)
- **Framework:** FastAPI for API, LangGraph for orchestration
- **LLMs:** Multi-provider (OpenAI, Anthropic, Google, Vertex AI)
- **Database:** PostgreSQL for persistence, Neo4j for GraphRAG
- **Vector Store:** Chroma, Pinecone, or custom
- **Async:** All agent operations use async/await

---

## Code Style

- Use **type hints** for all function signatures
- Follow **PEP 8** (enforced by ruff)
- **Docstrings** for all public functions (Google style)
- **Async/await** for I/O operations
- Keep functions **< 50 lines** (prefer smaller, focused functions)

---

## Key Patterns

### 1. Agent Creation

```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="assistant",
    description="General purpose assistant",
    system_prompt="You are a helpful assistant specialized in...",
    model=ModelConfig(model="gpt-4o", temperature=0.7),
    tools=[tool1, tool2],  # Optional
)

result = await agent.run("Query", thread_id="session-id")
```

### 2. Secure Context Injection

```python
from cortex.orchestration import ToolRegistry

# ✅ Good: Server-side context (LLM never sees user_id)
registry = ToolRegistry()
registry.set_context(user_id=request.user_id)
agent = Agent(tool_registry=registry, tools=None)

# ❌ Bad: LLM controls user_id
# Never: system_prompt = f"User ID is {user_id}"
```

### 3. Error Handling

```python
try:
    result = await agent.run(query)
except Exception as e:
    logger.error(f"Agent error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Agent execution failed")
```

### 4. SSE Streaming

```python
from cortex.orchestration import SimpleStreamWriter

writer = SimpleStreamWriter()
result = await agent.stream_to_writer(query, stream_writer=writer)
```

---

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/orchestration/test_agent.py -v

# Run with coverage
pytest --cov=cortex --cov-report=html tests/

# Run async tests
pytest tests/ -v -k "asyncio"
```

**Coverage Target:** 80% minimum

---

## Environment Setup

```bash
# Required environment variables
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."  # Optional

# Database (for GraphRAG)
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"

# PostgreSQL (for checkpointing)
export DATABASE_URL="postgresql://user:pass@localhost/cortex"
```

---

## Available Skills

Skills in `.claude/skills/` (invoke with `/skill-name`):

- **`/orchestration-dev`** - Agent development patterns and best practices
- **`/rag-query`** - GraphRAG query optimization and debugging
- **`/api-endpoint`** - Create Chat API endpoints with SSE streaming

**New to skills?** See [docs/CLAUDE_CODE_GUIDE.md](../docs/CLAUDE_CODE_GUIDE.md)

---

## Documentation

- [Quick Start](../docs/QUICK_START.md) - Get started in 5 minutes
- [Orchestration Architecture](../docs/ORCHESTRATION_ARCHITECTURE.md) - Deep dive
- [Memory Strategy](../docs/MEMORY_STRATEGY.md) - Memory patterns
- [GraphRAG](../docs/GRAPHRAG.md) - Knowledge graph implementation
- [Chat API](../docs/CHAT_API.md) - API endpoints
- [Claude Code Guide](../docs/CLAUDE_CODE_GUIDE.md) - CLAUDE.md, Skills reference

---

## Critical DON'Ts

- ❌ Never block on `agent.run()` without `await`
- ❌ Never put `user_id` in system prompts (use context injection)
- ❌ Never create new `thread_id` for every message (loses context)
- ❌ Never skip error handling on agent calls
- ❌ Never ignore token usage (monitor costs)
- ❌ Never commit `.env` files or API keys
- ❌ Never force push to main/master
- ❌ Never skip pre-commit hooks (`--no-verify`)

---

## Git Workflow

- **Branch naming:** `feature/description` or `fix/description`
- **Commit format:** `type: description` (feat, fix, chore, docs, test)
- **Default branch:** `main`
- **Before committing:** Run `pytest tests/` and `mypy cortex/`

---

## Need Help?

- Check `.claude/rules/` for path-specific guidelines
- Use `/orchestration-dev` skill for agent development
- See [docs/CLAUDE_CODE_GUIDE.md](../docs/CLAUDE_CODE_GUIDE.md) for complete reference
- Review [examples/](../examples/) for working code samples

---

**Last Updated:** March 2026
