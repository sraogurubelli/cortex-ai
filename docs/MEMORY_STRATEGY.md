# Memory Strategy for Cortex AI

**Date**: 2026-03-19
**Status**: Design Proposal
**Based on**: ml-infra memory patterns + TallyGo knowledge graph concepts

---

## 🎯 Executive Summary

**Goal**: Implement comprehensive memory capabilities in cortex-ai to enable agents to remember, learn, and build upon previous interactions across multiple sessions.

**Current State**:
- ✅ LangGraph checkpointer (session persistence)
- ❌ No semantic memory layer
- ❌ No domain-specific memory structures
- ❌ No long-term memory beyond checkpoints

**Proposed Solution**:
Multi-layered memory architecture with **3 memory types**:
1. **Session Memory** (short-term, current conversation)
2. **Semantic Memory** (medium-term, domain knowledge)
3. **Knowledge Memory** (long-term, persistent facts)

---

## 📊 Current State Analysis

### What Cortex-AI Has

| Component | Status | Location | Quality |
|-----------|--------|----------|---------|
| LangGraph Checkpointer | ✅ Complete | `cortex/orchestration/session/checkpointer.py` | Production-ready |
| PostgreSQL persistence | ✅ Complete | Integrated | Production-ready |
| MemorySaver (dev mode) | ✅ Complete | Built-in | Works |
| Health checks | ✅ Complete | `is_checkpointer_healthy()` | Good |
| Thread management | ✅ Complete | `build_thread_id()` | Good |
| Cleanup operations | ✅ Complete | `cleanup_old_checkpoints()` | Good |

**Assessment**: Strong foundation for session persistence, but **lacks semantic memory layer**.

### What ml_infra Has (That We Need)

| Pattern | File | Purpose | Adoptable? |
|---------|------|---------|------------|
| **KG Session Store** | `capabilities/tools/knowledge_graph/session_store.py` | Domain-specific memory for multi-turn analysis | ✅ Yes |
| **PreviousAnalysis** | Data structures for compressed context | Semantic memory objects | ✅ Yes |
| **Context Formatting** | `format_previous_context()` | Convert memory to LLM-readable format | ✅ Yes |
| **TTL-based Expiry** | Session context with 1-hour TTL | Automatic cleanup | ✅ Yes |
| **Conversation History Dumping** | `orchestration_sdk/observability/conversation.py` | Debug/analysis | ✅ Yes |

**Key Insight**: ml_infra has a **semantic memory layer** on top of checkpointer for domain-specific knowledge.

---

## 🏗️ Proposed Architecture

### Three-Layer Memory System

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Knowledge Memory (Long-Term)                      │
│  - Persistent facts about users, projects, entities         │
│  - Neo4j/Vector DB integration                              │
│  - Cross-session, cross-agent shared knowledge              │
│  - TTL: Months/Years                                        │
└─────────────────────────────────────────────────────────────┘
                          ↑
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Semantic Memory (Medium-Term)                     │
│  - Domain-specific compressed context                       │
│  - Previous analyses, decisions, patterns                   │
│  - Session-scoped, but structured                           │
│  - TTL: Hours/Days                                          │
└─────────────────────────────────────────────────────────────┘
                          ↑
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Session Memory (Short-Term)                       │
│  - LangGraph checkpoints (current implementation)           │
│  - Full conversation state                                  │
│  - Thread-scoped                                            │
│  - TTL: Minutes/Hours                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Layer 1: Session Memory (✅ Already Implemented)

### Current Implementation

**File**: `cortex/orchestration/session/checkpointer.py`

**Capabilities**:
- LangGraph state persistence
- PostgreSQL or MemorySaver backend
- Thread-based isolation
- Health checks
- Automatic cleanup

**Usage**:
```python
from cortex.orchestration.session import get_checkpointer
from cortex.orchestration import Agent

checkpointer = get_checkpointer()
agent = Agent(name="assistant", checkpointer=checkpointer)

# Automatically persists conversation state
result = await agent.run("Hello", thread_id="session-123")
result2 = await agent.run("Continue conversation", thread_id="session-123")
```

**What It Stores**:
- Full conversation messages (user, assistant, tool)
- Agent state snapshots
- LangGraph node execution history

**✅ No changes needed** - this layer is production-ready.

---

## 📦 Layer 2: Semantic Memory (⚠️ TO IMPLEMENT)

### Purpose

Store **compressed, domain-specific context** that agents can reference across turns without re-processing.

