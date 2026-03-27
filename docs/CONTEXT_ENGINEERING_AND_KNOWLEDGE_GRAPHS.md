# Context Engineering and Knowledge Graphs

**A Deep-Dive Reference for AI Engineers**

This document covers the theory, patterns, architectures, and best practices behind two of the most important disciplines in modern AI systems: **context engineering** (how you manage and deliver information to LLMs) and **knowledge graphs** (how you structure and traverse relationships between entities). The final section explores their powerful intersection -- GraphRAG and structured memory.

Where relevant, we reference concrete implementations from the cortex-ai codebase to ground the theory in practice.

---

## Table of Contents

- [Part 1: Context Engineering](#part-1-context-engineering)
  - [1.1 What Is Context Engineering](#11-what-is-context-engineering)
  - [1.2 The Anatomy of Context](#12-the-anatomy-of-context)
  - [1.3 Context Management Strategies](#13-context-management-strategies)
  - [1.4 Retrieval-Augmented Generation (RAG)](#14-retrieval-augmented-generation-rag)
  - [1.5 Agentic Context Engineering](#15-agentic-context-engineering)
- [Part 2: Knowledge Graphs](#part-2-knowledge-graphs)
  - [2.1 Foundations](#21-foundations)
  - [2.2 Graph Databases](#22-graph-databases)
  - [2.3 Building Knowledge Graphs from Unstructured Data](#23-building-knowledge-graphs-from-unstructured-data)
  - [2.4 Querying and Reasoning](#24-querying-and-reasoning)
  - [2.5 Knowledge Graph Embeddings](#25-knowledge-graph-embeddings)
- [Part 3: The Intersection -- GraphRAG](#part-3-the-intersection----graphrag)
  - [3.1 Why Plain RAG Falls Short](#31-why-plain-rag-falls-short)
  - [3.2 GraphRAG Architecture](#32-graphrag-architecture)
  - [3.3 Structured Memory via Knowledge Graphs](#33-structured-memory-via-knowledge-graphs)
  - [3.4 Key Design Decisions](#34-key-design-decisions)
  - [3.5 Evaluation](#35-evaluation)
- [Further Reading](#further-reading)

---

# Part 1: Context Engineering

## 1.1 What Is Context Engineering

### Definition

Context engineering is the discipline of dynamically building and managing the **entire information payload** delivered to an LLM at inference time -- system instructions, conversation history, retrieved documents, tool results, structured memory, and metadata -- so the model has exactly the right information to produce the best output.

Think of it this way: an LLM is a powerful reasoning engine, but it can only reason over what it can see. Context engineering is the art of putting the right things in front of it.

### Why It Matters More Than Prompt Engineering

**Prompt engineering** focuses on *how you ask* -- phrasing, formatting, few-shot examples, chain-of-thought triggers. It optimizes the instruction layer.

**Context engineering** focuses on *what information surrounds the ask* -- which documents to retrieve, how much conversation history to include, what tool results to inject, which metadata to attach. It optimizes the entire information environment.

As models get smarter (GPT-4o, Claude Sonnet, Gemini), the bottleneck shifts. These models can follow complex instructions well -- the constraint is whether they have the right context. A perfectly worded prompt with missing context will produce a worse answer than a simple prompt with comprehensive context.

```
┌───────────────────────────────────────────────────────────┐
│                     Context Window                         │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  System Instructions (persona, constraints, format) │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │  Retrieved Knowledge (RAG chunks, graph results)    │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │  Conversation History (prior turns)                 │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │  Tool Results (API calls, code execution output)    │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │  User/Session Metadata (tenant, permissions, state) │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │  Current User Message + Instructions                │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ← This entire payload is "context engineering"           │
└───────────────────────────────────────────────────────────┘
```

### The Context Window as a Programming Surface

The context window (4K to 2M tokens depending on the model) is essentially a **function signature**. What you pass in determines what you get out. The model has no memory beyond what is in the window -- every inference call starts fresh. This means:

- **Every token matters.** Irrelevant context wastes capacity and can distract the model.
- **Ordering matters.** Models attend more strongly to the beginning and end of context (the "lost in the middle" effect).
- **Structure matters.** Well-organized context with clear headings, delimiters, and formatting improves comprehension.
- **Freshness matters.** Stale or contradictory context degrades output quality.

---

## 1.2 The Anatomy of Context

Every context payload sent to an LLM is composed of several distinct components. Understanding each one, its purpose, and its trade-offs is fundamental.

### System Instructions

The foundation layer. Defines *who* the model is and *how* it should behave.

| Aspect | Purpose | Example |
|--------|---------|---------|
| Persona | Define the model's role | "You are a senior DevOps engineer" |
| Constraints | Limit what the model can do | "Never execute destructive commands" |
| Output format | Structure the response | "Return JSON with fields: action, reason" |
| Guardrails | Safety and compliance | "Do not reveal internal API keys" |
| Domain knowledge | Persistent facts | "Our CI/CD pipeline uses Harness" |

System instructions are typically static per agent configuration and consume a fixed token budget.

### Conversation History

Multi-turn memory -- the record of what was said before. This is how the model maintains continuity across a conversation.

**Key tension:** Long conversations accumulate history that eventually exceeds the context window. Solutions include summarization (lossy compression), sliding windows (dropping old messages), and checkpointing (persisting state externally).

In cortex-ai, conversation state is persisted via LangGraph checkpoints backed by PostgreSQL (see `cortex/orchestration/session/checkpointer.py`). When a user resumes a conversation, the checkpointer loads the thread state rather than replaying the full message history.

### Retrieved Knowledge (RAG)

Documents, chunks, or passages pulled from external stores based on the current query. This is the most dynamic and impactful context component -- it brings in information the model was never trained on.

Sources include vector databases (Qdrant, Pinecone), graph databases (Neo4j), keyword indexes (Elasticsearch), and structured APIs.

### Tool/Function Results

Structured data returned from API calls, code execution, database queries, or other tools. In agentic systems, the model calls tools and the results flow back into context for the next reasoning step.

**Key challenge:** Tool results can be very large (a full database query result, a long code file). Naively including the full result wastes tokens. Strategies include truncation, summarization, and virtual filesystem eviction (storing the full result externally, placing a pointer in context).

### User/Session Metadata

Contextual information about who is asking and what state they are in:

- **Tenant ID, Project ID** -- for multi-tenancy isolation
- **Permissions / roles** -- what the user is allowed to see or do
- **Current page / UI state** -- what the user is looking at (crucial for copilot-style assistants)
- **Preferences** -- language, verbosity, expertise level

In cortex-ai, this metadata is propagated via Python `contextvars` so that any component (tools, middleware, retriever) can access it without explicit parameter passing. See `cortex/orchestration/context.py`:

```python
# Request-scoped context using contextvars
with request_context(
    tenant_id="acc_123",
    project_id="prj_456",
    principal_id="usr_789",
    conversation_id="conv_abc",
    stream_writer=writer,
):
    result = await agent.stream(...)

# Later, in a tool or middleware -- no parameter threading needed:
tenant_id = get_tenant_id()
```

### Few-Shot Examples

Demonstrations of desired input-output behavior. Particularly effective for:

- Complex output formats (JSON schemas, code generation)
- Domain-specific reasoning patterns
- Calibrating the model's style or tone

Few-shot examples trade token budget for output quality. As models improve, fewer examples are needed, but they remain valuable for precise formatting or unusual tasks.

### Scratchpad / Chain-of-Thought

Intermediate reasoning artifacts. In agentic loops, the model may produce multi-step reasoning:

1. Think about the problem (chain-of-thought)
2. Call a tool
3. Analyze the result
4. Decide next action

Each step generates tokens that become part of the context for subsequent steps. This is how agentic systems "think" -- but it also means the context grows with every iteration.

---

## 1.3 Context Management Strategies

The fundamental constraint: **there is almost always more potentially-relevant context than fits in the window.** The art of context engineering is deciding what to include, what to exclude, and what to compress.

### Summarization

Replace verbose content with compressed summaries. Two approaches:

**LLM-based summarization** -- Use a model to generate a summary of older messages or long documents. High quality, but adds latency and cost (an extra LLM call per summarization).

**Deterministic trimming** -- Drop old messages, keeping a structural skeleton. Fast and free, but lossy.

cortex-ai implements both strategies in `cortex/orchestration/middleware/summarization.py`:

```python
# LLM-based: model generates summary of older messages
mw = create_summarization_middleware(strategy="summarize", model=my_model)

# Deterministic: keep system message + first user message + N recent messages
mw = create_summarization_middleware(strategy="trim", keep_messages=15)
```

The `MessageTrimmingMiddleware` preserves the system message (always), the first user message (original question), and the N most recent messages. Everything in between is replaced with a compact marker: `"[42 earlier messages trimmed for context management]"`.

This is a pragmatic default -- the system message provides the agent's persona, the first user message provides the original intent, and recent messages provide the current state. The "lost middle" is the least critical.

### Eviction / Sliding Window

Drop the oldest messages once a threshold is exceeded. Simple and effective for streaming conversations where only recent context matters.

**Token-triggered eviction**: When total tokens exceed a threshold (e.g., 100K), drop the oldest messages. This is configurable via the `SUMMARIZATION_TOKEN_TRIGGER` environment variable.

**Message-count eviction**: When the number of messages exceeds a threshold (e.g., 40), trim to keep the most recent N.

### Token Budgeting

Allocate fixed token budgets to each context component:

```
Total context budget: 128K tokens
├── System instructions:  ~2K   (fixed)
├── Retrieved knowledge:  ~50K  (dynamic, based on query)
├── Conversation history: ~40K  (sliding window)
├── Tool results:         ~20K  (most recent tool calls)
├── Metadata:             ~1K   (fixed)
└── Reserved for output:  ~15K  (model response)
```

The key insight: **retrieval and history compete for the same finite resource.** A system that retrieves too aggressively leaves no room for conversation history, and vice versa. Token budgeting makes this trade-off explicit and tunable.

### Hierarchical Memory

Structure memory in layers with different lifespans and costs:

| Layer | Lifespan | Storage | Access Pattern |
|-------|----------|---------|----------------|
| **Working memory** | Current turn | In-context (the window itself) | Always present |
| **Session memory** | Current conversation | LangGraph checkpoints (Postgres) | Loaded on conversation resume |
| **Semantic memory** | Cross-session | Vector store + knowledge graph | Retrieved per query |
| **Long-term memory** | Permanent | Persistent knowledge base | Retrieved when relevant |

Working memory is free but ephemeral. Each subsequent layer is more durable but more expensive to access (requires a retrieval step).

In cortex-ai, the `SessionOrchestrator` (`cortex/orchestration/session/orchestrator.py`) manages the first two layers. It checks whether a checkpoint exists for the conversation thread -- if so, it loads the persisted state (avoiding replay of the full history). If the checkpointer is unhealthy, it gracefully falls back to building context from the conversation history passed by the caller.

### Compression

Advanced techniques for fitting more information into fewer tokens:

- **LLMLingua** -- Uses a small model to identify and remove low-information tokens from context, achieving 2-10x compression with minimal quality loss.
- **Auto-compressive memory** -- Models that can read a long context and produce a compressed representation (e.g., Gisting, AutoCompressors).
- **Structured extraction** -- Instead of passing raw text, extract key facts into a structured format (JSON, table) that conveys the same information in fewer tokens.

### Dynamic Assembly

Rather than static templates, build context **on-the-fly** based on the current query:

1. Parse the user's intent
2. Determine which context components are relevant
3. Retrieve only what's needed (semantic search, graph traversal, API calls)
4. Assemble the payload with appropriate token budgets
5. Send to the model

This is the approach taken by agentic systems -- each turn dynamically determines which tools to call, which documents to retrieve, and what metadata to include.

---

## 1.4 Retrieval-Augmented Generation (RAG)

RAG is the single most common context engineering pattern. It bridges the gap between a model's training data and the user's specific domain knowledge.

### The Core Loop

```
User Query
    │
    ▼
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│  Embed   │───▶│   Retrieve   │───▶│   Augment    │───▶│ Generate │
│  Query   │    │  (top-K)     │    │  (build      │    │ (LLM     │
│          │    │              │    │   prompt)     │    │  call)   │
└──────────┘    └──────────────┘    └──────────────┘    └──────────┘
```

1. **Embed**: Convert the user's query into a dense vector using an embedding model (e.g., OpenAI `text-embedding-3-small`, Cohere `embed-v3`)
2. **Retrieve**: Find the top-K most similar documents in the vector store using approximate nearest-neighbor search
3. **Augment**: Inject the retrieved documents into the prompt alongside the user's query
4. **Generate**: The LLM produces an answer grounded in the retrieved context

### Embedding Models

Embedding models convert text into dense vectors (arrays of floats, typically 768-3072 dimensions) that capture semantic meaning. Similar texts produce similar vectors.

**Key properties:**
- **Dimensionality**: Higher dimensions capture more nuance but cost more storage and compute. 1536 (OpenAI) is a common sweet spot.
- **Max input length**: Most models handle 512-8192 tokens. Documents longer than this must be chunked.
- **Semantic alignment**: "How do I deploy?" and "deployment instructions" should have high cosine similarity.
- **Domain adaptation**: General-purpose embeddings may underperform on specialized domains (medical, legal, code). Fine-tuning or domain-specific models help.

In cortex-ai, embedding generation is handled by `cortex/rag/embeddings.py` with Redis caching to avoid redundant API calls.

### Vector Stores

Specialized databases for storing and searching vectors at scale:

| Store | Key Strengths | Search Types |
|-------|--------------|--------------|
| **Qdrant** | Rust-based, rich filtering, multi-vector | Dense, sparse, hybrid |
| **Pinecone** | Fully managed, serverless option | Dense, sparse, hybrid |
| **Weaviate** | GraphQL API, built-in vectorizers | Dense, hybrid, BM25 |
| **pgvector** | PostgreSQL extension (no new infra) | Dense (HNSW, IVFFlat) |
| **Milvus** | GPU-accelerated, massive scale | Dense, sparse, hybrid |

cortex-ai uses Qdrant (`cortex/rag/vector_store.py`) with support for dense vectors, sparse vectors (BM25-style), and hybrid search. Collections are created with both dense and sparse vector configurations:

```python
vector_store = VectorStore(
    url="http://localhost:6333",
    collection_name="documents",
    vector_size=1536,  # text-embedding-3-small dimensions
)
await vector_store.connect()
```

### Chunking Strategies

Documents must be split into chunks before embedding. The chunking strategy has a major impact on retrieval quality.

**Fixed-size chunking**: Split every N tokens/characters with optional overlap. Simple but can split mid-sentence or mid-paragraph.

```
Document: "Context engineering is the discipline of... [500 tokens] ...knowledge graphs enable..."
Chunk 1: "Context engineering is the discipline of..." (tokens 0-256)
Chunk 2: "...discipline of...[overlap]...knowledge graphs enable..." (tokens 200-456)
```

**Semantic chunking**: Split at natural boundaries (paragraphs, sections, headings). Preserves meaning but produces variable-size chunks.

**Recursive chunking**: Try to split at the largest natural boundary first (section), then fall back to smaller boundaries (paragraph, sentence, character) if chunks are still too large.

**Parent-child (hierarchical) chunking**: Embed small chunks for precision retrieval, but return the larger parent chunk for context. This balances retrieval precision with context richness.

**The golden rule:** Each chunk should be a self-contained unit of meaning that answers a specific type of question.

### Re-Ranking

Initial retrieval returns candidates based on embedding similarity, which is fast but approximate. Re-ranking applies a more expensive but more accurate model to re-order the candidates.

**Cross-encoder re-ranking**: A cross-encoder model takes (query, document) pairs and produces a relevance score. Unlike bi-encoders (which embed query and document independently), cross-encoders attend to both simultaneously, capturing fine-grained interactions. Models: Cohere Rerank, BGE Reranker, Jina Reranker.

**Reciprocal Rank Fusion (RRF)**: When combining results from multiple retrieval sources (e.g., vector + keyword + graph), RRF merges the ranked lists:

```
RRF_score(d) = Σ  weight_i / (k + rank_i(d))
```

Where `k` is a constant (typically 60), `rank_i(d)` is the rank of document `d` in source `i`, and `weight_i` is the source weight.

cortex-ai implements RRF in `cortex/rag/retriever.py` for fusing vector and graph search results:

```python
async def graphrag_search(self, query, top_k=5, vector_weight=0.7, graph_weight=0.3):
    vector_results = await self.search(query, top_k=top_k * 2)
    graph_results = []
    for concept_name in self._extract_concepts_from_query(query):
        concept_results = await self.graph_search(concept_name, max_hops=2)
        graph_results.extend(concept_results)
    return self._reciprocal_rank_fusion(vector_results, graph_results, vector_weight, graph_weight)
```

### Hybrid Search

Combining keyword search (BM25) with semantic search (embedding similarity). Each approach has complementary strengths:

| Approach | Strength | Weakness |
|----------|----------|----------|
| **Keyword (BM25)** | Exact term matching, rare terms, proper nouns | Misses synonyms, paraphrases |
| **Semantic (embedding)** | Captures meaning, handles synonyms | May miss exact terms, dilutes rare words |
| **Hybrid** | Best of both worlds | More complex, requires tuning alpha |

The `alpha` parameter controls the blend: `alpha=1.0` is pure semantic, `alpha=0.0` is pure keyword. Values around `0.7` (70% semantic, 30% keyword) are a good starting point.

### RAG Evaluation

How to measure whether your RAG system is working:

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| **Context Precision** | Are the retrieved chunks relevant? | >0.8 |
| **Context Recall** | Did we retrieve all relevant information? | >0.7 |
| **Faithfulness** | Is the answer grounded in retrieved context (no hallucination)? | >0.9 |
| **Answer Relevancy** | Does the answer actually address the question? | >0.8 |

The RAGAS framework (Retrieval-Augmented Generation Assessment) provides standardized implementations of these metrics. cortex-ai includes RAG-oriented metrics in `cortex-ai/evals/metrics.py`.

---

## 1.5 Agentic Context Engineering

In agentic systems, the model doesn't just receive context -- it actively participates in building it. Each tool call, retrieval, and reasoning step generates new context that feeds back into the next iteration.

### Request-Scoped Context (contextvars)

In a web server handling concurrent requests, each request needs isolated state (tenant ID, user ID, stream writer, etc.) that is accessible from any layer (route handler, tool, middleware, retriever) without explicitly threading parameters through every function call.

Python's `contextvars` module provides this via task-local storage:

```python
from contextvars import ContextVar

_tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)

def get_tenant_id() -> Optional[str]:
    return _tenant_id_var.get()
```

cortex-ai wraps this in `cortex/orchestration/context.py` with a context manager that sets all request-scoped variables on entry and clears them on exit, preventing leakage between requests.

**Why this matters for context engineering:** When a tool needs to filter retrieved documents by tenant, or a middleware needs to log the conversation ID, or a guardrail needs to check user permissions, it can access this context without every function in the call chain needing to accept and forward these parameters. This is the infrastructure that makes dynamic context assembly practical.

### Session Persistence (Checkpointing)

Multi-turn conversations need state that persists between HTTP requests. LangGraph's checkpointer pattern serializes the full agent state (messages, tool results, intermediate state) to a durable store after each turn.

cortex-ai uses PostgreSQL-backed checkpoints (`cortex/orchestration/session/checkpointer.py`):

```python
# Build a deterministic thread ID from the conversation
thread_id = build_thread_id(tenant_id, conversation_id)

# Get a checkpointer (Postgres in production, MemorySaver in development)
checkpointer = await get_checkpointer()

# The agent runs with the thread ID; LangGraph loads/saves state automatically
config = {"configurable": {"thread_id": thread_id}}
result = await agent.ainvoke(messages, config=config)
```

The `SessionOrchestrator` adds a critical optimization: if a checkpoint exists, it skips re-sending the full conversation history (which is already in the checkpoint). This avoids duplicate messages and saves tokens.

### Tool Result Management

Agentic systems often call tools that return large results:

- A database query returning hundreds of rows
- A code file with thousands of lines
- An API response with deeply nested JSON

Including these verbatim in context wastes tokens and can confuse the model. Strategies:

1. **Truncation** -- Return only the first N characters/rows with a "... truncated" marker
2. **Summarization** -- Use a fast model to summarize the tool result before injecting it
3. **Virtual filesystem eviction** -- Store the full result in a virtual filesystem (part of the LangGraph state), replace the in-context content with a reference. The model can request specific parts later if needed.

The virtual filesystem pattern (used in ml-infra's swarm architecture) is particularly elegant: large tool results are "evicted" to a key-value store within the agent state. The context contains a summary + pointer. If the model needs the full data, it can use a `read_file` tool to retrieve it from the virtual FS.

### Model Context Protocol (MCP)

MCP is an open protocol (originated at Anthropic) that standardizes how tools provide context to models. Instead of each tool having a bespoke integration, MCP defines:

- **Resources** -- Data sources that tools can expose (files, database rows, API endpoints)
- **Tools** -- Callable functions with typed inputs/outputs
- **Prompts** -- Suggested prompts that tools can provide
- **Context updates** -- Dynamic context that tools can push mid-session

The value for context engineering: MCP enables tools to **proactively update the context** without requiring the model to re-invoke them. For example, a monitoring tool could push an alert into context when a deployment fails, or a document tool could update the available context when new documents are indexed.

### Middleware Pattern

Middleware interceptors transform context at key points in the LLM call lifecycle:

```
User Message
    │
    ▼
┌─────────────────┐
│  Guardrail MW   │  ← Block harmful content before LLM
├─────────────────┤
│  Summarization  │  ← Compress history if too long
│  MW             │
├─────────────────┤
│  RAG MW         │  ← Retrieve and inject relevant docs
├─────────────────┤
│  Logging MW     │  ← Capture input for observability
└────────┬────────┘
         │
         ▼
    ┌─────────┐
    │   LLM   │
    └────┬────┘
         │
         ▼
┌─────────────────┐
│  Output Guard   │  ← Validate/filter LLM response
│  MW             │
└─────────────────┘
```

In cortex-ai, the `MessageTrimmingMiddleware` duck-types the LangChain `AgentMiddleware` protocol (`before_model` / `abefore_model`), so it integrates with `create_agent()` without requiring the optional LangChain middleware import. This is a clean example of middleware as a context management tool.

---

# Part 2: Knowledge Graphs

## 2.1 Foundations

### What Is a Knowledge Graph

A knowledge graph is a structured representation of real-world entities and the relationships between them, stored as a graph of **nodes** (entities) and **edges** (relationships), each annotated with **properties**.

At its simplest, a knowledge graph is a collection of **triples**:

```
(Subject) ──[Predicate]──▶ (Object)

Examples:
  (Einstein)    ──[born_in]──▶        (Ulm)
  (GraphRAG)    ──[uses]──▶           (Neo4j)
  (Python)      ──[is_a]──▶           (Programming Language)
  (LangGraph)   ──[depends_on]──▶     (LangChain)
  (Qdrant)      ──[stores]──▶         (Vectors)
```

### Why Graphs

**Natural modeling of relationships.** The real world is a graph -- people know people, documents reference documents, services call services, code depends on code. Relational databases can model this with JOIN tables, but the queries become unwieldy as relationships deepen. Graph databases make relationships first-class citizens.

**Multi-hop reasoning.** "Which services are affected if Redis goes down?" requires traversing dependency chains. In SQL, this is a recursive CTE nightmare. In a graph, it's a simple variable-length path query:

```cypher
MATCH (redis:Service {name: "Redis"})<-[:DEPENDS_ON*1..5]-(affected)
RETURN affected.name
```

**Heterogeneous data.** A knowledge graph can unify different types of entities (people, documents, concepts, services, deployments) and different types of relationships (authored, mentions, depends_on, deployed_to) in a single model. No schema migration needed -- just add new node and relationship types.

**Semantic richness.** Flat text stores the statement "GraphRAG uses Neo4j for knowledge graphs." A knowledge graph captures the *structured meaning*:

```
(GraphRAG) ──[USES {purpose: "knowledge graphs"}]──▶ (Neo4j)
(GraphRAG) ──[IS_A]──▶ (Methodology)
(Neo4j) ──[IS_A]──▶ (Graph Database)
```

This structure enables reasoning that text search alone cannot: "What methodologies use graph databases?" becomes a simple query.

### Graph Terminology

| Term | Meaning | Example |
|------|---------|---------|
| **Node (Vertex)** | An entity | `(:Person {name: "Einstein"})` |
| **Edge (Relationship)** | A connection between nodes | `-[:BORN_IN]->` |
| **Label** | A type tag on a node | `:Person`, `:Document`, `:Concept` |
| **Property** | A key-value attribute | `{name: "Einstein", born: 1879}` |
| **Path** | A sequence of nodes and edges | `(a)-[:KNOWS]->(b)-[:WORKS_AT]->(c)` |
| **Degree** | Number of edges on a node | A node with 10 relationships has degree 10 |
| **Subgraph** | A portion of the graph | All nodes within 2 hops of Einstein |

---

## 2.2 Graph Databases

### Property Graph Model

The dominant model for application-oriented knowledge graphs. Nodes and edges both have:
- **Labels** (types): `:Person`, `:Document`, `:KNOWS`, `:MENTIONS`
- **Properties** (attributes): `{name: "...", created_at: datetime, confidence: 0.95}`

**Neo4j** is the most widely used property graph database. Key features:

| Feature | Description |
|---------|-------------|
| **Cypher** | Declarative query language (SQL-like for graphs) |
| **ACID transactions** | Full transactional support |
| **APOC** | Library of 450+ procedures (import, export, graph algorithms, text processing) |
| **GDS** | Graph Data Science library (PageRank, community detection, embeddings, ML) |
| **Full-text search** | Lucene-based full-text indexes on node properties |
| **Multi-database** | Separate databases per tenant or use-case |

In cortex-ai, Neo4j is used as the graph store for GraphRAG (`cortex/rag/graph/graph_store.py`). The `GraphStore` class provides async CRUD operations via the official `neo4j` Python driver:

```python
graph = GraphStore(url="bolt://localhost:7687", user="neo4j", password="...")
await graph.connect()
await graph.create_constraints()  # Unique constraints + performance indexes

# Add entities
doc_id = await graph.add_document("doc-123", "GraphRAG uses Neo4j", "tenant-1")
concept_id = await graph.add_concept("GraphRAG", "methodology", "tenant-1")
await graph.add_relationship(doc_id, concept_id, "MENTIONS", {"confidence": 0.95})
```

**Amazon Neptune** -- AWS managed graph database supporting both property graph (openCypher/Gremlin) and RDF (SPARQL). Good for AWS-native architectures but less feature-rich than Neo4j for analytics.

### RDF / Triple Stores

The W3C standard for knowledge representation. Data is stored as subject-predicate-object triples:

```turtle
<http://example.org/Einstein> <http://schema.org/birthPlace> <http://example.org/Ulm> .
<http://example.org/Einstein> <rdf:type> <http://schema.org/Person> .
```

**Key differences from property graphs:**

| Aspect | Property Graph | RDF |
|--------|---------------|-----|
| Schema | Flexible, optional | Ontology-driven (OWL, RDFS) |
| Query language | Cypher, Gremlin | SPARQL |
| Identity | Internal IDs | Global URIs (every entity has a URL) |
| Reasoning | Application-level | Built-in inference (OWL reasoning) |
| Best for | Application data, analytics | Linked data, ontologies, interoperability |

**When to use RDF:** When you need to link data across organizations (Linked Open Data), when you have formal ontologies, or when you need built-in logical reasoning. **When to use property graphs:** For application data, analytics, recommendation engines, and most AI/ML use cases including GraphRAG.

### Neo4j Deep-Dive: Cypher

Cypher is a pattern-matching query language. You describe the shape of the graph you're looking for:

**Create nodes and relationships:**
```cypher
CREATE (graphrag:Concept {name: "GraphRAG", category: "methodology"})
CREATE (neo4j:Concept {name: "Neo4j", category: "technology"})
CREATE (graphrag)-[:USES {strength: 0.9}]->(neo4j)
```

**Find patterns:**
```cypher
-- Find all technologies used by a methodology
MATCH (m:Concept {category: "methodology"})-[:USES]->(t:Concept {category: "technology"})
RETURN m.name AS methodology, t.name AS technology

-- Multi-hop: find concepts within 3 hops of GraphRAG
MATCH (start:Concept {name: "GraphRAG"})-[*1..3]-(related:Concept)
RETURN DISTINCT related.name, related.category

-- Shortest path between two concepts
MATCH path = shortestPath(
  (a:Concept {name: "Python"})-[*]-(b:Concept {name: "Neo4j"})
)
RETURN path
```

**Aggregation and ordering:**
```cypher
-- Most-connected concepts (by degree)
MATCH (c:Concept)-[r]-()
RETURN c.name, COUNT(r) AS connections
ORDER BY connections DESC
LIMIT 10
```

**Multi-tenancy with MERGE (idempotent upserts):**
```cypher
-- cortex-ai uses MERGE to avoid duplicate concepts within a tenant
MERGE (c:Concept {name: $name, tenant_id: $tenant_id})
ON CREATE SET c.id = $concept_id,
              c.category = $category,
              c.created_at = datetime()
RETURN c.id
```

---

## 2.3 Building Knowledge Graphs from Unstructured Data

This is the extraction pipeline -- converting raw text into structured graph data.

### The Pipeline

```
Raw Text
    │
    ▼
┌──────────────────┐
│  Entity          │  ← NER or LLM extraction
│  Extraction      │     "GraphRAG", "Neo4j", "Python"
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Relation        │  ← Extract how entities relate
│  Extraction      │     GraphRAG --USES--> Neo4j
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Entity          │  ← Merge duplicates
│  Resolution      │     "Neo4J" = "Neo4j" = "neo4j"
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Graph           │  ← Write to Neo4j
│  Insertion       │
└──────────────────┘
```

### Named Entity Recognition (NER)

Identifying entities in text. Approaches:

1. **Rule-based**: Regex patterns, gazetteers (lists of known entities). Fast but brittle.
2. **Statistical NER**: spaCy, Hugging Face NER models. Good for standard entity types (person, org, location).
3. **LLM-based**: Use GPT-4o/Claude to extract entities with context and reasoning. Most flexible, handles domain-specific entities.

### LLM-Based Extraction

The most powerful approach for domain-specific knowledge graphs. cortex-ai implements this in `cortex/rag/graph/entity_extractor.py`:

```python
EXTRACTION_PROMPT = """You are an entity extraction specialist.
Extract the following from the given text:

1. **CONCEPTS**: Technical terms, topics, themes, technologies
   - Be specific: "GraphRAG", "Neo4j", not "system", "data"
   - Categorize each: "technology", "methodology", "language"

2. **RELATIONSHIPS**: How concepts relate
   - Use clear types: "USES", "IMPLEMENTS", "DEPENDS_ON"
   - Provide strength score (0.0 to 1.0)

Return as JSON:
{
  "concepts": [{"name": "GraphRAG", "category": "methodology"}],
  "relationships": [{"source": "GraphRAG", "target": "Neo4j", "type": "USES", "strength": 0.9}]
}"""
```

Key design decisions in this implementation:
- **Model choice**: Uses `gpt-4o-mini` for cost efficiency (extraction doesn't need the most powerful model)
- **Temperature 0.0**: Deterministic extraction (same input should produce same output)
- **Truncation**: Limits input to ~15K characters (~4K tokens) to stay within limits
- **Fallback**: `extract_with_fallback()` returns an empty result on errors rather than crashing the ingestion pipeline

### Entity Resolution / Deduplication

The same entity may appear in different forms across documents:

- "Albert Einstein", "Einstein", "A. Einstein" → single entity
- "Neo4j", "Neo4J", "neo4j graph database" → single entity
- "ML", "machine learning", "Machine Learning" → single entity

Approaches:
1. **Exact + normalized matching**: Lowercase, strip whitespace, remove punctuation
2. **Fuzzy matching**: Edit distance, Jaccard similarity on character n-grams
3. **Embedding similarity**: Embed entity names and cluster by cosine similarity
4. **LLM-based resolution**: Ask a model "Are these the same entity?"

cortex-ai handles this at the graph level with `MERGE` queries that match on `(name, tenant_id)`, so adding "Neo4j" twice returns the existing concept rather than creating a duplicate.

### Schema Design

Defining what types of nodes and relationships your graph supports:

**Strict schema** (define upfront):
```
Node Labels: Document, Concept, Person, Service
Relationship Types: MENTIONS, RELATES_TO, AUTHORED_BY, DEPENDS_ON
Required Properties: id, name, tenant_id, created_at
```

**Flexible schema** (discover as you go):
```
Any node label, any relationship type, any properties.
The LLM decides what to extract.
```

**Best practice:** Start with a core schema (the cortex-ai approach: `Document`, `Concept`, `MENTIONS`, `RELATES_TO`) and extend as needed. Enforce uniqueness constraints and required properties at the database level.

cortex-ai defines the schema in `cortex/rag/graph/schema.py` as Pydantic models:

```python
class Document(BaseModel):
    id: str
    content: str
    tenant_id: str
    created_at: datetime

class Concept(BaseModel):
    id: str
    name: str
    category: str    # "technology", "methodology", "language", etc.
    tenant_id: str
    created_at: datetime

class Relationship(BaseModel):
    source_id: str
    target_id: str
    type: str        # "MENTIONS", "RELATES_TO", "USES", etc.
    properties: dict  # {confidence: 0.95, strength: 0.9, ...}
```

### Incremental Updates

Knowledge graphs must evolve as new documents are ingested:

1. **Add-only**: New documents add new nodes and edges. Existing nodes gain new relationships. Simple and safe.
2. **Upsert**: MERGE semantics -- create if new, update if exists. cortex-ai uses this pattern.
3. **Versioning**: Track when facts were added and whether they've been superseded. Enables temporal queries ("What did we know as of last month?").
4. **Pruning**: Remove low-confidence edges, orphaned nodes, or stale relationships periodically.

---

## 2.4 Querying and Reasoning

### Pattern Matching with Cypher

Cypher's power lies in describing graph patterns visually:

```cypher
-- Direct relationships
MATCH (a:Concept)-[:USES]->(b:Concept)
WHERE a.name = "GraphRAG"
RETURN b.name

-- Variable-length paths (multi-hop)
MATCH (a:Concept {name: "GraphRAG"})-[:RELATES_TO*1..3]-(b:Concept)
RETURN DISTINCT b.name, b.category

-- Conditional traversal
MATCH (d:Document)-[m:MENTIONS]->(c:Concept)
WHERE m.confidence > 0.8
  AND c.category = "technology"
RETURN d.id, collect(c.name) AS technologies
```

### Multi-Hop Queries

The defining advantage of graph databases. Questions that require following chains of relationships:

**"Find all documents that discuss technologies related to GraphRAG"**
```cypher
MATCH (graphrag:Concept {name: "GraphRAG"})-[:RELATES_TO*1..2]-(related:Concept)
WITH DISTINCT related
MATCH (doc:Document)-[:MENTIONS]->(related)
RETURN DISTINCT doc.id, doc.content, collect(related.name) AS concepts
```

This traverses from GraphRAG to related concepts (up to 2 hops), then finds documents mentioning any of those concepts. In SQL, this would require multiple self-joins on a junction table -- possible but painful and slow.

### Graph Algorithms

For analytical queries, Neo4j's Graph Data Science (GDS) library provides:

| Algorithm | Use Case | Description |
|-----------|----------|-------------|
| **PageRank** | Importance | Which concepts are most influential? (Most referenced by other important concepts) |
| **Community Detection (Louvain)** | Clustering | Automatic grouping of related concepts into communities |
| **Betweenness Centrality** | Bridge nodes | Which concepts connect otherwise-separate clusters? |
| **Shortest Path** | Connection finding | How are two concepts related? |
| **Node Similarity** | Recommendations | Which concepts appear in similar contexts? |

**Community detection** is particularly important for GraphRAG (more on this in Part 3). It partitions the graph into clusters of densely-connected nodes, which can then be summarized for answering global questions.

### Inference and Reasoning

Deriving new facts from existing relationships:

**Transitive closure:** If A depends on B and B depends on C, then A transitively depends on C.

```cypher
-- Find all transitive dependencies
MATCH (a:Service {name: "my-app"})-[:DEPENDS_ON*]->(dep:Service)
RETURN dep.name AS transitive_dependency
```

**Rule-based reasoning:** "If two concepts are both mentioned in the same document with high confidence, they are related."

```cypher
MATCH (c1:Concept)<-[m1:MENTIONS]-(d:Document)-[m2:MENTIONS]->(c2:Concept)
WHERE c1 <> c2
  AND m1.confidence > 0.8
  AND m2.confidence > 0.8
  AND NOT (c1)-[:RELATES_TO]-(c2)
MERGE (c1)-[:RELATES_TO {inferred: true, source: "co-occurrence"}]->(c2)
```

### Text-to-Cypher

Using LLMs to generate Cypher queries from natural language:

```
User: "What technologies does GraphRAG depend on?"
LLM → Cypher: MATCH (g:Concept {name: "GraphRAG"})-[:DEPENDS_ON|USES]->(t:Concept)
               RETURN t.name, t.category
```

This is powerful but challenging:
- The LLM needs the graph schema in context (node labels, relationship types, property names)
- Generated Cypher must be validated before execution (security)
- Ambiguous questions produce ambiguous queries
- Complex queries (multi-hop, aggregation) have lower accuracy

Best practice: Provide the schema + a few examples of question → Cypher mappings in the system prompt. Validate generated Cypher against the schema before execution. Use parameterized queries to prevent injection.

---

## 2.5 Knowledge Graph Embeddings

### Concept

Just as text can be embedded into dense vectors, graph structures can too. Knowledge graph embedding (KGE) models learn vector representations of nodes and edges such that the geometric relationships between vectors reflect the graph structure.

### Core Models

**TransE** -- Models relationships as translations: if `(h, r, t)` is a valid triple, then `h + r ≈ t` in the embedding space.

```
Embedding space:
  Einstein + born_in ≈ Ulm
  GraphRAG + uses ≈ Neo4j
```

Simple and effective for 1-to-1 relationships. Struggles with 1-to-many (a person born in multiple cities) and many-to-many.

**RotatE** -- Models relationships as rotations in complex space. Handles symmetry, antisymmetry, inversion, and composition patterns better than TransE.

**ComplEx** -- Uses complex-valued embeddings to handle both symmetric and antisymmetric relationships.

### Use Cases

| Use Case | Description |
|----------|-------------|
| **Link prediction** | Predict missing relationships: "Is it likely that X relates to Y?" |
| **Entity classification** | Classify nodes based on their neighborhood embeddings |
| **Similarity search** | Find entities similar to a given entity via vector similarity |
| **Anomaly detection** | Triples with low plausibility scores may indicate errors |

### Relation to Vector Search

KG embeddings can be stored in the same vector databases used for document embeddings. This enables unified retrieval:

```
Query: "What is GraphRAG?"
    │
    ├── Vector search: find document chunks about GraphRAG (semantic)
    ├── KG embedding search: find entities near GraphRAG in the embedding space (structural)
    └── Graph traversal: find concepts connected to GraphRAG (explicit relationships)
```

This three-pronged approach gives you semantic similarity, structural similarity, and explicit relationships -- a comprehensive view of the knowledge landscape.

---

# Part 3: The Intersection -- GraphRAG

## 3.1 Why Plain RAG Falls Short

Standard RAG (vector search → augment prompt → generate) has fundamental limitations:

### The Needle Problem

Vector search finds chunks that are *semantically similar* to the query. But similarity is not always what you need:

- **"What technologies does GraphRAG use?"** -- The answer requires *relationship traversal*, not similarity. The chunk mentioning "GraphRAG uses Neo4j for knowledge graphs and Qdrant for vector storage" might not be the closest match to the query embedding.

### The Multi-Hop Problem

- **"Which teams maintain services that depend on Redis?"** -- This requires: (1) find services depending on Redis, (2) find which teams maintain those services. Vector search returns chunks about Redis or about teams, but not the chain.

### The Aggregation Problem

- **"What are the main themes across all our architecture documents?"** -- This requires synthesizing information across dozens of documents. Vector search returns the top-K most relevant chunks, missing the big picture.

### The Contradiction Problem

- When multiple documents contain conflicting information, vector search returns all of them without distinguishing which is authoritative. A knowledge graph can encode recency, confidence, and provenance.

---

## 3.2 GraphRAG Architecture

GraphRAG extends RAG by adding a knowledge graph as a parallel retrieval source:

```
                    ┌─────────────────────────────────────┐
                    │         Ingestion Pipeline           │
                    │                                     │
                    │  Document                           │
                    │     │                               │
                    │     ├──▶ Chunker ──▶ Embedder       │
                    │     │                  │             │
                    │     │           ┌──────▼──────┐     │
                    │     │           │ Vector Store │     │
                    │     │           │   (Qdrant)   │     │
                    │     │           └─────────────┘     │
                    │     │                               │
                    │     └──▶ Entity Extractor (LLM)     │
                    │              │                       │
                    │              ▼                       │
                    │     Entity Resolver                  │
                    │              │                       │
                    │        ┌─────▼─────┐                │
                    │        │Graph Store│                 │
                    │        │  (Neo4j)  │                 │
                    │        └──────────┘                  │
                    └─────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │         Retrieval Pipeline           │
                    │                                     │
                    │  User Query                         │
                    │     │                               │
                    │     ├──▶ Vector Search               │
                    │     │      (embed query, find        │
                    │     │       similar chunks)           │
                    │     │                               │
                    │     ├──▶ Graph Traversal             │
                    │     │      (extract concepts,        │
                    │     │       traverse neighbors)       │
                    │     │                               │
                    │     └──▶ Text-to-Cypher (optional)   │
                    │            (generate + execute        │
                    │             structured query)         │
                    │                                     │
                    │     All results                      │
                    │         │                            │
                    │         ▼                            │
                    │     RRF Fusion                       │
                    │         │                            │
                    │         ▼                            │
                    │     Context Builder                  │
                    │         │                            │
                    │         ▼                            │
                    │       LLM ──▶ Response               │
                    └─────────────────────────────────────┘
```

### The Ingestion Pipeline (Dual-Write)

When a document is uploaded, two things happen in parallel:

1. **Vector path**: Document → chunk → embed → store in Qdrant
2. **Graph path**: Document → entity extraction (LLM) → entity resolution → store in Neo4j

cortex-ai's document upload route (`cortex/api/routes/documents.py`) orchestrates this dual-write when `CORTEX_GRAPHRAG_ENABLED` is set. The graph path runs the `EntityExtractor` to identify concepts, then stores `Document` and `Concept` nodes with `MENTIONS` relationships.

### The Retrieval Pipeline (Hybrid Search)

On query, three retrieval strategies run (potentially in parallel):

1. **Vector search**: Embed the query, find top-K similar chunks in Qdrant
2. **Graph traversal**: Extract concept names from the query, traverse their neighborhoods in Neo4j to find related documents
3. **Text-to-Cypher** (optional): Generate a structured query from the natural language question

Results from all sources are combined using Reciprocal Rank Fusion (RRF):

```python
# From cortex/rag/retriever.py
def _reciprocal_rank_fusion(self, vector_results, graph_results, vector_weight, graph_weight, k=60):
    # RRF Score: score(d) = Σ w_i / (k + rank_i(d))
    for doc_id in all_doc_ids:
        rrf_score = 0.0
        if doc_id in vector_ranks:
            rrf_score += vector_weight / (k + vector_ranks[doc_id])
        if doc_id in graph_ranks:
            rrf_score += graph_weight / (k + graph_ranks[doc_id])
        doc_scores[doc_id] = rrf_score
```

The default weights (70% vector, 30% graph) can be tuned based on your query patterns. Entity-heavy queries benefit from higher graph weight; semantic similarity queries benefit from higher vector weight.

### Microsoft's GraphRAG Approach

Microsoft Research proposed a specific GraphRAG architecture focused on **global questions** (questions about the dataset as a whole, not specific entities):

1. **Build**: Extract entities and relationships from all documents into a knowledge graph
2. **Community detection**: Run Leiden/Louvain algorithm to partition the graph into communities of densely-connected entities
3. **Summarize**: Generate a natural-language summary for each community using an LLM
4. **Query (local)**: For entity-specific questions, traverse the entity's neighborhood
5. **Query (global)**: For thematic questions, map-reduce over community summaries

The community summaries are the key innovation: they provide pre-computed, high-level views of the knowledge that answer "what are the main themes?" questions without scanning every document.

### Local vs. Global Queries

| Query Type | Example | Retrieval Strategy |
|-----------|---------|-------------------|
| **Local** | "What is Neo4j?" | Graph neighborhood traversal + vector search |
| **Local+** | "What technologies does GraphRAG use?" | Multi-hop graph traversal (concept → neighbors → documents) |
| **Global** | "What are the main themes in our docs?" | Community summaries + map-reduce |
| **Hybrid** | "How does GraphRAG compare to standard RAG?" | Vector (semantic similarity) + graph (relationship-aware) + RRF fusion |

---

## 3.3 Structured Memory via Knowledge Graphs

Beyond retrieval, knowledge graphs serve as a **structured memory layer** for AI agents.

### Entity Memory

Instead of storing raw conversation history (which grows linearly and eventually overflows), extract key entities and facts into a knowledge graph:

```
Conversation turn 1: "I'm working on the auth service, it uses JWT tokens"
  → Extract: (auth_service)-[:USES]->(JWT)

Conversation turn 5: "We're migrating auth to OAuth2"
  → Extract: (auth_service)-[:MIGRATING_TO]->(OAuth2)
  → Update: (auth_service)-[:USES {status: "deprecated"}]->(JWT)

Conversation turn 20: "What's the status of auth?"
  → Retrieve: auth_service neighborhood from graph
  → Context: "auth_service uses JWT (deprecated), migrating to OAuth2"
```

The graph provides a compressed, structured summary of everything the agent has learned about each entity. This scales to thousands of conversations without growing the context window.

### Temporal Knowledge

Track *when* facts were learned and whether they've been superseded:

```cypher
CREATE (fact:Fact {
    subject: "auth_service",
    predicate: "uses",
    object: "JWT",
    learned_at: datetime("2026-01-15"),
    superseded_at: datetime("2026-03-10"),
    superseded_by: "OAuth2 migration"
})
```

This enables time-aware queries: "What did we know about auth as of January?" vs. "What is the current state of auth?"

### User Modeling

Build a per-user knowledge graph that captures:

- **Expertise areas**: What topics the user knows well (fewer explanations needed)
- **Preferences**: Verbose vs. concise, code examples vs. prose
- **Past interactions**: What projects they've worked on, what tools they use
- **Organizational context**: Their team, their role, their access permissions

This enables personalized context assembly: a senior engineer gets concise technical answers; a product manager gets higher-level explanations with business context.

### Evolving Context

As the agent interacts with users, the knowledge graph grows organically:

1. **Turn 1**: User asks about deploying to Kubernetes. Graph is empty for this user.
2. **Turn 5**: Graph now contains: user → uses → Kubernetes, app → deploys_to → GKE, app → uses → Helm
3. **Turn 20**: Graph has a rich model of the user's infrastructure. Context assembly can now include relevant background without the user re-explaining.

The graph becomes a **compressed, queryable summary** of all prior interactions -- far more efficient than storing and re-processing raw conversation logs.

---

## 3.4 Key Design Decisions

### Schema Flexibility vs. Strictness

| Approach | Pros | Cons |
|----------|------|------|
| **Strict** (predefined labels/types) | Consistent data, easier querying, schema validation | Limits discovery, requires upfront design |
| **Flexible** (LLM decides) | Adapts to any domain, discovers unexpected relationships | Noisy, inconsistent naming, harder to query |
| **Hybrid** (core strict + extension flexible) | Best of both: stable core + discovery | More complex to manage |

cortex-ai uses the hybrid approach: core schema (`Document`, `Concept`, `MENTIONS`, `RELATES_TO`) with LLM-extracted categories and relationship types that can vary.

### Extraction Quality vs. Cost

| Method | Quality | Cost per Document | Latency |
|--------|---------|-------------------|---------|
| Rule-based NER | Low-Medium | ~$0 | <100ms |
| spaCy/HF NER | Medium | ~$0 | <500ms |
| GPT-4o-mini extraction | Medium-High | ~$0.01 | 1-3s |
| GPT-4o extraction | High | ~$0.10 | 3-10s |
| Human annotation | Highest | $1-10+ | Minutes-Hours |

cortex-ai defaults to `gpt-4o-mini` at temperature 0.0 -- a pragmatic balance of quality, cost, and speed.

### Graph Size Management

As the knowledge graph grows, it needs maintenance:

- **Prune low-confidence edges**: Relationships below a confidence threshold (e.g., 0.3) add noise. Remove them periodically.
- **Merge near-duplicate entities**: Run entity resolution periodically to consolidate "Neo4J", "Neo4j", "neo4j" into one node.
- **Archive stale knowledge**: Move facts older than N days to an archive graph. Keep the active graph focused on current knowledge.
- **Degree limits**: Nodes with extremely high degree (connected to everything) are often generic concepts ("system", "data") that add little value. Consider removing or ignoring them in traversal.

### When NOT to Use a Knowledge Graph

Knowledge graphs add complexity. Skip them when:

- **Simple Q&A over homogeneous documents**: If your documents are all the same type and queries are straightforward, vector search alone is sufficient.
- **Low entity density**: If documents don't contain many named entities or explicit relationships, the extraction step produces thin graphs with little value.
- **No multi-hop queries needed**: If users only ask "find documents about X" (single-hop), the graph traversal doesn't add much over vector search.
- **Latency-critical paths**: Graph queries add 50-200ms. If your SLA is <100ms for retrieval, the overhead may be unacceptable (though caching can help).

### Latency Considerations

| Operation | Typical Latency | Optimization |
|-----------|----------------|-------------|
| Vector search (Qdrant) | 5-50ms | HNSW indexes, quantization |
| Graph traversal (Neo4j) | 20-200ms | Indexes, depth limits, caching |
| Entity extraction (LLM) | 1-5s | Async, batch processing, smaller models |
| RRF fusion | <1ms | In-memory computation |

For real-time queries, pre-compute common traversals and cache hot subgraphs. Run entity extraction asynchronously during document ingestion, not at query time.

---

## 3.5 Evaluation

### RAG Metrics (RAGAS)

| Metric | Formula (simplified) | Interpretation |
|--------|---------------------|----------------|
| **Context Precision** | Relevant chunks / Total chunks retrieved | Are we retrieving signal, not noise? |
| **Context Recall** | Retrieved relevant info / Total relevant info that exists | Are we finding everything we should? |
| **Faithfulness** | Answered claims supported by context / Total claims | Is the answer grounded (no hallucination)? |
| **Answer Relevancy** | Semantic similarity between answer and question | Does the answer address what was asked? |

### Graph-Specific Metrics

| Metric | What It Measures | How to Compute |
|--------|-----------------|----------------|
| **Entity Extraction F1** | Accuracy of NER | Compare extracted entities against human-labeled ground truth |
| **Relationship Accuracy** | Are extracted relationships correct? | Sample relationships, have humans verify |
| **Graph Coverage** | Does the graph represent the knowledge in the documents? | For a set of known facts, check if the graph contains them |
| **Entity Resolution Accuracy** | Are the right entities merged? | Check for false merges (different entities merged) and false splits (same entity not merged) |

### End-to-End Evaluation

The ultimate question: **Does KG-augmented retrieval produce better answers than vanilla RAG?**

Design an evaluation set:
1. **Local questions** (entity-specific): "What does X do?" → Both RAG and GraphRAG should answer well
2. **Multi-hop questions**: "What technologies are used by projects that depend on Redis?" → GraphRAG should outperform
3. **Global questions**: "What are the main architectural patterns in our codebase?" → GraphRAG (community summaries) should outperform
4. **Contradicting sources**: "What version of Python do we use?" (when different docs say different things) → GraphRAG can use recency/confidence to pick the right answer

Measure each category separately to understand where GraphRAG adds value vs. where vanilla RAG is sufficient.

---

## Further Reading

### Papers

- **"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"** (Lewis et al., 2020) -- The original RAG paper
- **"From Local to Global: A Graph RAG Approach to Query-Focused Summarization"** (Microsoft Research, 2024) -- The Microsoft GraphRAG paper
- **"Translating Embeddings for Modeling Multi-relational Data"** (Bordes et al., 2013) -- TransE, the foundational KG embedding model
- **"Lost in the Middle: How Language Models Use Long Contexts"** (Liu et al., 2023) -- Evidence for positional bias in context attention
- **"LLMLingua: Compressing Prompts for Accelerated Inference"** (Jiang et al., 2023) -- Prompt compression techniques

### Tools and Frameworks

| Tool | Purpose |
|------|---------|
| **LangChain / LangGraph** | Agent orchestration, tool calling, checkpointing |
| **Neo4j** | Property graph database |
| **Qdrant** | Vector database with hybrid search |
| **RAGAS** | RAG evaluation framework |
| **spaCy** | NLP pipeline (NER, tokenization, dependency parsing) |
| **LlamaIndex** | Data framework for LLM applications (includes KG support) |
| **Microsoft GraphRAG** | Open-source GraphRAG implementation |
| **Langfuse** | LLM observability and evaluation |

### Codebase References (cortex-ai)

| Component | Path | Relevance |
|-----------|------|-----------|
| Request-scoped context | `cortex/orchestration/context.py` | contextvars pattern for context engineering |
| Session orchestrator | `cortex/orchestration/session/orchestrator.py` | Full session lifecycle with context management |
| Checkpointer | `cortex/orchestration/session/checkpointer.py` | PostgreSQL-backed session persistence |
| Summarization middleware | `cortex/orchestration/middleware/summarization.py` | Message trimming and LLM summarization |
| Embedding service | `cortex/rag/embeddings.py` | OpenAI embeddings with Redis caching |
| Vector store | `cortex/rag/vector_store.py` | Qdrant integration (dense, sparse, hybrid) |
| Retriever | `cortex/rag/retriever.py` | Semantic, hybrid, and GraphRAG search with RRF |
| Graph store | `cortex/rag/graph/graph_store.py` | Neo4j CRUD operations |
| Entity extractor | `cortex/rag/graph/entity_extractor.py` | LLM-based concept and relationship extraction |
| Graph schema | `cortex/rag/graph/schema.py` | Pydantic models for Document, Concept, Relationship |
