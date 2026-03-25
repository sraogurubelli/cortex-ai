# Cortex-AI

**Production-ready AI orchestration platform with multi-agent coordination and RAG**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Cortex-AI is a standalone, open-source platform extracted from production systems (Harness ml-infra) that provides battle-tested AI orchestration, multi-agent swarm coordination, and Retrieval-Augmented Generation (RAG) capabilities.

## ✨ Features

### Core Orchestration ✅ Complete
- 🤖 **Single-Agent Orchestration** - LangGraph-based agent execution
- 🤝 **Multi-Agent Swarm** - Automatic handoffs and specialization
- 💬 **Streaming Responses** - Real-time SSE streaming with event suppression
- 🔌 **Multi-Provider LLMs** - OpenAI, Anthropic, Google, VertexAI
- 🛠️ **MCP Integration** - Model Context Protocol for external tools
- 🔧 **Context Injection** - Security pattern for sensitive parameters
- 📊 **Token Tracking** - Cost attribution with cache metrics

### Production Features ✅ Complete
- ⚡ **Prompt Caching** - 90% cost reduction (Anthropic)
- 🔍 **HTTP Request Logging** - Debug LLM provider calls
- 📡 **OpenTelemetry** - Distributed tracing
- ✅ **Validation Tools** - Schema validation
- 📦 **Conversation Compression** - LLM-based summarization
- 💾 **Session Persistence** - PostgreSQL-backed state
- 🎯 **Middleware System** - Pre/post hooks for LLM/tool calls
- 🔁 **Retry & Rate Limiting** - Production reliability

### Chat Interaction ✅ Complete
- 📎 **Attachments** - File references on chat messages
- 🏷️ **Smart Titles** - LLM-generated conversation titles
- 🔍 **Search** - Full-text search across conversations
- 👍 **Ratings** - Thumbs up/down with feedback per message
- 📥 **Export** - JSON and Markdown conversation export
- 🔄 **Regeneration** - Replay from any user message
- ⏹️ **Stop** - Cancel in-progress generation
- 🔗 **UI Actions** - Frontend continuations (navigate, create entity)
- 📝 **Citations** - Structured source attribution from RAG
- 🛡️ **Safety** - Input/output guardrails, PII redaction, token budget

### RAG Module ✅ Complete
- 🔍 **Semantic Search** - Qdrant vector database
- 🧠 **Embedding Service** - OpenAI with Redis caching (90% cost savings)
- 📚 **Document Management** - Lifecycle and chunking
- 🔀 **Hybrid Search** - Vector + keyword
- 🏢 **Multi-Tenancy** - Tenant isolation
- 🤖 **Agent Integration** - RAG-enhanced chatbots

### GraphRAG (Knowledge Graphs) ✅ Complete
- 🕸️ **Knowledge Graph** - Neo4j integration with automatic entity extraction
- 📊 **Entity Extraction** - LLM-based concept and relationship extraction
- 🔍 **Graph Search** - Concept-based retrieval with multi-hop traversal
- 🔀 **Hybrid GraphRAG** - Vector + graph search with RRF fusion
- 🎯 **Multi-Tenancy** - Tenant-isolated knowledge graphs

### Planned
- 📊 **Analytics Layer** - StarRocks OLAP for real-time analytics
- 📡 **Event Streaming** - Kafka integration for async workflows

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for Qdrant, Redis)
- OpenAI API key (for LLMs and embeddings)
- Anthropic API key (optional, for Claude)

### Installation

```bash
# Clone the repository
cd cortex-ai

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# For RAG: Start Qdrant and Redis
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
docker run -d --name redis -p 6379:6379 redis:7

# Set environment variables
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

### Basic Agent Usage

```python
from cortex.orchestration import Agent, ModelConfig

# Create agent
agent = Agent(
    name="assistant",
    system_prompt="You are a helpful assistant.",
    model=ModelConfig(model="gpt-4o", use_gateway=False),
)

# Run agent
result = await agent.run("What is Python?")
print(result.response)