### Key Concepts (from ml_infra)

#### 1. Memory Objects

```python
@dataclass
class PreviousInteraction:
    """Compressed context from a previous agent interaction."""

    timestamp: float
    user_query: str
    agent_reasoning: str
    key_decisions: List[str]
    tools_used: List[ToolExecution]
    outcome: str
    confidence: float


@dataclass
class ToolExecution:
    """Record of a tool execution."""

    tool_name: str
    parameters: dict
    result_summary: str  # Compressed, not full result
    success: bool
```

#### 2. Semantic Store

```python
class SemanticMemory:
    """
    Domain-specific memory layer for agents.

    Stores compressed interaction history with TTL-based expiry.
    Uses PostgreSQL or in-memory fallback.
    """

    async def save_interaction(
        self,
        conversation_id: str,
        user_query: str,
        agent_reasoning: str,
        decisions: List[str],
        tools_used: List[ToolExecution],
        outcome: str,
        ttl_seconds: int = 3600,
    ) -> None:
        """Save compressed interaction for future reference."""

    async def load_context(
        self,
        conversation_id: str,
        max_interactions: int = 5,
    ) -> List[PreviousInteraction]:
        """Load previous interactions for this conversation."""

    def format_for_llm(
        self,
        interactions: List[PreviousInteraction]
    ) -> str:
        """Format memory as LLM-readable context."""
```

#### 3. Context Injection

```python
from cortex.orchestration import Agent
from cortex.orchestration.memory import SemanticMemory

semantic_memory = SemanticMemory()

# Load previous context
previous_interactions = await semantic_memory.load_context("conv-123")

# Format for LLM
if previous_interactions:
    context = semantic_memory.format_for_llm(previous_interactions)
    system_prompt = f"{base_prompt}\n\n{context}"
else:
    system_prompt = base_prompt

# Run agent with injected context
agent = Agent(name="assistant", system_prompt=system_prompt)
result = await agent.run(user_query, thread_id="conv-123")

# Save new interaction
await semantic_memory.save_interaction(
    conversation_id="conv-123",
    user_query=user_query,
    agent_reasoning=result.metadata.get("reasoning", ""),
    decisions=extract_decisions(result),
    tools_used=extract_tool_executions(result),
    outcome=result.response,
)
```

### Benefits

✅ **Reduced Token Usage**: Compress 10K token conversation → 500 token summary
✅ **Faster Context Loading**: Don't re-process old interactions
✅ **Better Continuity**: Agent remembers key decisions/patterns
✅ **Cost Optimization**: Less prompt tokens, more cache hits

### Storage Strategy

**Option 1: PostgreSQL Table** (Recommended)
```sql
CREATE TABLE semantic_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    user_query TEXT NOT NULL,
    agent_reasoning TEXT,
    key_decisions JSONB,
    tools_used JSONB,
    outcome TEXT,
    confidence FLOAT,
    expires_at TIMESTAMP,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_expires_at (expires_at)
);

-- Auto-cleanup old entries
DELETE FROM semantic_memory WHERE expires_at < NOW();
```

**Option 2: Shared Checkpointer Table**
- Add custom metadata to existing checkpoints
- Piggyback on checkpoint infrastructure
- Simpler deployment

---

## 📦 Layer 3: Knowledge Memory (🔮 FUTURE)

### Purpose

Persistent facts about **entities** (users, projects, companies) that agents can query across sessions.

### Architecture

```
Agent Query → Semantic Search (Vector DB) → Retrieve Facts → Inject into Context
                        ↓
                  Neo4j Knowledge Graph
                   (Relationships)
```

### Example Use Cases

1. **User Preferences**:
   ```python
   # Agent remembers across sessions
   "User prefers Python over JavaScript"
   "User works in EST timezone"
   "User's company uses AWS, not GCP"
   ```

2. **Project Context**:
   ```python
   # Shared across team members
   "Project X uses microservices architecture"
   "Database is PostgreSQL 15 with pgvector"
   "Deployment is via Kubernetes on EKS"
   ```

3. **Decision History**:
   ```python
   # Why was this decision made?
   "Chose Redis over Memcached because of pub/sub requirement"
   "Migration to Python 3.11 delayed due to legacy dependencies"
   ```

### Integration with TallyGo Billing Knowledge Graph

From your RAMP prep doc, you have a **billing/logistics knowledge graph**:

