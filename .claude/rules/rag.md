---
paths:
  - "cortex/rag/**/*.py"
  - "tests/rag/**/*.py"
---

# RAG Development Rules

**Auto-loads when:** Working with RAG, GraphRAG, or vector store code

---

## Query Patterns

### Vector Search (Similarity)

```python
from cortex.rag import VectorStore

# ✅ Basic similarity search
results = await vector_store.similarity_search(
    query="User question",
    k=5,  # Top 5 results
    filter={"source": "documentation"},  # Optional metadata filter
)

# ✅ With score threshold
results = await vector_store.similarity_search(
    query="User question",
    k=10,
    score_threshold=0.7,  # Only results with score >= 0.7
)
```

### Graph Traversal (GraphRAG)

```python
from cortex.rag import GraphRAG

# ✅ Basic graph query
results = await graph_rag.query(
    query="User question",
    depth=2,  # Traversal depth (hops from starting nodes)
    include_relationships=True,  # Include edge information
)

# ✅ Hybrid (Vector + Graph)
results = await graph_rag.hybrid_search(
    query="User question",
    vector_weight=0.7,  # Weight for vector similarity
    graph_weight=0.3,   # Weight for graph traversal
    k=5,
)
```

---

## Chunk Optimization

✅ **Balanced chunk size:**

```python
from cortex.rag import TextChunker

# ✅ Good - Balanced chunks with overlap
chunker = TextChunker(
    chunk_size=512,      # Tokens per chunk (optimal for most embeddings)
    chunk_overlap=50,    # Overlap for context continuity
    separators=["\n\n", "\n", ". ", " "],  # Respect document structure
)

chunks = chunker.split_text(document)
```

❌ **Avoid extreme sizes:**

```python
# ❌ Too large - Loses precision
chunker = TextChunker(chunk_size=2048, chunk_overlap=0)

# ❌ Too small - Loses context
chunker = TextChunker(chunk_size=128, chunk_overlap=0)
```

**Rule:** Chunk size should match your embedding model's optimal input length (usually 256-512 tokens).

---

## Embedding Best Practices

✅ **Cache embeddings:**

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
async def get_embedding(text: str) -> list[float]:
    """Get embedding with caching."""
    return await embedder.embed(text)
```

✅ **Batch embeddings for efficiency:**

```python
# ✅ Good - Batch processing
texts = [chunk.content for chunk in chunks]
embeddings = await embedder.embed_batch(texts, batch_size=32)

# ❌ Bad - One at a time
embeddings = [await embedder.embed(text) for text in texts]
```

---

## Re-ranking for Precision

✅ **Use re-ranker after retrieval:**

```python
from cortex.rag import Reranker

reranker = Reranker(model="cross-encoder/ms-marco-MiniLM-L-12-v2")

# Step 1: Retrieve more candidates
candidates = await vector_store.similarity_search(query, k=20)

# Step 2: Re-rank for precision
reranked = await reranker.rerank(
    query=query,
    documents=candidates,
    top_k=5,  # Final number of results
)
```

**When to use:**
- Need high precision (top results must be very relevant)
- Have computational budget for second-pass ranking
- Retrieval returns many borderline results

---

## GraphRAG Structure

✅ **Rich entity and relationship modeling:**

```python
from cortex.rag import GraphRAG

graph = GraphRAG(neo4j_uri="bolt://localhost:7687")

# ✅ Good - Rich entities with properties
await graph.add_entity(
    id="person_john",
    type="Person",
    properties={
        "name": "John Doe",
        "role": "Engineer",
        "department": "AI/ML",
        "expertise": ["Python", "LLMs", "RAG"],
    },
)

# ✅ Good - Typed relationships with properties
await graph.add_relationship(
    source="person_john",
    target="project_cortex",
    type="WORKS_ON",
    properties={
        "since": "2024-01-01",
        "role": "Lead Developer",
    },
)
```

❌ **Avoid flat structure:**

```python
# ❌ Bad - Just vector embeddings, no graph
# Misses relationships and structured knowledge
```

---

## Performance Optimization

### 1. Indexing

```python
# ✅ Create indexes for fast retrieval
await vector_store.create_index(
    index_type="hnsw",  # Hierarchical Navigable Small World
    metric="cosine",     # Similarity metric
    ef_construction=200, # Index build quality
)

