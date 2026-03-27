---
paths:
  - "tests/**/*.py"
---

# Testing Requirements

**Auto-loads when:** Working with test files

---

## Test Structure

```
tests/
├── orchestration/       # Agent, tools, model config tests
├── api/                 # API endpoint tests
├── rag/                 # Vector store, GraphRAG tests
├── memory/              # Memory middleware, checkpointing tests
├── integration/         # Integration tests
└── conftest.py          # Shared fixtures
```

---

## Async Testing with pytest-asyncio

✅ **All async tests must use `@pytest.mark.asyncio`:**

```python
import pytest
from cortex.orchestration import Agent, ModelConfig

@pytest.mark.asyncio
async def test_agent_execution():
    """Test agent can execute simple query."""
    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("Say hello")

    assert result.response is not None
    assert "hello" in result.response.lower()
    assert "gpt-4o" in result.token_usage
```

❌ **Don't forget the marker:**

```python
# ❌ Wrong - Will not run as async
async def test_agent_execution():
    agent = Agent(...)
    result = await agent.run("Hello")  # Will hang or error
```

---

## Fixtures (conftest.py)

✅ **Share common setup in conftest.py:**

```python
# tests/conftest.py
import pytest
from cortex.orchestration import Agent, ModelConfig
from cortex.rag import VectorStore
from cortex.memory import PostgresSaver

@pytest.fixture
async def test_agent():
    """Reusable test agent without persistence."""
    return Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

@pytest.fixture
async def test_agent_with_memory():
    """Test agent with in-memory checkpointer."""
    checkpointer = PostgresSaver(connection_string="sqlite:///:memory:")
    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o"),
        checkpointer=checkpointer,
    )
    yield agent
    # Cleanup
    await checkpointer.clear_all()

@pytest.fixture
def mock_tool():
    """Mock tool for testing."""
    from langchain_core.tools import tool

    @tool
    def calculator(operation: str, a: float, b: float) -> str:
        """Perform math operations."""
        ops = {
            "add": lambda x, y: x + y,
            "multiply": lambda x, y: x * y,
        }
        return str(ops[operation](a, b))

    return calculator

@pytest.fixture
async def vector_store():
    """In-memory vector store for testing."""
    store = VectorStore(connection_string="sqlite:///:memory:")
    await store.initialize()
    yield store
    await store.close()
```

---

## Mocking External Services

### Mock LLM Providers

```python
from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.asyncio
async def test_agent_with_mocked_llm():
    """Test agent with mocked LLM response."""
    with patch("cortex.orchestration.llm.OpenAIProvider") as mock_provider:
        # Setup mock
        mock_instance = AsyncMock()
        mock_instance.generate.return_value = "Mocked response"
        mock_provider.return_value = mock_instance

        # Create agent
        agent = Agent(
            name="test_agent",
            model=ModelConfig(model="gpt-4o"),
        )

        result = await agent.run("Test query")

        # Assertions
        assert result.response == "Mocked response"
        mock_instance.generate.assert_called_once()

@pytest.mark.asyncio
async def test_api_endpoint_with_mock_agent():
    """Test API endpoint with mocked agent service."""
    from httpx import AsyncClient
    from cortex.api.app import app

    with patch("cortex.api.dependencies.get_agent_service") as mock_service:
        # Setup mock
        mock_service.return_value.process_message = AsyncMock(
            return_value={
                "response": "Test response",
                "tokens": {"gpt-4o": {"total": 100}},
            }
        )

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat",
                json={"message": "Hello", "session_id": "test"},
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert response.json()["message"] == "Test response"
```

---

## Coverage Requirements

**Target: 80% minimum**

```bash
# Run tests with coverage
pytest --cov=cortex --cov-report=html --cov-report=term tests/

# View HTML report
open htmlcov/index.html
```

✅ **What to cover:**
- All business logic (agents, tools, RAG, memory)
- API endpoints (request/response, validation, errors)
- Error handling paths
- Edge cases

❌ **What to skip:**
- Third-party library code
- Configuration files
- Migration scripts
- Simple getters/setters

---

## Test Categories