```
Entities: Invoice, Customer, Payment, Trip, Driver, Vehicle
Relationships:
  - Invoice → belongs_to → Customer
  - Payment → settles → Invoice
  - Trip → generates → Invoice
  - Driver → operates → Vehicle
```

**Cortex AI Integration**:
```python
from cortex.orchestration.memory import KnowledgeGraph

kg = KnowledgeGraph(neo4j_url="...")

# Agent queries knowledge graph
entities = await kg.find_related(
    entity_type="Invoice",
    entity_id="INV-12345",
    relationship_types=["belongs_to", "settled_by"],
    max_hops=2
)

# Inject into agent context
context = kg.format_entity_context(entities)
agent = Agent(
    name="billing-agent",
    system_prompt=f"{base_prompt}\n\n{context}"
)
```

**Benefits**:
- Agents understand business domain
- Cross-reference entities naturally
- Explain decisions with evidence chains
- Generate audit trails

---

## 🛠️ Implementation Roadmap

### Phase 1: Semantic Memory Foundation (Weeks 1-2)

**Goal**: Add compressed interaction memory to cortex-ai

**Tasks**:
1. Create `cortex/orchestration/memory/` directory
2. Implement `SemanticMemory` class
3. Define memory data structures (`PreviousInteraction`, `ToolExecution`)
4. PostgreSQL schema for semantic_memory table
5. TTL-based expiry logic
6. Context formatting for LLMs

**Files to Create**:
- `cortex/orchestration/memory/__init__.py`
- `cortex/orchestration/memory/semantic.py`
- `cortex/orchestration/memory/types.py`
- `cortex/orchestration/memory/formatters.py`

**Integration**:
- Add to `Agent.run()` as optional parameter
- Automatic save after each interaction
- Load on agent initialization

**Success Criteria**:
- Agent remembers previous 5 interactions
- Token usage reduced by 50% on multi-turn conversations
- No impact on response quality

### Phase 2: Memory Middleware (Weeks 3-4)

**Goal**: Automatic memory injection via middleware

**Tasks**:
1. Create `MemoryMiddleware` class
2. Auto-load semantic memory on agent initialization
3. Auto-save after agent completion
4. Configurable memory depth (how many previous interactions)
5. Memory compression strategies (summarization)

**Files to Create**:
- `cortex/orchestration/middleware/memory.py`

**Usage**:
```python
from cortex.orchestration.middleware import MemoryMiddleware

agent = Agent(
    name="assistant",
    middleware=[
        MemoryMiddleware(
            max_interactions=5,
            ttl_hours=24,
            compression="summarize"  # or "full"
        )
    ]
)

# Memory automatically loaded and saved
result = await agent.run("query", thread_id="conv-123")
```

### Phase 3: Knowledge Graph Integration (Month 2)

**Goal**: Connect to Neo4j/Vector DB for long-term knowledge

**Tasks**:
1. Create `KnowledgeGraph` adapter
2. Vector search for semantic retrieval
3. Entity extraction from conversations
4. Automatic knowledge update
5. Query optimization

**Files to Create**:
- `cortex/orchestration/memory/knowledge_graph.py`
- `cortex/orchestration/memory/vector_store.py`

**Integration with Existing RAG**:
- Leverage existing `cortex/rag/embeddings.py`
- Add Neo4j connector
- Unified retrieval API

### Phase 4: Multi-Agent Memory Sharing (Month 3)

**Goal**: Share knowledge across agents in swarms

**Tasks**:
1. Shared memory namespace
2. Agent-specific vs shared memory
3. Permission controls (which agents can read/write)
4. Conflict resolution (when agents disagree)

**Architecture**:
```python
# Shared knowledge pool
shared_memory = SemanticMemory(namespace="project-alpha")

# Agent 1 learns something
researcher = Agent(name="researcher", shared_memory=shared_memory)
await researcher.run("Find technical requirements")

# Agent 2 uses that knowledge
implementer = Agent(name="implementer", shared_memory=shared_memory)
await implementer.run("Implement the solution")
# → Automatically knows requirements from researcher
```

---

## 💡 Design Patterns from ml_infra

### Pattern 1: Graceful Degradation

ml_infra uses **PostgreSQL with in-memory fallback**:

```python
_memory_store: dict[str, str] = {}  # In-memory fallback

async def _get_pool():
    try:
        if is_checkpointing_enabled() and _pool is not None:
            return _pool
    except ImportError:
        pass
    return None

# Always works, even without DB
data = await load_from_postgres() or load_from_memory()
```

