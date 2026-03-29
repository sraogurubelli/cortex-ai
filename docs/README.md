# Cortex-AI Documentation

Complete documentation for the Cortex-AI platform.

## Quick Start

- **[Executive Brief](EXECUTIVE_BRIEF.md)** - High-level overview and value proposition
- **[Quick Start Guide](guides/QUICK_START.md)** - Get started in 5 minutes
- **[Claude Code Guide](CLAUDE_CODE_GUIDE.md)** - Development with Claude Code

## Architecture

Deep-dive into system architecture and design decisions:

- **[Orchestration Architecture](architecture/ORCHESTRATION_ARCHITECTURE.md)** - Multi-agent orchestration, LangGraph integration
- **[Document Processing Architecture](architecture/DOCUMENT_PROCESSING_ARCHITECTURE.md)** - Multi-format parsing, chunking, embeddings
- **[Reasoning Layer Architecture](architecture/REASONING_LAYER_ARCHITECTURE.md)** - Agent reasoning and decision-making
- **[Context Engineering & Knowledge Graphs](architecture/CONTEXT_ENGINEERING_AND_KNOWLEDGE_GRAPHS.md)** - GraphRAG and entity extraction

## User Guides

Practical guides for using Cortex-AI features:

### Core Features
- **[Chat API](guides/CHAT_API.md)** - REST API and WebSocket chat endpoints
- **[RAG](guides/RAG.md)** - Retrieval-Augmented Generation setup and usage
- **[GraphRAG](guides/GRAPHRAG.md)** - Knowledge graph-enhanced retrieval
- **[Memory Strategy](guides/MEMORY_STRATEGY.md)** - Memory middleware and semantic memory

### Advanced Features
- **[Prompt Caching](guides/PROMPT_CACHING_GUIDE.md)** - 90% cost reduction with prompt caching
- **[Research Tools](guides/RESEARCH_TOOLS.md)** - Built-in research capabilities

## Documentation Philosophy

**We don't maintain implementation summaries** - implementation details belong in:
- Code comments and docstrings
- Architecture docs (for design decisions)
- Git commit history (for change rationale)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.

## Project Structure

```
cortex-ai/
├── cortex/              # Core platform code
│   ├── api/            # FastAPI application
│   ├── orchestration/  # Agent orchestration
│   ├── rag/            # RAG and document processing
│   └── platform/       # Auth, database, utilities
├── docs/               # This directory
│   ├── architecture/   # Architecture deep-dives
│   └── guides/         # User guides
├── examples/           # Runnable examples
└── tests/              # Test suites
```

---

**Last Updated:** March 2026