# Streaming
async for event in agent.stream("Explain quantum computing"):
    if event.type == "on_chat_model_stream":
        print(event.data["chunk"].content, end="")
```

### Multi-Agent Swarm Example

```python
from cortex.orchestration import Swarm, Agent, ModelConfig

# Create specialized agents
researcher = Agent(
    name="researcher",
    system_prompt="You research topics and gather information.",
    model=ModelConfig(model="gpt-4o"),
)

writer = Agent(
    name="writer",
    system_prompt="You write clear, concise summaries.",
    model=ModelConfig(model="gpt-4o"),
)

# Create swarm with automatic handoffs
swarm = Swarm(agents=[researcher, writer])
result = await swarm.run(
    "Research quantum computing and write a summary",
    initial_agent=researcher,
)
```

### RAG Example

```python
from cortex.rag import EmbeddingService, VectorStore, DocumentManager, Retriever
from cortex.orchestration import Agent, ModelConfig

# Initialize RAG components
embeddings = EmbeddingService(openai_api_key="sk-...")
await embeddings.connect()

vector_store = VectorStore(url="http://localhost:6333")
await vector_store.connect()
await vector_store.create_collection()

doc_manager = DocumentManager(embeddings=embeddings, vector_store=vector_store)

# Ingest documents
await doc_manager.ingest_document(
    doc_id="python-intro",
    content="Python is a high-level programming language...",
    metadata={"source": "docs"},
)

# Search
retriever = Retriever(embeddings=embeddings, vector_store=vector_store)
results = await retriever.search("What is Python?", top_k=3)

# Use with Agent for RAG
async def search_knowledge_base(query: str) -> str:
    """Search the knowledge base."""
    results = await retriever.search(query, top_k=3)
    return retriever.format_context(results, max_tokens=1000)

agent = Agent(
    name="rag-assistant",
    system_prompt="Use search_knowledge_base to find information before answering.",
    model=ModelConfig(model="gpt-4o"),
    tools=[search_knowledge_base],
)

result = await agent.run("Tell me about Python")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Client Applications                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                   API Gateway (FastAPI)                         │
└─────┬──────────────────┬──────────────────┬─────────────────────┘
      │                  │                  │
┌─────▼─────┐   ┌────────▼────────┐  ┌─────▼──────────┐
│  Agent    │   │   Multi-Agent   │  │   RAG Service  │
│Orchestrator│   │  Coordinator    │  │   (Search)     │
└─────┬─────┘   └────────┬────────┘  └─────┬──────────┘
      │                  │                  │
┌─────▼──────────────────▼──────────────────▼─────────────────────┐
│                    Tool Execution Layer                         │
└─────┬──────────────────┬──────────────────┬─────────────────────┘
      │                  │                  │