**Adopt for cortex-ai**: Same pattern in `SemanticMemory`.

### Pattern 2: Compressed Context

ml_infra stores **summaries, not full content**:

```python
@dataclass
class PreviousQuery:
    title: str          # "Find unpaid invoices"
    hql: str            # "MATCH (i:Invoice) WHERE ..."
    row_count: int      # 42
    finding: str        # "Found 42 unpaid invoices totaling $125K"
    # NOT: full 10K row result
```

**Adopt for cortex-ai**: Compress tool outputs, keep only key findings.

### Pattern 3: TTL-Based Expiry

ml_infra expires context after 1 hour:

```python
_CONTEXT_TTL_SECONDS = 3600

analyses_data = [
    a for a in analyses_data
    if now - a.get("timestamp", 0) < _CONTEXT_TTL_SECONDS
]
```

**Adopt for cortex-ai**: Configurable TTL based on use case.

### Pattern 4: Max Items Limit

ml_infra keeps only last N interactions:

```python
MAX_ANALYSES_PER_CONVERSATION = 5

existing = existing[-MAX_ANALYSES_PER_CONVERSATION:]
```

**Adopt for cortex-ai**: Prevent unbounded memory growth.

---

## 📊 Expected Impact

### Cost Reduction

**Scenario**: Agent with 20-turn conversation

**Without Semantic Memory**:
- Turn 1: 2K tokens (system) + 500 (user) = 2500 tokens
- Turn 10: 2K + 500 + 15K (history) = 17.5K tokens
- Turn 20: 2K + 500 + 35K (history) = 37.5K tokens
- **Average**: 20K tokens/turn
- **Total**: 400K input tokens

**With Semantic Memory**:
- Turn 1: 2K + 500 = 2500 tokens
- Turn 10: 2K + 500 + 1K (compressed) = 3500 tokens
- Turn 20: 2K + 500 + 1.5K (compressed) = 4K tokens
- **Average**: 3.5K tokens/turn
- **Total**: 70K input tokens

**Savings**: 82.5% token reduction = ~80% cost savings on multi-turn conversations

### Performance Improvement

- **Faster Context Loading**: 100ms vs 500ms (less data to serialize)
- **Better Cache Hits**: Stable system prompt = more caching
- **Reduced Latency**: Smaller prompts = faster LLM processing

---

## 🔒 Security Considerations

### Data Privacy

1. **PII Redaction**: Automatically redact sensitive data before storing
2. **Encryption**: Encrypt semantic memory at rest
3. **TTL Enforcement**: Strict expiry to comply with data retention policies
4. **User Controls**: Allow users to delete their memory

### Access Control

1. **Namespace Isolation**: Agent A can't read Agent B's private memory
2. **Role-Based Access**: Admin agents vs user agents
3. **Audit Logging**: Track who accessed what memory

---

## 📚 References

### ml_infra Patterns
- `ml-infra/capabilities/tools/knowledge_graph/session_store.py` - Semantic memory implementation
- `ml-infra/unified_chat/session/checkpointer.py` - PostgreSQL checkpointer
- `ml-infra/orchestration_sdk/observability/conversation.py` - Conversation dumping

### TallyGo Context
- Knowledge graph for billing/logistics domain
- Evidence chains for decision explanation
- Multi-entity relationships

### LangChain/LangGraph
- Memory patterns: https://python.langchain.com/docs/modules/memory/
- Checkpointers: https://langchain-ai.github.io/langgraph/concepts/persistence/

---

## 🚀 Next Steps

**Immediate (This Week)**:
1. Review this design with team
2. Decide on Phase 1 scope
3. Create initial data structures

**Short-Term (Month 1)**:
1. Implement `SemanticMemory` class
2. PostgreSQL schema
3. Integration with `Agent`

**Medium-Term (Month 2-3)**:
1. Memory middleware
2. Knowledge graph integration
3. Multi-agent sharing

**Long-Term (Quarter 2)**:
1. Advanced compression (LLM-based summarization)
2. Vector search for semantic retrieval
3. Cross-session knowledge persistence

---

**Questions for Discussion**:
1. Should semantic memory be opt-in or default?
2. What TTL makes sense for different use cases?
3. Do we need multi-tenancy isolation?
4. How to handle memory conflicts in swarms?
5. Integration with existing TallyGo knowledge graph?

**Document Status**: Draft for Review
**Author**: Based on ml_infra patterns and TallyGo requirements
**Last Updated**: 2026-03-19