### Unit Tests

**Purpose:** Test individual functions in isolation

```python
@pytest.mark.asyncio
async def test_embedding_generation():
    """Test embedding generation for single text."""
    from cortex.rag import Embedder

    embedder = Embedder(model="text-embedding-ada-002")
    text = "Sample text for embedding"

    embedding = await embedder.embed(text)

    assert isinstance(embedding, list)
    assert len(embedding) == 1536  # OpenAI embedding dimension
    assert all(isinstance(x, float) for x in embedding)

@pytest.mark.asyncio
async def test_chunk_text():
    """Test text chunking with overlap."""
    from cortex.rag import TextChunker

    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    text = "Lorem ipsum " * 50  # Long text

    chunks = chunker.split_text(text)

    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
```

### Integration Tests

**Purpose:** Test component interactions

```python
@pytest.mark.asyncio
async def test_agent_with_rag():
    """Test agent using RAG for retrieval."""
    from cortex.orchestration import Agent, ModelConfig
    from cortex.rag import VectorStore
    from langchain_core.tools import tool

    # Setup vector store
    vector_store = VectorStore(connection_string="sqlite:///:memory:")
    await vector_store.initialize()

    # Add test documents
    await vector_store.add_documents([
        {"content": "Paris is the capital of France", "source": "test"},
        {"content": "Berlin is the capital of Germany", "source": "test"},
    ])

    # Create RAG tool
    @tool
    async def search_knowledge_base(query: str) -> str:
        """Search knowledge base."""
        results = await vector_store.similarity_search(query, k=1)
        return results[0].content if results else "No results found"

    # Create agent with tool
    agent = Agent(
        name="rag_agent",
        model=ModelConfig(model="gpt-4o"),
        tools=[search_knowledge_base],
    )

    result = await agent.run("What is the capital of France?")

    # Agent should use the tool and answer correctly
    assert "paris" in result.response.lower()

    # Cleanup
    await vector_store.close()
```

### End-to-End Tests

**Purpose:** Test full workflows

```python
@pytest.mark.asyncio
async def test_chat_workflow_e2e():
    """Test complete chat workflow from API to agent."""
    from httpx import AsyncClient
    from cortex.api.app import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        # First message
        response1 = await client.post(
            "/api/v1/chat",
            json={"message": "My name is Alice", "session_id": "e2e-test"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response1.status_code == 200

        # Follow-up message (should remember name)
        response2 = await client.post(
            "/api/v1/chat",
            json={"message": "What is my name?", "session_id": "e2e-test"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response2.status_code == 200
        assert "alice" in response2.json()["message"].lower()
```

---

## Test Naming Conventions

✅ **Good test names - Descriptive and specific:**

```python
def test_agent_returns_error_when_prompt_is_empty():
    pass

def test_vector_store_retrieves_top_k_results_by_similarity():
    pass

def test_api_endpoint_returns_401_for_invalid_token():
    pass

def test_memory_checkpointer_persists_conversation_across_runs():
    pass
```

❌ **Bad test names - Vague:**

```python
def test_agent():
    pass

def test_rag():
    pass

def test_api():
    pass
```

**Rule:** Test name should describe what is being tested and expected outcome.

---

## Assertions

✅ **Specific assertions:**

```python
@pytest.mark.asyncio
async def test_agent_response():
    agent = Agent(...)
    result = await agent.run("Hello")

    # ✅ Good - Specific assertions
    assert result.response is not None
    assert isinstance(result.response, str)
    assert len(result.response) > 0
    assert "gpt-4o" in result.token_usage
    assert result.token_usage["gpt-4o"]["total_tokens"] > 0
```

❌ **Weak assertions:**

```python
# ❌ Bad - Too weak
assert result  # What are we actually testing?
assert True    # Useless

# ❌ Bad - Try/except swallowing errors
try:
    result = await agent.run("Hello")
except:
    pass  # Test passes even if it fails!
```

---

## Cleanup and Teardown

✅ **Always cleanup resources:**