┌─────▼──────────────────▼──────────────────▼─────────────────────┐
│               Data Platform (PostgreSQL, Qdrant, Redis)         │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
cortex-ai/
├── cortex/
│   ├── api/                        # FastAPI application
│   │   ├── main.py                # App factory, middleware, lifespan
│   │   ├── middleware/            # Auth (JWT), metrics (Prometheus)
│   │   └── routes/
│   │       ├── chat.py            # Core chat endpoints (stream, sync)
│   │       ├── chat_extensions.py # Search, ratings, export, regenerate, stop
│   │       ├── documents.py       # Document upload and RAG ingestion
│   │       ├── agents.py          # Agent CRUD
│   │       ├── skills.py          # Skill management
│   │       └── ...                # auth, accounts, orgs, projects, models, traces
│   │
│   ├── orchestration/              # Agent orchestration SDK
│   │   ├── agent.py               # High-level Agent API
│   │   ├── swarm.py               # Multi-agent swarm
│   │   ├── llm.py                 # LLM provider clients
│   │   ├── tools.py               # Tool registry with context injection
│   │   ├── streaming.py           # SSE streaming + event types
│   │   ├── caching/               # Prompt caching (Anthropic, Google, OpenAI)
│   │   ├── middleware/            # Middleware system (memory, summarization)
│   │   ├── session/               # SessionOrchestrator + checkpointer
│   │   ├── safety/                # Guardrails, PII redaction, token budget
│   │   ├── skills/                # Progressive skill disclosure (SKILL.md)
│   │   ├── memory/                # Semantic memory (cross-session)
│   │   ├── ui_actions/            # UI action schemas, emitters, continuations
│   │   ├── observability/         # OpenTelemetry + Langfuse
│   │   └── mcp/                   # MCP protocol support
│   │
│   ├── platform/                   # Platform services
│   │   ├── auth/                  # RBAC, permissions, JWT
│   │   ├── config/                # Settings (env-driven)
│   │   └── database/             # SQLAlchemy models + repositories
│   │
│   ├── prompts/                    # Jinja2 prompt registry
│   ├── tools/                      # Built-in tools (doc search, code exec)
│   └── rag/                        # RAG Module
│       ├── embeddings.py          # Embedding service (OpenAI + Redis)
│       ├── vector_store.py        # Qdrant vector database
│       ├── document.py            # Document lifecycle
│       ├── retriever.py           # Semantic search
│       └── graph_rag/             # Neo4j knowledge graph RAG
│
├── examples/                       # Comprehensive examples
├── docs/                           # Documentation
│   ├── CHAT_API.md                # Chat interaction API reference
│   ├── ORCHESTRATION_ARCHITECTURE.md  # Architecture guide
│   ├── QUICK_START.md             # Getting started
│   ├── RAG.md                     # RAG documentation
│   └── ...                        # Memory, GraphRAG, prompt caching guides
│
├── requirements.txt                # Dependencies
└── README.md                       # This file
```

## Core Modules

### Orchestration SDK

**Single-Agent:**
```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="assistant",
    model=ModelConfig(model="gpt-4o"),
)
result = await agent.run("Hello!")
```

**Multi-Agent Swarm:**
```python
from cortex.orchestration import Swarm, Agent

swarm = Swarm(agents=[agent1, agent2])
result = await swarm.run("Complex task", initial_agent=agent1)
```

**MCP Tools:**
```python
from cortex.orchestration.mcp import MCPLoader, MCPHttpConfig

loader = MCPLoader()
tools = await loader.load_tools(
    MCPHttpConfig(url="http://localhost:3000")
)
agent = Agent(name="assistant", tools=tools)
```

### RAG Module

**Document Ingestion:**
```python
from cortex.rag import DocumentManager

await doc_manager.ingest_document(
    doc_id="doc-1",
    content="...",
    metadata={"source": "docs"},
)
```

**Semantic Search:**
```python
from cortex.rag import Retriever

results = await retriever.search(
    query="...",
    top_k=5,
    filter={"source": "docs"},
)
```

**RAG with Agent:**
```python
async def search_kb(query: str) -> str:
    results = await retriever.search(query)
    return retriever.format_context(results)

agent = Agent(name="rag", tools=[search_kb])
```

## Development

### Running Tests

```bash
# Unit tests
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# All tests with coverage
pytest --cov=cortex --cov-report=html
```

### Code Quality

```bash
# Format code
black cortex/ tests/

# Lint
ruff check cortex/ tests/

# Type checking
mypy cortex/
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Configuration

### Environment Variables

See [.env.example](.env.example) for all configuration options:

- `OPENAI_API_KEY` - OpenAI API key for embeddings
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `QDRANT_URL` - Qdrant vector database URL

### Docker Compose

The `docker-compose.yml` includes:
- PostgreSQL 16 (OLTP)
- Qdrant 1.16+ (Vector search)
- Redis 7 (Caching)

## Examples

See the [examples/](examples/) directory for comprehensive demos:

**Core Orchestration:**
- `orchestration_demo.py` - 5 basic agent demos
- `swarm_demo.py` - 3 multi-agent swarm demos
- `advanced_features_demo.py` - 7 advanced feature demos

