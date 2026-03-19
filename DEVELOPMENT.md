# Cortex-AI Development Guide

This guide provides detailed information for developers working on Cortex-AI.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Development Setup](#development-setup)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Database](#database)
- [API Development](#api-development)
- [Agent & Orchestration](#agent--orchestration)
- [Debugging](#debugging)
- [Release Process](#release-process)

## Architecture Overview

Cortex-AI is an enterprise-grade AI platform with the following layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                       │
│              (Web, Mobile, API Consumers)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   API Layer (FastAPI)                        │
│  - Authentication (JWT)                                      │
│  - Authorization (RBAC)                                      │
│  - Routes (Auth, Accounts, Orgs, Projects, Chat)            │
└────────┬──────────────┬──────────────┬─────────────────────┘
         │              │              │
    ┌────▼───┐    ┌────▼────┐    ┌───▼────┐
    │Platform│    │Orchestr.│    │  RAG   │
    │        │    │         │    │        │
    └────┬───┘    └────┬────┘    └───┬────┘
         │             │              │
┌────────▼─────────────▼──────────────▼────────────────────────┐
│                   Data Layer                                  │
│  - PostgreSQL (OLTP)                                          │
│  - Qdrant (Vector Search)                                     │
│  - Redis (Cache)                                              │
│  - Neo4j (Knowledge Graph)                                    │
└────────────────────────────────────────────────────────────────┘
```

### Technology Stack

**Core Framework:**
- Python 3.11+
- FastAPI 0.115+ (async REST API)
- SQLAlchemy 2.0 (async ORM)
- Pydantic v2 (validation)

**LLM Integration:**
- OpenAI SDK (GPT models)
- Anthropic SDK (Claude models)
- Google Cloud AI Platform (Vertex AI)
- LangGraph (agent orchestration)

**Data Stores:**
- PostgreSQL 16 (OLTP database)
- Redis 7 (caching, sessions)
- Qdrant 1.16+ (vector search)
- Neo4j 5 (knowledge graphs)

**Development Tools:**
- Black 25.1.0 (code formatter)
- Ruff 0.8+ (linter)
- Mypy 1.13+ (type checker)
- Pytest 8.3+ (testing)
- Pre-commit (git hooks)

## Project Structure

```
cortex-ai/
├── cortex/                     # Main Python package
│   ├── platform/               # Platform features
│   │   ├── auth/               # Authentication & RBAC
│   │   ├── config/             # Configuration management
│   │   └── database/           # Database models & repositories
│   ├── orchestration/          # Agent orchestration SDK
│   │   ├── agent.py            # High-level Agent API
│   │   ├── tools.py            # Tool registry
│   │   ├── session/            # Session persistence
│   │   └── mcp/                # MCP protocol support
│   ├── rag/                    # RAG module
│   │   ├── embeddings.py       # Embedding service
│   │   ├── vector_store.py     # Qdrant integration
│   │   └── graph/              # GraphRAG (Neo4j)
│   ├── api/                    # FastAPI application
│   │   ├── main.py             # Application entry point
│   │   ├── routes/             # API route handlers
│   │   └── middleware/         # Middleware (auth, logging)
│   └── core/                   # Core utilities
│       └── streaming/          # SSE streaming
├── tests/                      # Test suite
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests
├── examples/                   # Example applications
├── .github/                    # GitHub configuration
│   └── workflows/              # CI/CD workflows
├── Taskfile.yml                # Task automation (go-task)
├── docker-compose.yml          # Local development stack
├── pyproject.toml              # Python package configuration
└── .env.example                # Environment variable template
```

### Import Conventions

```python
# Standard library imports
import asyncio
import uuid
from datetime import datetime

# Third-party imports
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Local imports - use absolute imports from cortex
from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import get_db, Project
from cortex.orchestration import Agent, ModelConfig
```

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/cortex-ai.git
cd cortex-ai
```

### 2. Install Task Runner

```bash
# macOS
brew install go-task

# Linux
sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d

# Verify installation
task --version
```

### 3. Install Dependencies

```bash
task install
```

This installs:
- Python dependencies from `pyproject.toml`
- Pre-commit hooks

### 4. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
vim .env
```

Required environment variables:
```bash
# Security
JWT_SECRETS=secret1,secret2,secret3  # Generate with: openssl rand -hex 32
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=postgresql://cortex:password@localhost:5432/cortex

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### 5. Start Infrastructure

```bash
task docker:up
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Qdrant (port 6333)
- Neo4j (ports 7474, 7687)

### 6. Initialize Database

```bash
task db:migrate
```

Creates all database tables.

### 7. Verify Setup

```bash
# Run tests
task test

# Check services
task docker:ps
```

### Troubleshooting

**Port conflicts:**
```bash
# Check what's using port 5432
lsof -i :5432

# Stop conflicting services
brew services stop postgresql
```

**Docker issues:**
```bash
# Reset Docker state
task docker:reset

# View logs
task docker:logs
```

**Database connection errors:**
```bash
# Verify PostgreSQL is running
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Reset database
task db:reset
```

## Running the Application

### Development Server

```bash
# Start server (auto-reload enabled)
task dev
```

Server runs at: http://localhost:8000
- API docs: http://localhost:8000/api/docs
- Health check: http://localhost:8000/health

### Debug Mode

```bash
# Enable debug logging
task dev:debug
```

This sets:
- `DEBUG=true`
- `LOG_LEVEL=DEBUG`

### Hot Reload

FastAPI automatically reloads on code changes when running via `task dev`.

Watched directories:
- `cortex/`
- `.env`

### Environment Configurations

**Development (`APP_ENV=development`):**
- Debug enabled
- Auto-reload enabled
- API docs enabled
- In-memory checkpointer (optional)

**Staging (`APP_ENV=staging`):**
- Debug disabled
- API docs enabled
- PostgreSQL checkpointer

**Production (`APP_ENV=production`):**
- Debug disabled
- API docs disabled
- PostgreSQL checkpointer
- Structured logging

## Testing

### Test Structure

```
tests/
├── unit/                       # Fast, isolated tests
│   ├── platform/
│   │   ├── test_auth.py
│   │   └── test_database.py
│   ├── orchestration/
│   │   └── test_agent.py
│   └── rag/
│       └── test_embeddings.py
└── integration/                # Tests requiring services
    ├── api/
    │   ├── test_auth_api.py
    │   └── test_chat_api.py
    └── database/
        └── test_repositories.py
```

### Running Tests

```bash
# All tests
task test

# Unit tests only (fast)
task test:unit

# Integration tests (require Docker)
task test:integration

# With coverage report
task test:coverage

# Quick unit tests (excludes slow tests)
task test:quick

# Watch mode (run tests on file changes)
task test:watch
```

### Writing Tests

**Unit Test Example:**
```python
import pytest
from cortex.platform.auth import has_permission, Permission

def test_role_permissions():
    """Test role-permission mappings."""
    assert has_permission("owner", Permission.ACCOUNT_DELETE)
    assert has_permission("admin", Permission.PROJECT_EDIT)
    assert not has_permission("reader", Permission.PROJECT_DELETE)
```

**Integration Test Example:**
```python
import pytest
from httpx import AsyncClient
from cortex.api.main import app

@pytest.mark.asyncio
async def test_signup_endpoint():
    """Test user signup creates account and organization."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/auth/signup", json={
            "email": "test@example.com",
            "display_name": "Test User",
            "password": "securepass123",
            "organization_name": "Test Org",
        })

    assert response.status_code == 201
    data = response.json()
    assert data["principal"]["email"] == "test@example.com"
    assert "access_token" in data
```

### Test Fixtures

Common fixtures in `tests/conftest.py`:

```python
@pytest.fixture
async def db_session():
    """Provide database session for tests."""
    # Setup
    session = await create_test_session()
    yield session
    # Teardown
    await session.close()

@pytest.fixture
def test_user(db_session):
    """Create test user."""
    user = Principal(email="test@example.com", ...)
    db_session.add(user)
    await db_session.commit()
    return user
```

### Mocking

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_llm_call():
    """Test LLM integration with mocking."""
    with patch('cortex.orchestration.llm.LLMClient.generate') as mock_generate:
        mock_generate.return_value = AsyncMock(response="Mocked response")

        agent = Agent(name="test", model=ModelConfig(model="gpt-4o"))
        result = await agent.run("test message")

        assert result.response == "Mocked response"
        mock_generate.assert_called_once()
```

## Code Quality

### Formatting

```bash
# Auto-format code
task format
```

This runs:
1. **Black** - Code formatter (100-char line length)
2. **Ruff** - Import sorting and auto-fixes

### Linting

```bash
# Run all linters
task lint
```

This runs:
1. **Ruff** - Fast Python linter
2. **Mypy** - Static type checker
3. **Bandit** - Security vulnerability scanner

### Type Checking

```bash
# Type check only
task type-check
```

Mypy configuration in `pyproject.toml`:
```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # Gradually enable
```

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`:

```bash
# Run hooks manually
task pre-commit

# Update hooks
task pre-commit:update
```

Hooks configured in `.pre-commit-config.yaml`:
- Trailing whitespace removal
- YAML/JSON/TOML validation
- Black formatting
- Ruff linting
- File size checks
- Security checks (Bandit)

### Security Scanning

```bash
# Scan dependencies for vulnerabilities
pip-audit
```

Run automatically in CI via `.github/workflows/security.yml`.

## Database

### Schema Overview

**Entity Hierarchy:**
```
Account (billing entity)
  └── Organization (business unit)
      └── Project (workspace)
          ├── Conversation (AI chat session)
          │   └── Message (chat message)
          └── Document (RAG document)
```

**RBAC:**
```
Principal (user/service account)
  └── Membership (role on resource)
      └── Role (owner, admin, contributor, reader)
```

### Models

SQLAlchemy models in `cortex/platform/database/models.py`:

```python
class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    uid = Column(String(255), unique=True)
    status = Column(Enum(AccountStatus))
    organizations = relationship("Organization", back_populates="account")
```

### Repositories

Repository pattern in `cortex/platform/database/repositories/`:

```python
class AccountRepository(BaseRepository[Account]):
    async def find_by_uid(self, uid: str) -> Optional[Account]:
        result = await self.session.execute(
            select(Account).where(Account.uid == uid)
        )
        return result.scalar_one_or_none()
```

Usage in routes:
```python
@router.get("/accounts/{uid}")
async def get_account(
    uid: str,
    session: AsyncSession = Depends(get_db),
):
    repo = AccountRepository(session)
    account = await repo.find_by_uid(uid)
    if not account:
        raise HTTPException(404, "Account not found")
    return account
```

### Migrations

We use SQLAlchemy's `Base.metadata.create_all()` for now.

**Run migrations:**
```bash
task db:migrate
```

**Future:** Alembic for versioned migrations.

### Database Tasks

```bash
# Open PostgreSQL shell
task db:shell

# Dump database
task db:dump

# Restore from dump
task db:restore

# Reset database (drop and recreate)
task db:reset
```

## API Development

### Adding New Endpoints

1. **Define request/response models** in route file:
```python
class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None

class ProjectInfo(BaseModel):
    id: str
    name: str
    created_at: datetime
```

2. **Create route handler** with RBAC:
```python
@router.post("/organizations/{org_uid}/projects", response_model=ProjectInfo)
async def create_project(
    org_uid: str,
    request: CreateProjectRequest,
    principal: Principal = Depends(
        require_permission(Permission.ORG_CREATE_PROJECT, "organization", "org_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    # Implementation
    ...
```

3. **Register router** in `cortex/api/main.py`:
```python
from cortex.api.routes import projects

app.include_router(projects.router)
```

### Authentication

JWT tokens extracted from:
1. `Authorization: Bearer <token>` header
2. Basic auth (`<token>:`)
3. Query param (`?token=<token>`)
4. Cookie (`token=<token>`)

**Require authentication:**
```python
from cortex.api.middleware.auth import require_authentication

@router.get("/protected")
async def protected_route(
    principal: Principal = Depends(require_authentication()),
):
    return {"user_id": principal.uid}
```

### Authorization (RBAC)

**Permission check:**
```python
from cortex.platform.auth import Permission, require_permission

@router.delete("/projects/{uid}")
async def delete_project(
    uid: str,
    principal: Principal = Depends(
        require_permission(Permission.PROJECT_DELETE, "project", "uid")
    ),
):
    # Only users with PROJECT_DELETE permission can access this
    ...
```

**Available permissions:**
- `ACCOUNT_*` - View, Edit, Delete, Manage Billing, Manage Members
- `ORG_*` - View, Edit, Delete, Manage Members, Create Project
- `PROJECT_*` - View, Edit, Delete, Manage Members
- `CONVERSATION_*` - View, Create, Edit, Delete
- `DOCUMENT_*` - View, Upload, Edit, Delete
- `APIKEY_*` - View, Create, Delete

### Error Handling

**HTTPException for API errors:**
```python
from fastapi import HTTPException, status

if not resource:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Resource not found",
    )
```

**Global exception handler** in `cortex/api/main.py` catches unhandled exceptions.

## Agent & Orchestration

### Agent SDK Usage

**Simple agent:**
```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="assistant",
    system_prompt="You are a helpful AI assistant.",
    model=ModelConfig(model="gpt-4o"),
)

result = await agent.run("What is the capital of France?")
print(result.response)
```

**With tools:**
```python
from cortex.orchestration import Agent, ModelConfig, ToolRegistry

def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"

tool_registry = ToolRegistry()
tool_registry.register(search_web)

agent = Agent(
    name="assistant",
    model=ModelConfig(model="gpt-4o"),
    tool_registry=tool_registry,
)

result = await agent.run("Search for Python best practices")
```

### Creating Custom Tools

```python
from typing import Annotated
from cortex.orchestration import ToolRegistry

tool_registry = ToolRegistry()

@tool_registry.register
def calculate_sum(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

@tool_registry.register
def get_user_data(
    user_id: Annotated[str, "Injected from context"],
    query: str,
) -> dict:
    """
    Fetch user-specific data.

    Args with Annotated["Injected from context"] are server-side injected.
    LLM only sees and provides the 'query' parameter.
    """
    return {"user_id": user_id, "data": "..."}

# Set context values (injected server-side)
tool_registry.set_context(user_id="usr_123")
```

### Session Persistence

**PostgreSQL checkpointer:**
```python
from cortex.orchestration.session.checkpointer import get_checkpointer

agent = Agent(
    name="assistant",
    model=ModelConfig(model="gpt-4o"),
    checkpointer=get_checkpointer(),  # Persistent across requests
)

# Multi-turn conversation
result1 = await agent.run("My name is Alice", thread_id="conv-1")
result2 = await agent.run("What is my name?", thread_id="conv-1")
# Response: "Your name is Alice"
```

### SSE Streaming

```python
from cortex.orchestration import Agent
from cortex.core.streaming.stream_writer import StreamWriter, create_streaming_response

stream_writer = StreamWriter()

async def stream_agent():
    result = await agent.stream_to_writer(
        message="Tell me about AI",
        stream_writer=stream_writer,
        thread_id="conv-1",
    )
    await stream_writer.close()

# FastAPI route
return await create_streaming_response(stream_writer)
```

## Debugging

### Using IPython/IPdb

```python
# Add breakpoint in code
import ipdb; ipdb.set_trace()

# Or use Python 3.7+ breakpoint()
breakpoint()
```

### Logging

**Configure logging level:**
```bash
export LOG_LEVEL=DEBUG
task dev
```

**Add logging in code:**
```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)
```

### Common Pitfalls

1. **Async/Await Mixing**
   ```python
   # ❌ Wrong
   result = agent.run("message")  # Missing await

   # ✅ Correct
   result = await agent.run("message")
   ```

2. **Database Session Commits**
   ```python
   # ❌ Wrong
   await repo.create(entity)
   # Session not committed!

   # ✅ Correct
   await repo.create(entity)
   await session.commit()
   ```

3. **Context Injection**
   ```python
   # ❌ Wrong - user_id from request body (security issue!)
   tool_registry.set_context(user_id=request.json["user_id"])

   # ✅ Correct - user_id from authenticated principal
   tool_registry.set_context(user_id=principal.uid)
   ```

## Release Process

### Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** - Breaking changes
- **MINOR** - New features (backward compatible)
- **PATCH** - Bug fixes (backward compatible)

### Creating a Release

1. **Update version** in `pyproject.toml`:
   ```toml
   [project]
   version = "0.2.0"
   ```

2. **Update CHANGELOG.md:**
   ```markdown
   ## [0.2.0] - 2024-03-10

   ### Added
   - New feature X

   ### Fixed
   - Bug Y

   ### Changed
   - Improvement Z
   ```

3. **Commit and tag:**
   ```bash
   git commit -m "chore: bump version to 0.2.0"
   git tag v0.2.0
   git push origin main --tags
   ```

4. **Create GitHub Release** with changelog

### Future: PyPI Publishing

```bash
# Build package
python -m build

# Upload to PyPI
python -m twine upload dist/*
```

---

For contributor guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).
