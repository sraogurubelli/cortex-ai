---
name: rag-query
description: GraphRAG and vector store query optimization. Auto-activates when working with RAG retrieval code.
paths:
  - "cortex/rag/**/*.py"
  - "tests/rag/**/*.py"
allowed-tools: Read, Grep, Glob, Edit
model: sonnet
effort: medium
---

# RAG Query Optimization

## Purpose

Optimize GraphRAG queries, debug retrieval issues, and improve relevance scoring.

## When to Use This Skill

**Auto-activates when:**
- Writing GraphRAG queries
- Debugging retrieval quality
- Optimizing embedding strategies
- Troubleshooting knowledge graph queries

**Manual invoke:** `/rag-query`

---

## Query Optimization Workflow

### 1. Choose Query Type

**Vector Search (Similarity):**
```python
from cortex.rag import VectorStore

results = await vector_store.similarity_search(
    query="User question",
    k=5,  # Top 5 results
    filter={"source": "documentation"},
)
```

**Graph Traversal (GraphRAG):**
```python
from cortex.rag import GraphRAG

results = await graph_rag.query(
    query="User question",
    depth=2,  # Traversal depth
    include_relationships=True,
)
```

**Hybrid (Vector + Graph):**
```python
results = await graph_rag.hybrid_search(
    query="User question",
    vector_weight=0.7,
    graph_weight=0.3,
)
```

---

## Debug Poor Retrieval

### Check Embedding Quality

```python
# Test embedding similarity
embedding1 = await embedder.embed("query text")
embedding2 = await embedder.embed("document text")

similarity = cosine_similarity(embedding1, embedding2)
print(f"Similarity: {similarity}")  # Should be > 0.7 for relevant docs
```

### Inspect Retrieved Chunks

```python
results = await vector_store.similarity_search(query, k=10)

for i, doc in enumerate(results):
    print(f"{i}. Score: {doc.score:.3f}")
    print(f"   Content: {doc.content[:100]}...")
    print(f"   Metadata: {doc.metadata}")
```

---

## Optimize Chunk Size

**Problem:** Chunks too large or too small affect retrieval.

**Solution:** Experiment with chunk size and overlap.

```python
# ✅ Good - Balanced chunks
chunker = TextChunker(
    chunk_size=512,  # Tokens per chunk
    chunk_overlap=50,  # Overlap for context
)

# ❌ Bad - Too large (loses precision)
chunker = TextChunker(chunk_size=2048, chunk_overlap=0)

# ❌ Bad - Too small (loses context)
chunker = TextChunker(chunk_size=128, chunk_overlap=0)
```

---

## Improve Graph Structure

**For GraphRAG:**

```python
# ✅ Good - Rich relationships
graph.add_entity(
    id="entity_id",
    type="Person",
    properties={"name": "John", "role": "Engineer"},
)

graph.add_relationship(
    source="entity_1",
    target="entity_2",
    type="WORKS_WITH",
    properties={"since": "2020"},
)

# ❌ Bad - Flat structure
# Just vector embeddings without relationships
```

---

## Common Issues

### Issue 1: Low Retrieval Relevance

**Symptoms:** Retrieved chunks not relevant to query.

**Debug:**
1. Check embedding model (try different models)
2. Inspect chunk quality (are they coherent?)
3. Adjust k (try more results, then re-rank)
4. Add metadata filters

**Solution:**
```python
# Try re-ranking
from cortex.rag import Reranker

reranker = Reranker(model="cross-encoder/ms-marco-MiniLM-L-12-v2")

# Get more candidates
candidates = await vector_store.similarity_search(query, k=20)

# Re-rank for precision
reranked = await reranker.rerank(query, candidates, top_k=5)
```

### Issue 2: Slow Queries

**Symptoms:** Queries take > 1 second.

**Debug:**
1. Check vector store index (is it built?)
2. Monitor embedding generation time
3. Profile graph traversal depth

**Solution:**
```python
# ✅ Good - Caching and batching
@lru_cache(maxsize=1000)
async def get_embeddings(text: str):
    return await embedder.embed(text)

# Batch queries
results = await vector_store.batch_search(queries, k=5)
```

### Issue 3: Missing Context

**Symptoms:** Chunks lack surrounding context.

**Solution:**
```python
# ✅ Good - Chunk with overlap
chunker = TextChunker(
    chunk_size=512,
    chunk_overlap=100,  # Include surrounding context
)

# ✅ Good - Retrieve parent chunks
results = await vector_store.similarity_search(query, k=5)

for doc in results:
    # Fetch parent document for context
    parent = await doc_store.get(doc.metadata["parent_id"])
```

---

## Performance Metrics

**Monitor these:**

```python
metrics = {
    "query_latency_ms": time_elapsed,
    "num_candidates": len(candidates),
    "num_results": len(filtered_results),
    "avg_relevance_score": avg_score,
    "embedding_cache_hit_rate": cache_hits / total_queries,
}

logger.info("RAG query completed", extra=metrics)
```

---

## Reference Files

- [GraphRAG Implementation](../../../cortex/rag/graphrag.py)
- [Vector Store](../../../cortex/rag/vector_store.py)
- [Embeddings](../../../cortex/rag/embeddings.py)
- [GraphRAG Docs](../../../docs/GRAPHRAG.md)
- [RAG Architecture](../../../docs/RAG.md)

---

**Need more help?** Check `.claude/rules/rag.md` for detailed guidelines.
