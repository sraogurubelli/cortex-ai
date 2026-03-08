# Cortex-AI

**Enterprise-grade AI orchestration platform for multi-agent systems, RAG, and analytics**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Cortex-AI is a standalone, open-source platform that provides production-ready AI orchestration, multi-agent coordination, Retrieval-Augmented Generation (RAG), and data analytics capabilities.

## Features

### Phase 1 (Current)
- 🤖 **Single-Agent Orchestration** - Intelligent agent execution with tool calling
- 🔍 **RAG Foundation** - Vector search with Qdrant, hybrid search, embedding caching
- 💬 **Streaming Responses** - Real-time SSE streaming for chat interfaces
- 🔌 **Multi-Provider Support** - Anthropic, OpenAI, VertexAI integrations
- 🛠️ **MCP Integration** - Model Context Protocol for tool execution
- 🗄️ **Data Persistence** - PostgreSQL for OLTP, Redis for caching

### Phase 2 (Planned)
- 🤝 **Multi-Agent Coordination** - Task decomposition and parallel execution
- 🕸️ **Knowledge Graph** - Neo4j integration for semantic reasoning
- 📊 **Analytics Layer** - StarRocks OLAP for real-time analytics
- 📡 **Event Streaming** - Kafka integration for async workflows

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- OpenAI API key (for embeddings)
- Anthropic/OpenAI API key (for LLM)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/cortex-ai.git
cd cortex-ai

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[all]"

# Start infrastructure (PostgreSQL, Qdrant, Redis)
docker-compose up -d

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Initialize database
python scripts/setup_db.py

# Run the API server
uvicorn cortex.api.main:app --reload
```

### Basic Usage

```python
from cortex.core.agents import SingleAgent
from cortex.core.providers import AnthropicProvider

# Initialize agent
agent = SingleAgent(
    provider=AnthropicProvider(api_key="your-key"),
    model="claude-sonnet-4"
)

# Chat with streaming
async for chunk in agent.chat_stream("Explain quantum computing"):
    print(chunk, end="")
```

### RAG Example

```python
from cortex.search import DocumentService, SearchService

# Ingest documents
doc_service = DocumentService()
await doc_service.ingest_document(
    content="Quantum computing uses qubits...",
    metadata={"source": "docs"}
)

# Search
search_service = SearchService()
results = await search_service.search(
    query="What are qubits?",
    limit=5
)
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
├── cortex/                 # Main Python package
│   ├── core/              # Agent orchestration
│   ├── search/            # RAG service
│   ├── tools/             # Tool ecosystem
│   ├── storage/           # Data persistence
│   └── api/               # FastAPI application
├── sdk/                   # Client SDKs
├── examples/              # Example applications
├── tests/                 # Test suite
└── docs/                  # Documentation
```

## API Endpoints

### Agent Endpoints
```
POST   /api/v1/chat                    # Single-agent chat
POST   /api/v1/chat/stream             # Streaming chat
GET    /api/v1/conversations           # List conversations
```

### Search Endpoints
```
POST   /api/v1/search/documents        # Ingest document
POST   /api/v1/search                  # Semantic search
POST   /api/v1/search/hybrid           # Hybrid search
```

### Admin Endpoints
```
GET    /api/v1/health                  # Health check
GET    /api/v1/metrics                 # Prometheus metrics
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

See the [examples/](examples/) directory for:
- `simple_chat.py` - Basic chat interface
- `rag_chat.py` - RAG-powered Q&A
- `multi_agent_demo.py` - Multi-agent coordination (Phase 2)

## Documentation

- [Architecture](docs/architecture.md) - System design and patterns
- [API Reference](docs/api-reference.md) - Complete API documentation
- [Deployment](docs/deployment.md) - Production deployment guide

## Roadmap

### Phase 1 (Current) - Foundation
- [x] Repository setup
- [ ] Agent orchestration core
- [ ] RAG service
- [ ] FastAPI application
- [ ] Documentation
- [ ] Test coverage 90%+

### Phase 2 - Advanced Features
- [ ] Multi-agent coordination
- [ ] Knowledge graph integration
- [ ] Analytics layer (StarRocks)
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