```python
@pytest.fixture
async def database_connection():
    """Database connection with cleanup."""
    conn = await create_connection()
    yield conn
    await conn.close()

@pytest.mark.asyncio
async def test_with_cleanup():
    """Test with explicit cleanup."""
    checkpointer = PostgresSaver(...)
    agent = Agent(..., checkpointer=checkpointer)

    try:
        # Test code
        result = await agent.run("Test")
        assert result.response is not None
    finally:
        # Cleanup
        await checkpointer.clear_all()
        await checkpointer.close()
```

---

## Parametrized Tests

✅ **Test multiple scenarios efficiently:**

```python
import pytest

@pytest.mark.parametrize(
    "model,expected_provider",
    [
        ("gpt-4o", "openai"),
        ("claude-sonnet-4", "anthropic"),
        ("gemini-2.0-flash", "google"),
    ],
)
@pytest.mark.asyncio
async def test_model_provider_detection(model: str, expected_provider: str):
    """Test provider is detected correctly from model name."""
    from cortex.orchestration import ModelConfig

    config = ModelConfig(model=model)

    assert config.provider == expected_provider

@pytest.mark.parametrize(
    "operation,a,b,expected",
    [
        ("add", 5, 7, "12"),
        ("multiply", 3, 4, "12"),
        ("add", -1, 1, "0"),
    ],
)
def test_calculator_tool(operation: str, a: float, b: float, expected: str):
    """Test calculator tool with different operations."""
    from tests.conftest import mock_tool

    tool = mock_tool()
    result = tool.invoke({"operation": operation, "a": a, "b": b})

    assert result == expected
```

---

## Common Patterns

### Pattern 1: Test Error Handling

```python
@pytest.mark.asyncio
async def test_agent_handles_empty_message():
    """Test agent raises error for empty message."""
    agent = Agent(...)

    with pytest.raises(ValueError, match="Message cannot be empty"):
        await agent.run("")

@pytest.mark.asyncio
async def test_api_returns_400_for_invalid_input():
    """Test API returns 400 for invalid input."""
    from httpx import AsyncClient
    from cortex.api.app import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "", "session_id": "test"},  # Invalid
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 400
    assert "validation_error" in response.json()["error"]
```

### Pattern 2: Test Idempotency

```python
@pytest.mark.asyncio
async def test_embedding_is_idempotent():
    """Test same text produces same embedding."""
    embedder = Embedder(...)
    text = "Test text"

    embedding1 = await embedder.embed(text)
    embedding2 = await embedder.embed(text)

    assert embedding1 == embedding2
```

### Pattern 3: Test Thread Safety

```python
import asyncio

@pytest.mark.asyncio
async def test_concurrent_agent_requests():
    """Test agent handles concurrent requests safely."""
    agent = Agent(...)

    # Run 10 concurrent requests
    tasks = [agent.run(f"Query {i}") for i in range(10)]
    results = await asyncio.gather(*tasks)

    # All should succeed
    assert len(results) == 10
    assert all(r.response is not None for r in results)
```

---

## Best Practices Summary

✅ **Do:**
- Use `@pytest.mark.asyncio` for all async tests
- Share setup via fixtures in conftest.py
- Mock external services (LLMs, databases)
- Aim for 80%+ coverage
- Use descriptive test names
- Write specific assertions
- Clean up resources (fixtures, finally blocks)
- Parametrize similar tests
- Test error handling paths

❌ **Don't:**
- Skip async marker (test will fail)
- Forget to cleanup resources
- Use vague test names
- Write weak assertions
- Test third-party code
- Share state between tests
- Ignore flaky tests (fix them)
- Commit with failing tests

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/orchestration/test_agent.py -v

# Run specific test
pytest tests/orchestration/test_agent.py::test_agent_basic_execution -v

# Run with coverage
pytest --cov=cortex --cov-report=html tests/

# Run only fast tests (skip slow integration tests)
pytest -m "not slow" tests/

# Run in parallel (faster)
pytest -n auto tests/
```

---

## Reference Files

- [conftest.py](../../tests/conftest.py)
- [Test Examples](../../tests/orchestration/test_agent.py)
- [Testing Docs](../../docs/TESTING.md)
