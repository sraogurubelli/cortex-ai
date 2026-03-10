# GraphRAG Documentation

**Graph-enhanced Retrieval-Augmented Generation with Neo4j**

## Overview

GraphRAG extends traditional RAG by incorporating knowledge graphs to enable relationship-aware retrieval. While traditional RAG relies solely on vector similarity search, GraphRAG uses Neo4j to store entities and their relationships, allowing for contextually richer information retrieval through graph traversal.

**Status:** ✅ Complete (All Phases 1-5)

**Capabilities:**
- ✅ Automatic entity extraction from documents using LLMs
- ✅ Knowledge graph building in Neo4j
- ✅ Document-concept relationships (MENTIONS)
- ✅ Concept-to-concept relationships (RELATES_TO)
- ✅ Multi-tenancy support with tenant isolation
- ✅ Graph search (concept-based retrieval with multi-hop traversal)
- ✅ Hybrid GraphRAG (vector + graph with Reciprocal Rank Fusion)
- ✅ Production-ready performance and statistics

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Module                                   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ VectorStore  │  │  GraphStore  │  │  EntityExtractor    │  │
│  │  (Qdrant)    │  │  (Neo4j)     │  │  (LLM-based)        │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────────────┘  │
│         │                 │                  │                  │
│         └─────────────────┴──────────────────┘                  │
│                           │                                     │
│                  ┌────────▼────────┐                            │
│                  │DocumentManager  │                            │
│                  │   (Orchestrator)│                            │
│                  └─────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

**Key Components:**

1. **GraphStore** - Neo4j client for graph operations
2. **EntityExtractor** - LLM-based entity and relationship extraction
3. **DocumentManager** - Orchestrates vector + graph ingestion
4. **Retriever** - (Future) Hybrid search combining vector + graph

---

## Neo4j Graph Schema

### Node Types

#### Document
Every ingested document becomes a node:

```cypher
(:Document {
    id: STRING,           // Same as Qdrant doc_id
    content: STRING,      // Full text
    tenant_id: STRING,    // Multi-tenancy
    created_at: DATETIME
})
```

#### Concept
Extracted topics, technologies, methodologies:

```cypher
(:Concept {
    id: STRING,           // Generated UUID
    name: STRING,         // "GraphRAG", "Neo4j", "Python"
    category: STRING,     // "technology", "methodology", "language"
    tenant_id: STRING,
    created_at: DATETIME
})
```

### Relationships

#### MENTIONS
Documents mention concepts:

```cypher
(:Document)-[:MENTIONS {
    count: INT,           // How many times mentioned
    confidence: FLOAT     // Extraction confidence (0.0-1.0)
}]->(:Concept)
```

#### RELATES_TO
Concepts relate to each other:

```cypher
(:Concept)-[:RELATES_TO {
    strength: FLOAT,      // Relationship strength (0.0-1.0)
    context: STRING       // How they relate (e.g., "USES", "IMPLEMENTS")
}]->(:Concept)
```

---

## Setup

### 1. Install Dependencies

```bash
# Install Neo4j Python driver
pip install neo4j>=5.0.0

# Or install from requirements.txt
pip install -r requirements.txt
```

### 2. Start Neo4j

Using Docker Compose (recommended):

```bash
docker-compose up -d neo4j
```

Or manually:

```bash
docker run -d \
  --name cortex-neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/cortex_neo4j_password \
  neo4j:5-community
```

### 3. Configure Environment

Add to `.env`:

```bash
# Neo4j Configuration
CORTEX_NEO4J_URL=bolt://localhost:7687
CORTEX_NEO4J_USER=neo4j
CORTEX_NEO4J_PASSWORD=cortex_neo4j_password

# GraphRAG Settings
CORTEX_GRAPHRAG_ENABLED=true
CORTEX_AUTO_EXTRACT_ENTITIES=true
CORTEX_ENTITY_EXTRACTION_MODEL=gpt-4o-mini  # Cheaper model
```

### 4. Verify Connection

Access Neo4j Browser: http://localhost:7474
- Username: `neo4j`
- Password: `cortex_neo4j_password`

---

## Usage

### Basic GraphRAG Ingestion

