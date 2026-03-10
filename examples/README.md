# Cortex-AI Examples

This directory contains example applications demonstrating the capabilities of Cortex-AI.

## Prerequisites

```bash
# Set API keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."  # Optional
export GOOGLE_API_KEY="..."           # Optional
```

## Examples

### 1. [`orchestration_demo.py`](orchestration_demo.py) - Core Features

Foundational orchestration SDK features:

**Demo 1: Basic Agent Usage** - Creating agents with tools, running queries, token tracking
**Demo 2: Context Injection** - Automatic parameter injection, security best practices
**Demo 3: Streaming** - SSE streaming, real-time responses
**Demo 4: Low-level API** - Direct LangGraph usage with AgentConfig + build_agent
**Demo 5: Multi-turn Conversation** - Stateful conversations, checkpointer usage

```bash
python orchestration_demo.py
```

---

### 2. [`swarm_demo.py`](swarm_demo.py) - Multi-Agent Swarm

Multi-agent orchestration with automatic handoffs:

**Demo 1: Simple Swarm** - Two-agent system with handoffs (general ↔ specialist)
**Demo 2: Research & Writing Team** - Specialized agents with tool distribution
**Demo 3: Customer Support** - Multi-tier escalation (tier1 → tier2 → billing)

**Key Features:**
- Automatic handoff tool injection
- Agent specialization
- Conversation routing
- Context preservation across handoffs

```bash
python swarm_demo.py
```

---

### 3. [`advanced_features_demo.py`](advanced_features_demo.py) - Advanced Features

Production-grade capabilities:

**Demo 1: Retry Logic** - Automatic retries for flaky tools with exponential backoff
**Demo 2: Rate Limiting** - Token bucket rate limiting for expensive operations
**Demo 3: Context Injection** - Security demo - hiding sensitive params from LLM
**Demo 4: Conversation Debugging** - Dumping full history to JSON for inspection
**Demo 5: Token Tracking** - Comprehensive usage metrics across multi-turn conversations
**Demo 6: Event Suppression** - UI control - hiding tool events for end-users

```bash
python advanced_features_demo.py
```

---

## Feature Matrix

| Feature | Basic Demo | Swarm Demo | Advanced Demo |
|---------|------------|------------|---------------|
| Single Agent | ✅ | | ✅ |
| Multi-Agent | | ✅ | |
| Tool Calling | ✅ | ✅ | ✅ |
| Streaming | ✅ | | ✅ |
| Context Injection | ✅ | | ✅ |
| Token Tracking | ✅ | | ✅ |
| Retry Logic | | | ✅ |
| Rate Limiting | | | ✅ |
| Debugging | | | ✅ |
| Handoffs | | ✅ | |

---

## Running All Examples

```bash
# Run all demos
python orchestration_demo.py
python swarm_demo.py
python advanced_features_demo.py
```

---

## Next Steps

1. **Read architecture docs:** [`docs/ORCHESTRATION_ARCHITECTURE.md`](../docs/ORCHESTRATION_ARCHITECTURE.md)
2. **Quick start guide:** [`docs/QUICK_START.md`](../docs/QUICK_START.md)
3. **Build your own agents:** Customize examples for your use case

---

## Coming Soon

- **RAG Examples**: Document ingestion, semantic search, hybrid retrieval with Qdrant
- **MCP Examples**: Model Context Protocol integration, custom MCP servers
- **Production Examples**: FastAPI integration, authentication, deployment patterns
- **Knowledge Graph Examples**: Neo4j integration, entity extraction, graph-enhanced RAG