**Production Features:**
- `test_caching.py` - Prompt caching (cost optimization)
- `test_http_logging.py` - HTTP request logging
- `test_validation.py` - Schema validation tools
- `test_telemetry.py` - OpenTelemetry tracing
- `test_compression.py` - Conversation compression
- `test_session_persistence.py` - PostgreSQL-backed state
- `test_middleware.py` - Middleware system

**RAG:**
- `test_rag.py` - 7 comprehensive RAG demos

Total: **52+ individual demos** across 10 example files

## Documentation

Comprehensive documentation with 35,000+ words:

- **[CHAT_API.md](docs/CHAT_API.md)** - Chat interaction API reference (endpoints, SSE events, schemas, safety)
- **[ORCHESTRATION_ARCHITECTURE.md](docs/ORCHESTRATION_ARCHITECTURE.md)** - 12,000-word architecture deep dive
- **[QUICK_START.md](docs/QUICK_START.md)** - 5-minute getting started guide
- **[RAG.md](docs/RAG.md)** - Complete RAG documentation
- **[COMPLETION_SUMMARY.md](docs/COMPLETION_SUMMARY.md)** - Implementation summary

## Roadmap

### ✅ Phase 1 - Core Orchestration (Complete)
- [x] Repository setup and structure
- [x] Single-agent orchestration (LangGraph)
- [x] Multi-provider LLM support (OpenAI, Anthropic, Google, VertexAI)
- [x] Tool execution with context injection
- [x] Streaming responses (SSE)
- [x] Token tracking and cost attribution
- [x] Comprehensive documentation (35,000+ words)
- [x] 52+ example demos

### ✅ Phase 1.5 - Production Features (Complete)
- [x] Prompt caching (90% cost reduction)
- [x] HTTP request logging
- [x] Enhanced tool registry with pattern matching
- [x] Validation tools
- [x] OpenTelemetry integration (distributed tracing)
- [x] Conversation compression (LLM-based summarization)
- [x] Session persistence (PostgreSQL-backed state)
- [x] Middleware system (pre/post hooks)

### ✅ Phase 2 - Multi-Agent & RAG (Complete)
- [x] Multi-agent swarm with automatic handoffs
- [x] MCP protocol support for external tools
- [x] RAG module with Qdrant vector store
- [x] Embedding service with Redis caching
- [x] Document lifecycle management
- [x] Semantic and hybrid search
- [x] Multi-tenancy support

### ✅ Phase 3 - Platform API & Security (Complete)
- [x] FastAPI REST API layer with RBAC
- [x] SSE streaming endpoints (part streaming, full message)
- [x] JWT authentication and project-level authorization
- [x] SessionOrchestrator (checkpoint health, message dedup, Langfuse spans)
- [x] Knowledge graph integration (Neo4j GraphRAG)
- [x] Safety & guardrails (input/output guardrails, PII redaction, token budget)
- [x] Trace sanitization for observability tools

### ✅ Phase 4 - Complete Chat Interaction (Complete)
- [x] Chat attachments (file references on messages)
- [x] LLM-based conversation title generation
- [x] Conversation search (full-text on titles + message content)
- [x] Message ratings / reactions (thumbs up/down with feedback)
- [x] Conversation export (JSON and Markdown)
- [x] Message regeneration (replay from a specific point)
- [x] Stop/cancel in-progress generation
- [x] System events / UI action continuations
- [x] Typing indicators + structured citations in SSE
- [x] Skills middleware + semantic memory wired into orchestrator

### 🚧 Phase 5 - Scale & Analytics (Planned)
- [ ] Unit and integration tests (90%+ coverage)
- [ ] Analytics layer (StarRocks OLAP)
- [ ] Event streaming (Kafka)
- [ ] Dashboard generation

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 📧 Email: sraogurubelli@gmail.com
- 💬 Discussions: [GitHub Discussions](https://github.com/yourusername/cortex-ai/discussions)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/cortex-ai/issues)

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [Qdrant](https://qdrant.tech/) - Vector database
- [Anthropic Claude](https://www.anthropic.com/) - LLM provider
- [OpenAI](https://openai.com/) - Embeddings and LLM

---

**Made with ❤️ by the open-source community**