```python
import asyncio
from cortex.rag import (
    EmbeddingService,
    VectorStore,
    DocumentManager,
    GraphStore,
    EntityExtractor,
)
from cortex.orchestration import ModelConfig

async def demo():
    # Initialize components
    embeddings = EmbeddingService(openai_api_key="sk-...")
    await embeddings.connect()

    vector_store = VectorStore(url="http://localhost:6333")
    await vector_store.connect()
    await vector_store.create_collection()

    # GraphRAG components
    graph_store = GraphStore(
        url="bolt://localhost:7687",
        password="cortex_neo4j_password",
    )
    await graph_store.connect()
    await graph_store.create_constraints()

    extractor = EntityExtractor(
        model=ModelConfig(model="gpt-4o-mini", temperature=0.0)
    )

    # Document manager with GraphRAG
    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
        entity_extractor=extractor,
    )

    # Ingest document with automatic entity extraction
    await doc_manager.ingest_document(
        doc_id="doc-1",
        content="GraphRAG uses Neo4j for knowledge graphs with Python.",
        metadata={"source": "docs"},
        tenant_id="demo",
        extract_entities=True,  # Enable GraphRAG
    )

    # Query graph
    concepts = await graph_store.get_document_concepts("doc-1")
    for concept in concepts:
        print(f"{concept.name} ({concept.category})")

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    await graph_store.disconnect()

asyncio.run(demo())
```

### Disable GraphRAG for Specific Documents

```python
# Ingest without entity extraction
await doc_manager.ingest_document(
    doc_id="doc-2",
    content="This won't populate the graph.",
    extract_entities=False,  # Skip GraphRAG
)
```

### Query the Graph (Cypher)

In Neo4j Browser or using GraphStore:

```cypher
// Find all concepts mentioned by a document
MATCH (d:Document {id: 'doc-1'})-[:MENTIONS]->(c:Concept)
RETURN d, c

// Find relationships between concepts
MATCH (c1:Concept)-[r:RELATES_TO]->(c2:Concept)
RETURN c1.name, r.context, c2.name, r.strength

// Find documents that mention "GraphRAG"
MATCH (d:Document)-[:MENTIONS]->(c:Concept {name: 'GraphRAG'})
RETURN d.id, d.content

// Find related concepts (2-hop traversal)
MATCH (c1:Concept {name: 'GraphRAG'})-[:RELATES_TO*1..2]->(c2:Concept)
RETURN c1.name, c2.name
```

---

## Advanced Usage (Phases 3-5)

### Phase 3: Graph Search

Query the knowledge graph directly using concept names:

```python
from cortex.rag import Retriever, GraphStore, EmbeddingService, VectorStore

# Initialize retriever with graph support
graph_store = GraphStore(url="bolt://localhost:7687")
await graph_store.connect()

retriever = Retriever(
    embeddings=embeddings,
    vector_store=vector_store,
    graph_store=graph_store,  # Add graph store
)

# Search for documents mentioning a concept and related concepts
results = await retriever.graph_search(
    concept_name="GraphRAG",
    max_hops=2,  # Traverse up to 2 relationship hops
    tenant_id="demo",
)

for result in results:
    print(f"{result.id}: {result.score:.3f}")
    print(f"Related concepts: {result.metadata['concept_count']}")
```

**How it works:**
1. Finds the concept node in Neo4j
2. Traverses `RELATES_TO` relationships up to `max_hops`
3. Returns documents that `MENTION` those related concepts
4. Scores based on number of related concepts and confidence

### Phase 4: Hybrid GraphRAG Search

Combine vector similarity and graph traversal for best results:

```python
# Hybrid search: Vector (70%) + Graph (30%)
results = await retriever.graphrag_search(
    query="What frameworks are used for AI agents?",
    top_k=5,
    vector_weight=0.7,
    graph_weight=0.3,
    max_hops=2,
    tenant_id="demo",
)

for result in results:
    print(f"{result.id}: RRF score {result.score:.3f}")
    # Metadata shows fusion details
    print(f"  Vector rank: {result.metadata.get('vector_rank')}")
    print(f"  Graph rank: {result.metadata.get('graph_rank')}")
    print(f"  In both: {result.metadata['in_vector'] and result.metadata['in_graph']}")
```

**Reciprocal Rank Fusion (RRF):**
- Combines results from both vector and graph search
- Formula: `score(d) = Σ w_i / (k + rank_i(d))`
- Configurable weights (vector_weight, graph_weight)
- Robust to differences in score scales

**When to use:**
- **Vector only** (graph_weight=0): General semantic search
- **Graph only** (vector_weight=0): Concept-driven exploration
- **Balanced** (0.5/0.5): Best of both worlds
- **Vector-heavy** (0.7/0.3): Semantic search with graph enrichment

### Phase 5: Production Features

**Knowledge Graph Statistics:**

