# Graph Neural Networks (GNN) for Cortex-AI GraphRAG

**Architectural guide for integrating GNNs into the knowledge graph retrieval system**

---

## 📚 Documentation Index

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Deep-dive into GNN integration architecture
- **[MODELS.md](MODELS.md)** - GNN model selection guide and comparison
- **[GETTING_STARTED.md](GETTING_STARTED.md)** - Hands-on prototyping guide

---

## What Are Graph Neural Networks?

Graph Neural Networks (GNNs) are deep learning models designed to operate on graph-structured data. Unlike traditional neural networks that work on fixed-size vectors, GNNs can learn representations for nodes, edges, and entire graphs by aggregating information from neighboring nodes.

**Key Concepts:**
- **Node Embeddings**: Dense vector representations of graph nodes (e.g., concepts)
- **Message Passing**: Nodes exchange information with neighbors through edges
- **Graph Convolution**: Aggregation of neighbor features (similar to CNN on images)
- **Inductive Learning**: Models generalize to new, unseen nodes (critical for growing knowledge graphs)

---

## Why GNNs Matter for GraphRAG

Cortex-AI's GraphRAG system currently uses **keyword-based concept matching** and **simple graph traversal**. GNNs can enhance this in several ways:

### Current Limitations:
1. **Keyword Matching Breaks on Synonyms**: "ML" vs "machine learning" treated as different concepts
2. **Missing Implicit Relationships**: Only explicitly extracted edges exist in the graph
3. **Equal Relationship Weighting**: All RELATES_TO edges treated equally in ranking
4. **No Graph-Aware Embeddings**: Document embeddings ignore graph structure
5. **Manual Fusion Weights**: RRF fusion uses fixed 0.7/0.3 weights (not learned)

### GNN Solutions:
1. **Semantic Concept Search**: Graph-aware embeddings handle synonyms naturally
2. **Link Prediction**: Discover missing relationships automatically
3. **Learned Attention**: GAT models learn which relationships matter most
4. **Structural Similarity**: Embeddings reflect graph neighborhoods
5. **Adaptive Fusion**: Learn optimal fusion weights from usage patterns

---

## 4 Critical Integration Points

### 1. Concept Embeddings (CRITICAL - Highest Impact)
**What:** Generate dense vector representations for each concept node using GraphSAGE

**Where:** `cortex/rag/graph/graph_store.py` + new `cortex/rag/gnn/concept_embedder.py`

**Impact:**
- ✅ Semantic concept search (handles synonyms)
- ✅ 20-30% better concept discovery
- ✅ Graph-aware similarity (concepts in similar neighborhoods cluster together)

**Example:**
```python
# Instead of keyword matching
concept = find_concept_by_name("machine learning")  # Fails for "ML"

# GNN embedding search
similar_concepts = search_concept_embeddings(query_embedding, top_k=5)
# Finds: ["machine learning", "ML", "deep learning", "artificial intelligence"]
```

---

### 2. Link Prediction (HIGH VALUE)
**What:** Predict missing RELATES_TO relationships using TransE/RotatE models

**Where:** `cortex/rag/document.py` + new `cortex/rag/gnn/link_predictor.py`

**Impact:**
- ✅ Discover implicit relationships ("Python" → "data science")
- ✅ Improve multi-hop traversal recall
- ✅ Enrich knowledge graph automatically

**Example:**
```python
# After entity extraction
predicted_links = link_predictor.predict_missing_relationships(
    confidence_threshold=0.8
)
# Adds: ("GraphRAG", "RELATES_TO", "vector search", confidence=0.89)
```

---

### 3. Graph Attention Ranking (ADVANCED)
**What:** Use Graph Attention Networks (GAT) to learn relationship importance

**Where:** `cortex/rag/retriever.py` + new `cortex/rag/gnn/gat_ranker.py`

**Impact:**
- ✅ Better ranking (important concepts weighted higher)
- ✅ Adaptive to query context
- ✅ Learns from usage patterns

**Example:**
```python
# Instead of equal weighting
neighbors = get_neighbors(concept, max_hops=2)  # All equal weight

# GAT attention
attention_weights = gat_model.compute_attention(concept, neighbors)
# Learns: Some relationships are 10x more important than others
```

---

### 4. Community Detection (MEDIUM PRIORITY)
**What:** Use Louvain algorithm to cluster related concepts into topics

**Where:** `cortex/rag/graph/graph_store.py` + new `cortex/rag/gnn/community_detector.py`

**Impact:**
- ✅ Auto-generate topic clusters
- ✅ Better navigation for large graphs
- ✅ Improved global question answering

**Example:**
```python
communities = graph_store.detect_communities()
# Returns: {"community_1": ["Python", "pandas", "numpy"],
#           "community_2": ["GraphRAG", "knowledge graph", "Neo4j"]}
```

---

## Architecture Overview

### Current System (No GNNs)
```
Query
  ├─→ Vector Search (OpenAI embeddings → Qdrant)
  └─→ Graph Search (Keyword extraction → Neo4j multi-hop)
        ↓
  RRF Fusion (static weights: 0.7 vector, 0.3 graph)
```

### With GNNs
```
Query
  ├─→ Vector Search (OpenAI → Qdrant documents)
  ├─→ Concept Search (GNN embeddings → Qdrant concepts) ★ NEW ★
  └─→ Graph Search (Semantic lookup → GAT-weighted traversal) ★ ENHANCED ★
        ↓
  Learned Fusion (adaptive weights) ★ NEW ★
```