# For GraphRAG
await graph_rag.create_indexes([
    ("Person", "name"),
    ("Person", "email"),
    ("Document", "created_at"),
])
```

### 2. Caching

```python
from cortex.rag import QueryCache

cache = QueryCache(ttl=3600)  # 1 hour TTL

# ✅ Cache frequent queries
cached_results = await cache.get_or_compute(
    key=query,
    compute_fn=lambda: vector_store.similarity_search(query, k=5),
)
```

### 3. Monitoring

```python
import time
import logging

logger = logging.getLogger(__name__)

start = time.time()
results = await vector_store.similarity_search(query, k=5)
duration_ms = (time.time() - start) * 1000

logger.info(
    "RAG query completed",
    extra={
        "query": query[:100],
        "num_results": len(results),
        "duration_ms": duration_ms,
        "avg_score": sum(r.score for r in results) / len(results),
    },
)
```

**Targets:**
- Query latency: < 200ms for vector search
- Query latency: < 500ms for graph traversal
- Embedding generation: < 100ms per document

---

## Testing RAG Quality

### Retrieval Metrics

```python
import pytest
from cortex.rag import VectorStore

@pytest.mark.asyncio
async def test_retrieval_relevance():
    """Test that retrieval returns relevant documents."""
    vector_store = VectorStore(...)

    query = "How do I create an orchestration agent?"
    results = await vector_store.similarity_search(query, k=5)

    # Check we got results
    assert len(results) == 5

    # Check relevance scores
    assert all(r.score > 0.5 for r in results), "Low relevance scores"

    # Check top result contains key terms
    assert "agent" in results[0].content.lower()
    assert "orchestration" in results[0].content.lower()

@pytest.mark.asyncio
async def test_embedding_consistency():
    """Test embedding consistency for same text."""
    text = "Sample text for embedding"

    embedding1 = await embedder.embed(text)
    embedding2 = await embedder.embed(text)

    # Embeddings should be identical for same text
    assert embedding1 == embedding2
```

---

## Common Issues and Solutions

### Issue 1: Low Retrieval Relevance

**Symptoms:** Retrieved chunks not relevant to query.

**Solutions:**
1. Check embedding model quality
2. Adjust chunk size and overlap
3. Add metadata filters
4. Use re-ranking
5. Try hybrid search (vector + graph)

### Issue 2: Slow Queries

**Symptoms:** Queries take > 1 second.

**Solutions:**
1. Create vector indexes (HNSW)
2. Cache frequent queries
3. Batch embed operations
4. Reduce traversal depth (GraphRAG)

### Issue 3: Missing Context

**Symptoms:** Chunks lack surrounding context.

**Solutions:**
1. Increase chunk overlap
2. Retrieve parent/child chunks
3. Include metadata (source, section, page)

---

## Best Practices Summary

✅ **Do:**
- Use chunk size 256-512 tokens with overlap
- Cache embeddings and frequent queries
- Monitor query latency and relevance scores
- Use re-ranking for high-precision needs
- Create indexes before production
- Test retrieval quality with real queries
- Use hybrid search (vector + graph) when possible

❌ **Don't:**
- Embed entire documents without chunking
- Ignore chunk overlap (loses context)
- Skip indexing (slow queries)
- Hardcode chunk sizes (make configurable)
- Forget to monitor performance metrics
- Use only vector search (graphs add value)

---

## Reference Files

- [Vector Store](../../cortex/rag/vector_store.py)
- [GraphRAG](../../cortex/rag/graphrag.py)
- [Embeddings](../../cortex/rag/embeddings.py)
- [GraphRAG Docs](../../docs/GRAPHRAG.md)
- [RAG Architecture](../../docs/RAG.md)