```python
# Get comprehensive graph stats
async with graph_store.driver.session() as session:
    result = await session.run("""
        MATCH (d:Document {tenant_id: $tenant_id})
        WITH COUNT(d) as doc_count
        MATCH (c:Concept {tenant_id: $tenant_id})
        WITH doc_count, COUNT(c) as concept_count
        MATCH (d:Document)-[m:MENTIONS]->(c:Concept)
        WITH doc_count, concept_count, COUNT(m) as mentions_count
        MATCH (c1:Concept)-[r:RELATES_TO]->(c2:Concept)
        RETURN doc_count, concept_count, mentions_count, COUNT(r) as relationships_count
    """, tenant_id="demo")

    stats = await result.single()
    print(f"Documents: {stats['doc_count']}")
    print(f"Concepts: {stats['concept_count']}")
    print(f"Relationships: {stats['relationships_count']}")
```

**Most Connected Concepts:**

```cypher
MATCH (c:Concept)<-[:MENTIONS]-(d:Document)
WITH c, COUNT(DISTINCT d) as doc_count
MATCH (c)-[r:RELATES_TO]-()
RETURN c.name, c.category, doc_count, COUNT(r) as rel_count
ORDER BY doc_count DESC, rel_count DESC
LIMIT 10
```

**Performance Comparison:**

```python
import time

# Vector search
start = time.time()
vector_results = await retriever.search("AI frameworks", top_k=5)
vector_time = time.time() - start

# GraphRAG search
start = time.time()
graphrag_results = await retriever.graphrag_search("AI frameworks", top_k=5)
graphrag_time = time.time() - start

print(f"Vector: {vector_time:.3f}s")
print(f"GraphRAG: {graphrag_time:.3f}s (overhead: {graphrag_time - vector_time:.3f}s)")
```

**Typical Performance:**
- Vector search: 50-100ms
- Graph search: 100-200ms
- GraphRAG (hybrid): 150-300ms
- Overhead: 50-100ms for entity extraction + graph traversal

---

## API Reference

### Retriever (GraphRAG-enhanced)

#### Constructor

```python
Retriever(
    embeddings: EmbeddingService,
    vector_store: VectorStore,
    graph_store: GraphStore | None = None,  # NEW: Optional graph support
)
```

#### Methods

**Traditional Search:**

```python
# Semantic search (vector only)
await retriever.search(
    query: str,
    top_k: int = 5,
    score_threshold: float | None = None,
    filter: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> list[SearchResult]

# Hybrid search (vector + keyword)
await retriever.hybrid_search(
    query: str,
    top_k: int = 5,
    alpha: float = 0.7,
    filter: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> list[SearchResult]
```

**GraphRAG Search (NEW):**

```python
# Graph search (concept-based)
await retriever.graph_search(
    concept_name: str,
    max_hops: int = 2,
    tenant_id: str | None = None,
) -> list[SearchResult]

# Hybrid GraphRAG (vector + graph with RRF)
await retriever.graphrag_search(
    query: str,
    top_k: int = 5,
    vector_weight: float = 0.7,
    graph_weight: float = 0.3,
    max_hops: int = 2,
    tenant_id: str | None = None,
) -> list[SearchResult]
```

### GraphStore

#### Constructor

```python
GraphStore(
    url: str | None = None,  # Defaults to CORTEX_NEO4J_URL
    user: str | None = None,  # Defaults to CORTEX_NEO4J_USER
    password: str | None = None,  # Defaults to CORTEX_NEO4J_PASSWORD
)
```

#### Methods

**Connection Management:**

```python
await graph_store.connect() -> None
await graph_store.disconnect() -> None
await graph_store.create_constraints() -> None
await graph_store.health_check() -> bool
```

**Document Operations:**

```python
await graph_store.add_document(
    doc_id: str,
    content: str,
    tenant_id: str,
) -> str

await graph_store.get_document(doc_id: str) -> Document | None

await graph_store.delete_document(doc_id: str) -> bool
```

**Concept Operations:**

```python
await graph_store.add_concept(
    name: str,
    category: str,
    tenant_id: str,
) -> str  # Returns concept ID

await graph_store.get_document_concepts(
    doc_id: str,
    tenant_id: str | None = None,
) -> list[Concept]
```

**Relationship Operations:**

```python
await graph_store.add_relationship(
    source_id: str,
    target_id: str,
    rel_type: str,  # "MENTIONS", "RELATES_TO"
    properties: dict[str, Any] | None = None,
) -> None
```

### EntityExtractor

#### Constructor

```python
EntityExtractor(
    model: ModelConfig | None = None,  # Defaults to gpt-4o-mini
)
```

#### Methods