**Key Change:** Concepts get their own embeddings and vector search, separate from documents.

---

## Technology Stack

### Recommended: PyTorch + PyTorch Geometric

**Why PyTorch Geometric (PyG)?**
- ✅ Mature, production-ready GNN library
- ✅ Rich model zoo (GraphSAGE, GCN, GAT, TransE built-in)
- ✅ Excellent documentation and tutorials
- ✅ GPU-accelerated (but CPU inference works well)
- ✅ Inductive learning support (handles new nodes)

**Dependencies to Add:**
```python
torch>=2.1.0                    # Core deep learning
torch-geometric>=2.4.0          # GNN library
torch-scatter>=2.1.0            # Scatter operations
torch-sparse>=0.6.0             # Sparse tensors
```

**Alternative:** DGL (Deep Graph Library) - also excellent, slightly steeper learning curve

---

## Current System Status

### What Exists:
- ✅ **Neo4j Knowledge Graph**: Document and Concept nodes with relationships
- ✅ **Multi-hop Graph Traversal**: Cypher queries with configurable depth
- ✅ **Entity Extraction**: LLM-based (gpt-4o-mini) concept extraction
- ✅ **Hybrid GraphRAG Search**: Vector + graph with RRF fusion
- ✅ **Qdrant Vector Store**: Dense + sparse vector search
- ✅ **Multi-tenancy**: Tenant-isolated graphs

### What's Missing for GNNs:
- ❌ **No Deep Learning Frameworks**: PyTorch, TensorFlow not installed
- ❌ **No Concept Embeddings**: Concepts stored as categorical names only
- ❌ **No Graph Algorithms**: PageRank, centrality, community detection
- ❌ **No Link Prediction**: Only explicitly extracted relationships exist
- ❌ **No Model Serving Infrastructure**: No registry, versioning, or batch inference

---

## Quick Start

For prototyping and evaluation, see:
- **[GETTING_STARTED.md](GETTING_STARTED.md)** - Step-by-step guide to building your first GNN prototype
- **[MODELS.md](MODELS.md)** - Which GNN model to choose for your use case

For detailed architecture and integration points, see:
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete technical architecture with code examples

---

## Expected Impact

### Performance Improvements:
| Metric | Current | With GNNs | Improvement |
|--------|---------|-----------|-------------|
| Concept Discovery Recall | 60% | 80-85% | +20-25% |
| Synonym Handling | Poor | Excellent | Semantic search |
| Multi-hop Relevance | 70% | 85-90% | +15-20% |
| Graph Enrichment | Manual | Automatic | Link prediction |

### Cost Considerations:
- **Training**: AWS p3.2xlarge ~$3/hour for 2-4 hours = $6-12 one-time
- **Inference**: CPU inference ~10-20ms/query (acceptable overhead)
- **Storage**: 10k concepts × 256D × 4 bytes ≈ 10MB (negligible)

---

## Roadmap

### Phase 1: Proof of Concept (1-2 weeks)
- Install PyTorch + PyTorch Geometric
- Generate concept embeddings (node2vec → GraphSAGE)
- Measure concept search accuracy vs keyword matching

### Phase 2: Production Integration (2-3 weeks)
- Store embeddings in Qdrant concept collection
- Integrate semantic concept search into `graphrag_search()`
- Add link prediction (TransE model)

### Phase 3: Advanced Features (3-6 months)
- GAT attention ranking
- Community detection API
- Learned fusion weights
- Temporal graphs

---

## FAQs

**Q: Do we need GPUs for GNNs?**
A: **Training:** Helpful but not required (small graphs train fine on CPU in minutes). **Inference:** CPU is sufficient (10-20ms per query).

**Q: How does this affect existing retrieval?**
A: **Zero breaking changes**. GNN features are additive - keyword-based graph search remains as fallback.

**Q: What if GraphSAGE embeddings are worse than keyword matching?**
A: Measure and compare. Start with hybrid approach: try GNN embeddings first, fall back to keywords if confidence is low.

**Q: Can we use pre-trained GNN models?**
A: For concept categorization (GCN), possibly. For embeddings (GraphSAGE) and link prediction (TransE), you need to train on your specific knowledge graph.

**Q: How do we handle new concepts?**
A: GraphSAGE is **inductive** - it can generate embeddings for new nodes without retraining, by aggregating from neighbors.

---

## Research Papers

- **GraphSAGE**: [Inductive Representation Learning on Large Graphs](https://arxiv.org/abs/1706.02216) (Hamilton et al., 2017)
- **TransE**: [Translating Embeddings for Modeling Multi-relational Data](https://papers.nips.cc/paper/2013/hash/1cecc7a77928ca8133fa24680a88d2f9-Abstract.html) (Bordes et al., 2013)
- **GAT**: [Graph Attention Networks](https://arxiv.org/abs/1710.10903) (Veličković et al., 2018)
- **RotatE**: [RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space](https://arxiv.org/abs/1902.10197) (Sun et al., 2019)

---

## Contributing

This is exploratory documentation for future GNN integration. To contribute:
1. Experiment with prototypes (see GETTING_STARTED.md)
2. Measure performance on real queries
3. Report findings and recommend next steps
4. Update documentation with lessons learned

---

**Last Updated:** March 28, 2026
**Status:** Exploratory - No implementation yet
**Maintained By:** Cortex-AI Team