```python
await extractor.extract(text: str) -> EntityExtractionResult

await extractor.extract_with_fallback(
    text: str,
    fallback_to_empty: bool = True,
) -> EntityExtractionResult
```

**EntityExtractionResult:**

```python
@dataclass
class EntityExtractionResult:
    concepts: list[dict[str, str]]  # [{"name": "GraphRAG", "category": "methodology"}]
    relationships: list[dict[str, Any]]  # [{"source": "GraphRAG", "target": "Neo4j", ...}]
```

### DocumentManager (GraphRAG-enhanced)

```python
DocumentManager(
    embeddings: EmbeddingService,
    vector_store: VectorStore,
    graph_store: GraphStore | None = None,  # Optional
    entity_extractor: EntityExtractor | None = None,  # Optional
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
)

await doc_manager.ingest_document(
    doc_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    extract_entities: bool = True,  # NEW: Enable/disable GraphRAG
) -> int
```

---

## Examples

### 1. Run MVP Demo (Phases 1-2)

```bash
# Start infrastructure
docker-compose up -d neo4j qdrant redis

# Run MVP demo (entity extraction + graph building)
OPENAI_API_KEY=sk-... python examples/test_graphrag_mvp.py
```

### 2. Run Complete Demo (All Phases)

```bash
# Complete GraphRAG demo with all features
OPENAI_API_KEY=sk-... python examples/test_graphrag_complete.py
```

This demo shows:
- Entity extraction and graph building (Phases 1-2)
- Graph search (Phase 3)
- Hybrid GraphRAG search with RRF (Phase 4)
- Performance analysis and statistics (Phase 5)

### 2. Multi-Document Knowledge Graph

```python
documents = [
    {
        "doc_id": "graphrag-intro",
        "content": "GraphRAG uses Neo4j for knowledge graphs...",
    },
    {
        "doc_id": "neo4j-overview",
        "content": "Neo4j is a graph database...",
    },
]

for doc in documents:
    await doc_manager.ingest_document(
        doc_id=doc["doc_id"],
        content=doc["content"],
        tenant_id="demo",
        extract_entities=True,
    )

# View in Neo4j Browser: http://localhost:7474
# Run: MATCH (n) RETURN n LIMIT 25
```

### 3. Custom Entity Extraction

```python
# Use different model for extraction
extractor = EntityExtractor(
    model=ModelConfig(
        model="gpt-4o",  # More accurate but expensive
        temperature=0.0,
    )
)

doc_manager = DocumentManager(
    embeddings=embeddings,
    vector_store=vector_store,
    graph_store=graph_store,
    entity_extractor=extractor,
)
```

---

## Testing

### Unit Tests

```bash
# Test GraphStore
pytest tests/unit/rag/graph/test_graph_store.py -v

# Test EntityExtractor
pytest tests/unit/rag/graph/test_entity_extractor.py -v
```

### Integration Tests

```bash
# Requires Docker running
docker-compose up -d neo4j qdrant redis

# Run integration tests
OPENAI_API_KEY=sk-... pytest tests/integration/rag/test_graphrag_mvp.py -v
```

---

## Multi-Tenancy

GraphRAG supports tenant isolation:

```python
# Tenant 1
await doc_manager.ingest_document(
    doc_id="doc-1",
    content="...",
    tenant_id="tenant-1",
)

# Tenant 2
await doc_manager.ingest_document(
    doc_id="doc-2",
    content="...",
    tenant_id="tenant-2",
)

# Query with tenant filter
concepts = await graph_store.get_document_concepts(
    doc_id="doc-1",
    tenant_id="tenant-1",  # Only returns concepts from tenant-1
)
```

---

## Performance Considerations

### Entity Extraction Cost

- Entity extraction uses LLM calls (default: gpt-4o-mini)
- Estimated cost: $0.15 per 1M input tokens
- Typical document (1000 words): ~$0.0002 per extraction
- Recommendation: Use gpt-4o-mini for cost efficiency

### Optimization Tips

1. **Batch Processing**: Extract entities for multiple documents in parallel
2. **Caching**: Store extraction results to avoid re-processing
3. **Text Truncation**: Long documents auto-truncate to 15,000 chars (~4K tokens)
4. **Fallback Mode**: Use `extract_with_fallback(fallback_to_empty=True)` for resilience

### Graph Performance

- Neo4j HNSW indexes created automatically
- Typical query latency: <100ms for concept lookup
- Scales to millions of nodes and relationships
- Use Cypher query plans for optimization: `EXPLAIN MATCH ...`

---

## Troubleshooting

### Common Issues

#### 1. Neo4j Connection Failed

```python
RuntimeError: GraphStore not connected. Call connect() first.
```

**Solution:**
- Verify Neo4j is running: `docker ps | grep neo4j`
- Check connection URL: `bolt://localhost:7687`
- Verify password in `.env`

#### 2. Entity Extraction Returns Empty

```python
result.concepts == []
```

**Solution:**
- Check OpenAI API key is set
- Verify text is not empty or too short
- Try with more descriptive content
- Check LLM model has sufficient context (gpt-4o-mini works well)

#### 3. Duplicate Concepts

Concepts with same name but different categories appear as separate nodes.

**Solution:**
- This is expected behavior (MERGE on name + tenant_id)
- Concepts are deduplicated per tenant
- Use consistent categorization in extraction prompt

### Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

View extraction results:

```python
result = await extractor.extract(text)
print(f"Concepts: {result.concepts}")
print(f"Relationships: {result.relationships}")
```

Check Neo4j Browser:
- URL: http://localhost:7474
- Query: `MATCH (n) RETURN n LIMIT 25`

---

## Roadmap

### ✅ Phase 1-2: MVP (Complete)
- ✅ Neo4j integration
- ✅ Entity extraction with LLM
- ✅ Graph building (documents, concepts, relationships)
- ✅ Multi-tenancy support

### ✅ Phase 3: Graph Search (Complete)
- ✅ Query graph for concepts
- ✅ Multi-hop traversal (configurable max_hops)
- ✅ Return results as SearchResult objects
- ✅ Scoring based on concept relevance

### ✅ Phase 4: Hybrid Retrieval (Complete)
- ✅ Combine vector + graph results
- ✅ Reciprocal Rank Fusion (RRF) algorithm
- ✅ Configurable weighting (vector_weight, graph_weight)
- ✅ Metadata tracking for fusion sources

### ✅ Phase 5: Production Features (Complete)
- ✅ Knowledge graph statistics and analysis
- ✅ Performance benchmarking
- ✅ Most connected concepts queries
- ✅ Tenant isolation verification
- ✅ Comprehensive integration tests

### 🔮 Future Enhancements (Optional)
- Community detection algorithms
- PageRank for concept importance
- Graph embeddings (node2vec, DeepWalk)
- Temporal graphs (time-aware relationships)
- Custom reranking models
- Graph visualization API endpoints

---

## Best Practices

### 1. Entity Extraction

✅ **Do:**
- Use domain-specific documents
- Provide clear, technical content
- Extract from 200-5000 word documents (sweet spot)
- Use gpt-4o-mini for cost efficiency

❌ **Don't:**
- Extract from very short snippets (<100 words)
- Use overly generic content
- Extract from code snippets or data files

### 2. Graph Design

✅ **Do:**
- Use consistent concept names
- Leverage tenant_id for isolation
- Clean up old/unused concepts periodically
- Monitor graph size and query performance

❌ **Don't:**
- Create too fine-grained concepts
- Mix different tenant data
- Store large text in concept nodes (use Document.content)

### 3. Multi-Tenancy

✅ **Do:**
- Always provide tenant_id
- Filter queries by tenant_id
- Test tenant isolation in integration tests

❌ **Don't:**
- Share concepts across tenants (duplicates are OK)
- Query without tenant filters in production

---

## FAQ

**Q: Can I use GraphRAG without Neo4j?**

A: No, GraphRAG requires Neo4j for graph storage. However, traditional RAG works without it.

**Q: What's the difference between RAG and GraphRAG?**

A: Traditional RAG uses only vector search. GraphRAG adds knowledge graphs for relationship-aware retrieval.

**Q: Can I disable GraphRAG for specific documents?**

A: Yes, set `extract_entities=False` when ingesting.

**Q: How much does entity extraction cost?**

A: With gpt-4o-mini: ~$0.0002 per 1000-word document.

**Q: Can I customize the extraction prompt?**

A: Yes, modify `EXTRACTION_PROMPT` in `cortex/rag/graph/entity_extractor.py`.

**Q: Does GraphRAG work with existing documents?**

A: Yes, re-ingest with `extract_entities=True` to populate the graph.

---

## Support

- **Documentation**: [docs/GRAPHRAG.md](./GRAPHRAG.md)
- **Examples**: [examples/test_graphrag_mvp.py](../examples/test_graphrag_mvp.py)
- **Tests**: [tests/integration/rag/test_graphrag_mvp.py](../tests/integration/rag/test_graphrag_mvp.py)
- **Issues**: [GitHub Issues](https://github.com/yourusername/cortex-ai/issues)

---

**Built with ❤️ using Neo4j, LangGraph, and OpenAI**
