# GNN Integration Architecture

**Detailed technical architecture for integrating Graph Neural Networks into Cortex-AI GraphRAG**

---

## Table of Contents

1. [Current Architecture (Before GNNs)](#current-architecture-before-gnns)
2. [Target Architecture (With GNNs)](#target-architecture-with-gnns)
3. [Integration Point 1: Concept Embeddings](#integration-point-1-concept-embeddings)
4. [Integration Point 2: Link Prediction](#integration-point-2-link-prediction)
5. [Integration Point 3: Graph Attention Ranking](#integration-point-3-graph-attention-ranking)
6. [Integration Point 4: Community Detection](#integration-point-4-community-detection)
7. [Component Stack](#component-stack)
8. [Data Flow](#data-flow)
9. [Files to Create/Modify](#files-to-createmodify)
10. [Storage Layer Changes](#storage-layer-changes)

---

## Current Architecture (Before GNNs)

### System Overview

```
┌──────────────────────────────────────────────────────────┐
│                   Current GraphRAG System                 │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  User Query                                               │
│      │                                                    │
│      ├─→ [Vector Search]                                 │
│      │    └─ OpenAI embedding → Qdrant similarity        │
│      │                                                    │
│      └─→ [Graph Search]                                  │
│           └─ Keyword extraction → Neo4j multi-hop        │
│                                                           │
│  [RRF Fusion] ← Static weights (0.7 vector, 0.3 graph)   │
│      │                                                    │
│      └─→ Ranked Results                                  │
│                                                           │
│  Storage:                                                 │
│  ┌───────────┐  ┌──────────┐  ┌─────────┐              │
│  │ Qdrant    │  │ Neo4j    │  │ Redis   │              │
│  │           │  │          │  │         │              │
│  │ Document  │  │ Concepts │  │ Embed   │              │
│  │ vectors   │  │ +        │  │ cache   │              │
│  │ (1536D)   │  │ Relations│  │         │              │
│  └───────────┘  └──────────┘  └─────────┘              │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Current Neo4j Graph Schema

**Node Types:**
```cypher
(:Document {
    id: String,           // UUID
    content: Text,        // Full document text
    tenant_id: String,    // Multi-tenancy
    created_at: DateTime
})

(:Concept {
    id: String,           // UUID
    name: String,         // "GraphRAG", "Python", etc.
    category: String,     // "technology", "methodology", "language"
    tenant_id: String,
    created_at: DateTime
})
```

**Relationship Types:**
```cypher
(:Document)-[:MENTIONS {count: Int, confidence: Float}]->(:Concept)
(:Concept)-[:RELATES_TO {strength: Float, context: String}]-(:Concept)
```

### Current Retrieval Flow

**File:** `cortex/rag/retriever.py`

```python
async def graphrag_search(self, query: str, top_k: int = 5):
    """Hybrid GraphRAG search (vector + graph)."""

    # Step 1: Vector search
    query_embedding = await self.embeddings.generate_embedding(query)
    vector_results = await self.vector_store.search(
        query_vector=query_embedding,
        top_k=top_k * 2
    )

    # Step 2: Graph search (KEYWORD-BASED)
    concept_names = self._extract_concepts_from_query(query)  # Simple keyword extraction
    graph_results = []
    for concept_name in concept_names:
        results = await self.graph_search(concept_name, max_hops=2)
        graph_results.extend(results)

    # Step 3: RRF fusion with STATIC weights
    fused_results = self._fuse_results(
        vector_results,
        graph_results,
        alpha=0.7  # Fixed weight
    )

    return fused_results[:top_k]
```

**Cypher Query for Graph Traversal:**
```cypher
MATCH (c:Concept {name: $concept_name})
WHERE c.tenant_id = $tenant_id
WITH c
MATCH (c)-[:RELATES_TO*0..$max_hops]-(related:Concept)
WITH DISTINCT related
MATCH (d:Document)-[m:MENTIONS]->(related)
RETURN DISTINCT d.id, d.content,
       COUNT(DISTINCT related) as concept_count,
       SUM(m.confidence) as total_confidence
ORDER BY concept_count DESC, total_confidence DESC
```

### Limitations of Current Approach

1. **Keyword Matching:** `_extract_concepts_from_query()` uses simple keyword extraction
   - Breaks on synonyms: "ML" ≠ "machine learning"
   - No semantic understanding of concepts

2. **Static Traversal:** All `RELATES_TO` edges weighted equally
   - Relationship strength ignored in ranking
   - No learned importance (some relationships matter more)

3. **Fixed Fusion:** RRF alpha=0.7 hardcoded
   - Not optimized for specific domains
   - Same weights for all query types

4. **Document-Only Embeddings:** Concepts have no vector representation
   - Can't do semantic concept search
   - Graph structure ignored in embeddings

---

## Target Architecture (With GNNs)

### Enhanced System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│              GNN-Enhanced GraphRAG System                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  User Query                                                       │
│      │                                                            │
│      ├─→ [Vector Search]                                         │
│      │    └─ OpenAI embedding → Qdrant (documents)               │
│      │                                                            │
│      ├─→ [Semantic Concept Search] ★ NEW ★                       │
│      │    ├─ Query embedding                                     │
│      │    └─ Qdrant similarity search on concept embeddings      │
│      │                                                            │
│      └─→ [Graph Search] ★ ENHANCED ★                             │
│           ├─ Semantic concept lookup (not keywords)              │
│           ├─ GNN-weighted multi-hop traversal                    │
│           └─ Link prediction for missing relationships           │
│                                                                   │
│  [Learned Fusion] ★ NEW ★ ← GNN attention weights                │
│      │                                                            │
│      └─→ Ranked Results                                          │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Storage & Models Layer                      │   │
│  │                                                           │   │
│  │  ┌───────────┐  ┌──────────┐  ┌─────────┐  ┌─────────┐ │   │
│  │  │ Qdrant    │  │ Neo4j    │  │ Redis   │  │  GNN    │ │   │
│  │  │           │  │          │  │         │  │ Models  │ │   │
│  │  │ Docs      │  │ Concepts │  │ Embed   │  │         │ │   │
│  │  │ (1536D)   │  │ +        │  │ cache   │  │ Graph-  │ │   │
│  │  │           │  │ Relations│  │         │  │ SAGE    │ │   │
│  │  │ Concepts★ │  │ +        │  │         │  │ TransE  │ │   │
│  │  │ (256D)    │  │ Commun.★ │  │         │  │ GAT     │ │   │
│  │  └───────────┘  └──────────┘  └─────────┘  └─────────┘ │   │
│  │                                                           │   │
│  │  ★ New: Concept embeddings stored in separate collection│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Key Architectural Changes

| Component | Current | With GNNs | Benefit |
|-----------|---------|-----------|---------|
| **Concept Representation** | Categorical names | 256D embeddings (GraphSAGE) | Semantic similarity |
| **Concept Search** | Keyword matching | Vector similarity | Handles synonyms |
| **Relationship Discovery** | Manual extraction only | Automatic link prediction | Enriches graph |
| **Traversal Ranking** | Equal weights | GAT attention weights | Better relevance |
| **Fusion Strategy** | Fixed weights | Learned weights | Adaptive to domain |
| **Storage** | 1 Qdrant collection | 2 collections (docs + concepts) | Separate search spaces |

---

## Integration Point 1: Concept Embeddings

### Problem Statement
Concepts stored as categorical strings → keyword matching breaks on synonyms and semantically related terms.

### GNN Solution
Use **GraphSAGE** (Graph Sample and Aggregate) to generate graph-aware embeddings for concept nodes.

### Architecture

```
Concept Creation Flow:
    ↓
Generate text embedding (OpenAI)
    ↓
Load graph context (neighbors from Neo4j)
    ↓
GraphSAGE aggregation
    ↓
Store embedding in Qdrant (concept collection)
    ↓
Query time: Semantic similarity search on concepts
```

### Code Integration

**New Module:** `cortex/rag/gnn/concept_embedder.py`

```python
import torch
from torch_geometric.nn import SAGEConv
from typing import Any

class ConceptEmbedder:
    """Generate graph-aware embeddings for concepts using GraphSAGE."""

    def __init__(self,
        in_features: int = 1536,   # OpenAI embedding dim
        hidden_dim: int = 128,
        out_dim: int = 256          # Concept embedding dim
    ):
        self.model = GraphSAGEModel(in_features, hidden_dim, out_dim)
        self.model.eval()  # Inference mode

    async def generate_concept_embedding(self,
        concept_id: str,
        name: str,
        category: str,
        neighbors: list[dict]
    ) -> list[float]:
        """Generate embedding for a single concept."""

        # Get initial text embedding from OpenAI
        text_embedding = await openai.embed(f"{category}: {name}")

        # Get neighbor embeddings (if they exist)
        neighbor_embeddings = [
            n.get('embedding', text_embedding)  # Fallback to text if no GNN embedding yet
            for n in neighbors
        ]

        # GraphSAGE aggregation
        x = torch.tensor([text_embedding] + neighbor_embeddings)
        edge_index = self._build_edge_index(len(neighbors))

        with torch.no_grad():
            graph_embedding = self.model(x, edge_index)

        return graph_embedding[0].tolist()  # First node is our concept

    def _build_edge_index(self, num_neighbors: int) -> torch.Tensor:
        """Build edge index connecting concept (node 0) to neighbors (nodes 1..N)."""
        edges = [[0, i+1] for i in range(num_neighbors)] + \
                [[i+1, 0] for i in range(num_neighbors)]  # Bidirectional
        return torch.tensor(edges).t()


class GraphSAGEModel(torch.nn.Module):
    """GraphSAGE model definition."""

    def __init__(self, in_features: int, hidden_dim: int, out_dim: int):
        super().__init__()
        self.conv1 = SAGEConv(in_features, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, out_dim)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x, edge_index)
        x = torch.relu(x)
        x = self.conv2(x, edge_index)
        return x
```

**Modified:** `cortex/rag/graph/graph_store.py`

```python
class GraphStore:
    def __init__(self, ..., gnn_embedder: ConceptEmbedder | None = None):
        self.driver = driver
        self.vector_store = vector_store
        self.gnn_embedder = gnn_embedder  # NEW

    async def add_concept(self,
        name: str,
        category: str,
        tenant_id: str
    ) -> str:
        """Add concept to Neo4j + generate GNN embedding."""

        # Existing: Create concept node in Neo4j
        concept_id = await self._create_neo4j_concept(name, category, tenant_id)

        # NEW: Generate graph-aware embedding
        if self.gnn_embedder:
            neighbors = await self._get_neighbors(concept_id)
            concept_embedding = await self.gnn_embedder.generate_concept_embedding(
                concept_id=concept_id,
                name=name,
                category=category,
                neighbors=neighbors
            )

            # Store embedding in Qdrant (separate collection)
            await self.vector_store.add_concept_embedding(
                concept_id=concept_id,
                embedding=concept_embedding,
                metadata={
                    "name": name,
                    "category": category,
                    "tenant_id": tenant_id
                }
            )

        return concept_id
```

**Modified:** `cortex/rag/retriever.py`

```python
class Retriever:
    async def graphrag_search(self, query: str, top_k: int = 5):
        """Enhanced GraphRAG search with GNN concept embeddings."""

        # Vector search (unchanged)
        query_embedding = await self.embeddings.generate_embedding(query)
        vector_results = await self.vector_store.search(query_vector=query_embedding, top_k=top_k * 2)

        # NEW: Semantic concept search (replaces keyword extraction)
        similar_concepts = await self.vector_store.search_concept_embeddings(
            query_vector=query_embedding,
            top_k=5,
            tenant_id=self.tenant_id
        )

        # Graph traversal from similar concepts
        graph_results = []
        for concept in similar_concepts:
            docs = await self.graph_search(concept.name, max_hops=2)
            graph_results.extend(docs)

        # Fusion (unchanged for now, can be enhanced with learned weights later)
        fused_results = self._fuse_results(vector_results, graph_results, alpha=0.7)

        return fused_results[:top_k]
```

### Expected Impact

**Before:**
```python
query = "What is ML?"
concepts = extract_concepts("What is ML?")  # ["ml"] - lowercase, exact match
graph_results = []  # No match if concept stored as "Machine Learning"
```

**After:**
```python
query = "What is ML?"
query_embedding = openai.embed("What is ML?")
similar_concepts = qdrant.search_concepts(query_embedding)
# Returns: [("Machine Learning", 0.92), ("Deep Learning", 0.85), ("AI", 0.81)]
graph_results = traverse_from_concepts(similar_concepts)  # Rich results
```

---

## Integration Point 2: Link Prediction

### Problem Statement
Only explicitly extracted relationships exist → missing implicit connections between concepts.

### GNN Solution
Use **TransE** (Translating Embeddings) or **RotatE** for knowledge graph completion.

**TransE Intuition:** Models relationships as translations in embedding space.
- If (head, relation, tail) is true, then: `embedding(head) + embedding(relation) ≈ embedding(tail)`

### Architecture

```
Document Ingestion
    ↓
Entity Extraction (existing)
    ↓
Create Concepts + Relationships (existing)
    ↓
Link Prediction (NEW)
    ├─ Load current graph structure
    ├─ TransE model scores all possible pairs
    ├─ Filter high-confidence predictions (>0.8)
    └─ Add predicted relationships to Neo4j
```

### Code Integration

**New Module:** `cortex/rag/gnn/link_predictor.py`

```python
from torch_geometric.nn import TransE

class LinkPredictor:
    """Predict missing RELATES_TO relationships using TransE."""

    def __init__(self, embedding_dim: int = 256):
        self.model = TransE(
            num_nodes=0,  # Dynamically set
            num_relations=1,  # Single relation type: RELATES_TO
            embedding_dim=embedding_dim
        )

    async def predict_missing_relationships(self,
        graph_store: GraphStore,
        min_confidence: float = 0.8,
        top_k: int = 100
    ) -> list[dict]:
        """Predict missing relationships in knowledge graph."""

        # Get current graph
        concepts = await graph_store.get_all_concepts()
        edges = await graph_store.get_all_relationships()

        # Build concept_id → index mapping
        concept_to_idx = {c.id: i for i, c in enumerate(concepts)}

        # Prepare edge index for TransE
        edge_index = torch.tensor([
            [concept_to_idx[e['source_id']], concept_to_idx[e['target_id']]]
            for e in edges
        ]).t()

        # Score all possible pairs (expensive for large graphs)
        predictions = []
        for i, concept_a in enumerate(concepts):
            for j, concept_b in enumerate(concepts):
                if i != j and not self._edge_exists(i, j, edge_index):
                    # Predict link score
                    score = self.model.predict_link(
                        torch.tensor([i]),
                        torch.tensor([0]),  # Relation type 0 (RELATES_TO)
                        torch.tensor([j])
                    ).item()

                    if score >= min_confidence:
                        predictions.append({
                            'source_id': concept_a.id,
                            'target_id': concept_b.id,
                            'confidence': float(score),
                            'type': 'RELATES_TO',
                            'context': 'PREDICTED'
                        })

        return sorted(predictions, key=lambda x: x['confidence'], reverse=True)[:top_k]

    def _edge_exists(self, i: int, j: int, edge_index: torch.Tensor) -> bool:
        """Check if edge (i, j) exists in graph."""
        matches = (edge_index[0] == i) & (edge_index[1] == j)
        return matches.any().item()
```

**Modified:** `cortex/rag/document.py`

```python
class DocumentManager:
    def __init__(self, ..., link_predictor: LinkPredictor | None = None):
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.entity_extractor = entity_extractor
        self.link_predictor = link_predictor  # NEW

    async def ingest_document(self, doc_id: str, content: str, metadata: dict):
        """Ingest document with entity extraction and link prediction."""

        # Existing: Embed, store in Qdrant, extract entities, add to Neo4j
        await self._existing_ingestion_pipeline(doc_id, content, metadata)

        # NEW: Predict missing relationships
        if self.link_predictor:
            predicted_links = await self.link_predictor.predict_missing_relationships(
                graph_store=self.graph_store,
                min_confidence=0.8
            )

            # Add top 20 high-confidence predictions
            for link in predicted_links[:20]:
                await self.graph_store.add_relationship(
                    source_id=link['source_id'],
                    target_id=link['target_id'],
                    rel_type='RELATES_TO',
                    properties={
                        'strength': link['confidence'],
                        'context': 'PREDICTED',
                        'model': 'TransE'
                    }
                )
                logger.info(f"Added predicted relationship: {link}")
```

### Expected Impact

**Before:**
```cypher
// Only explicit relationships
MATCH (python:Concept {name: "Python"})-[:RELATES_TO]-(related)
RETURN related.name
// Returns: ["programming", "scripting"]  (only what LLM extracted)
```

**After:**
```cypher
// Explicit + predicted relationships
MATCH (python:Concept {name: "Python"})-[:RELATES_TO]-(related)
WHERE related.context IN ["EXTRACTED", "PREDICTED"]
RETURN related.name, related.context, related.strength
// Returns: ["programming" (EXTRACTED, 0.9),
//           "data science" (PREDICTED, 0.88),
//           "pandas" (PREDICTED, 0.85)]
```

---

## Integration Point 3: Graph Attention Ranking

### Problem Statement
All `RELATES_TO` edges weighted equally → ranking misses important relationships.

### GNN Solution
Use **Graph Attention Networks (GAT)** to learn which neighbors matter most.

**GAT Intuition:** Attention mechanism learns to focus on important neighbors.
- Each neighbor gets an attention weight: `α_ij = attention(node_i, neighbor_j)`
- Higher α → more important relationship

### Architecture

```
Graph Traversal
    ↓
Get neighbors (multi-hop)
    ↓
GAT computes attention weights
    ↓
Weight documents by attention × confidence
    ↓
Ranked results
```

### Code Integration

**New Module:** `cortex/rag/gnn/gat_ranker.py`

```python
from torch_geometric.nn import GATConv

class GATRanker:
    """Graph Attention Networks for relationship-aware ranking."""

    def __init__(self, hidden_dim: int = 128, heads: int = 4):
        self.gat = GATConv(
            in_channels=256,  # Concept embedding dim
            out_channels=hidden_dim,
            heads=heads,
            concat=False
        )
        self.gat.eval()

    async def compute_attention(self,
        node: Concept,
        neighbors: list[Concept],
        edge_features: list[dict]
    ) -> list[float]:
        """Compute attention weights for neighbors."""

        # Convert to PyTorch tensors
        node_embedding = torch.tensor(node.embedding).unsqueeze(0)
        neighbor_embeddings = torch.tensor([n.embedding for n in neighbors])
        x = torch.cat([node_embedding, neighbor_embeddings], dim=0)

        # Build edge index (star graph: node 0 connected to all neighbors)
        edge_index = self._build_edge_index(len(neighbors))

        # GAT forward pass with attention weights
        out, (edge_index, attention_weights) = self.gat(
            x,
            edge_index,
            return_attention_weights=True
        )

        # Extract attention weights for neighbors (exclude self-loop)
        return attention_weights[len(neighbors):].tolist()

    def _build_edge_index(self, num_neighbors: int) -> torch.Tensor:
        """Build star graph edge index."""
        edges = [[0, i+1] for i in range(num_neighbors)] + \
                [[i+1, 0] for i in range(num_neighbors)]
        return torch.tensor(edges).t()
```

**Modified:** `cortex/rag/retriever.py`

```python
class Retriever:
    def __init__(self, ..., gat_ranker: GATRanker | None = None):
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.gat_ranker = gat_ranker  # NEW

    async def graph_search(self, concept_name: str, max_hops: int = 2):
        """Graph search with GAT attention ranking."""

        # Find concept
        concept = await self._get_concept(concept_name)

        # Get neighbors via multi-hop traversal
        neighbors = await self._get_multi_hop_neighbors(concept.id, max_hops)

        # NEW: Compute attention weights using GAT
        if self.gat_ranker and concept.embedding:
            attention_weights = await self.gat_ranker.compute_attention(
                node=concept,
                neighbors=neighbors,
                edge_features=[n.relationship for n in neighbors]
            )
        else:
            # Fallback to uniform weights
            attention_weights = [1.0] * len(neighbors)

        # Score documents with attention-weighted importance
        scored_docs = []
        for neighbor, weight in zip(neighbors, attention_weights):
            docs = await self._get_docs_for_concept(neighbor.id)
            for doc in docs:
                # Attention-weighted scoring
                score = doc.base_score * weight
                scored_docs.append((doc, score))

        return sorted(scored_docs, key=lambda x: x[1], reverse=True)
```

### Expected Impact

**Before (Equal Weights):**
```
Neighbor A (weak relationship) → Document X (score=1.0)
Neighbor B (strong relationship) → Document Y (score=1.0)
Both ranked equally
```

**After (GAT Attention):**
```
Neighbor A → Attention weight: 0.2 → Document X (score=0.2)
Neighbor B → Attention weight: 0.8 → Document Y (score=0.8)
Document Y ranked 4x higher (learned importance)
```

---

## Integration Point 4: Community Detection

### Problem Statement
Large graphs (10k+ concepts) are hard to navigate → no automatic topic clustering.

### GNN Solution
Use **Louvain** or **Label Propagation** algorithms for community detection.

### Architecture

```
Knowledge Graph (Neo4j)
    ↓
Extract graph structure
    ↓
Run community detection (Louvain)
    ↓
Store community assignments in Neo4j
    ↓
API endpoint for community exploration
```

### Code Integration

**New Module:** `cortex/rag/gnn/community_detector.py`

```python
import community as community_louvain  # python-louvain package
import networkx as nx

class CommunityDetector:
    """Detect communities in concept graph using Louvain algorithm."""

    async def detect_communities(self,
        concepts: list[Concept],
        relationships: list[dict],
        algorithm: str = 'louvain'
    ) -> dict[str, list[str]]:
        """Detect communities in concept graph."""

        # Build NetworkX graph
        G = nx.Graph()
        for concept in concepts:
            G.add_node(concept.id, name=concept.name, category=concept.category)
        for rel in relationships:
            G.add_edge(
                rel['source_id'],
                rel['target_id'],
                weight=rel.get('strength', 1.0)
            )

        # Run community detection
        if algorithm == 'louvain':
            partition = community_louvain.best_partition(G)
        elif algorithm == 'label_propagation':
            communities = nx.algorithms.community.label_propagation_communities(G)
            partition = {}
            for i, community in enumerate(communities):
                for node in community:
                    partition[node] = i
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        # Group by community ID
        communities = {}
        for concept_id, community_id in partition.items():
            if community_id not in communities:
                communities[community_id] = []
            communities[community_id].append(concept_id)

        return communities
```

**Modified:** `cortex/rag/graph/graph_store.py`

```python
class GraphStore:
    async def detect_and_store_communities(self) -> dict[str, list[str]]:
        """Detect communities and store in Neo4j."""

        # Get graph structure
        concepts = await self.get_all_concepts()
        relationships = await self.get_all_relationships()

        # Run community detection
        detector = CommunityDetector()
        communities = await detector.detect_communities(concepts, relationships)

        # Store community assignments in Neo4j
        for community_id, concept_ids in communities.items():
            for concept_id in concept_ids:
                await self.driver.execute_write(
                    lambda tx: tx.run(
                        "MATCH (c:Concept {id: $id}) SET c.community = $community",
                        {"id": concept_id, "community": str(community_id)}
                    )
                )

        return communities
```

**New API Endpoint:** `cortex/api/routes/graph.py` (NEW FILE)

```python
from fastapi import APIRouter, Depends
from cortex.rag.graph.graph_store import GraphStore
from cortex.api.dependencies import get_graph_store, get_tenant_id

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])

@router.get("/communities")
async def get_communities(
    tenant_id: str = Depends(get_tenant_id),
    graph_store: GraphStore = Depends(get_graph_store)
):
    """Get concept communities for topic exploration."""

    communities = await graph_store.detect_and_store_communities()

    # Enrich with metadata
    enriched = {}
    for community_id, concept_ids in communities.items():
        concepts = [await graph_store.get_concept(cid) for cid in concept_ids]

        # Compute community metadata
        categories = [c.category for c in concepts]
        dominant_category = max(set(categories), key=categories.count)

        enriched[community_id] = {
            'size': len(concepts),
            'dominant_category': dominant_category,
            'top_concepts': sorted(
                [{'name': c.name, 'category': c.category} for c in concepts],
                key=lambda x: x.get('mention_count', 0),
                reverse=True
            )[:10]
        }

    return enriched
```

### Expected Impact

**Before:**
```
10,000 concepts in flat list → no organization
User must browse linearly or search by keyword
```

**After:**
```
Community 1: "Python Ecosystem" (250 concepts)
  - Python, pandas, numpy, scikit-learn, ...

Community 2: "Machine Learning" (180 concepts)
  - ML, neural networks, deep learning, GPT, ...

Community 3: "Web Development" (200 concepts)
  - JavaScript, React, Node.js, API, ...
```

---

## Component Stack

### Full Technology Stack

```
┌──────────────────────────────────────────────────────────────┐
│                    GNN Component Stack                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Application Layer (Existing)                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ FastAPI Routes │ Retriever │ GraphStore │ VectorStore  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                           │                                   │
│  ┌────────────────────────▼──────────────────────────────┐   │
│  │         GNN Service Layer (NEW)                       │   │
│  │                                                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │   │
│  │  │ Concept      │  │ Link         │  │ GAT        │ │   │
│  │  │ Embedder     │  │ Predictor    │  │ Ranker     │ │   │
│  │  │              │  │              │  │            │ │   │
│  │  │ GraphSAGE    │  │ TransE       │  │ Attention  │ │   │
│  │  │ + OpenAI     │  │ RotatE       │  │ Weights    │ │   │
│  │  └──────────────┘  └──────────────┘  └────────────┘ │   │
│  │                                                        │   │
│  │  ┌──────────────┐  ┌──────────────┐                  │   │
│  │  │ Community    │  │ Model        │                  │   │
│  │  │ Detector     │  │ Registry     │                  │   │
│  │  │              │  │              │                  │   │
│  │  │ Louvain      │  │ Artifacts    │                  │   │
│  │  └──────────────┘  └──────────────┘                  │   │
│  └────────────────────────────────────────────────────────┘   │
│                           │                                     │
│  Storage Layer (Enhanced)                                      │
│  ┌─────────────────────────▼──────────────────────────────┐   │
│  │ ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐  │   │
│  │ │ Qdrant  │  │ Neo4j   │  │ Redis   │  │ PostgreSQL│  │   │
│  │ │         │  │         │  │         │  │           │  │   │
│  │ │ Docs    │  │ Graph   │  │ Embed   │  │ GNN Model │  │   │
│  │ │ (1536D) │  │ +       │  │ cache   │  │ Metadata  │  │   │
│  │ │         │  │ Concept │  │         │  │ Versions  │  │   │
│  │ │ Concept │  │ Commun. │  │         │  │ Metrics   │  │   │
│  │ │ (256D)★ │  │ Props★  │  │         │  │           │  │   │
│  │ └─────────┘  └─────────┘  └─────────┘  └──────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Complete Query Flow with GNNs

```
User Query: "How does GraphRAG work?"
    │
    ├─→ [Step 1] Generate query embedding (OpenAI)
    │   Result: [0.123, -0.456, ..., 0.789] (1536D)
    │
    ├─→ [Step 2] Search concept embeddings (Qdrant) ★ GNN ★
    │   Input: query_embedding
    │   Model: GraphSAGE embeddings (256D)
    │   Output: [Concept("GraphRAG", score=0.95),
    │            Concept("knowledge graph", score=0.87),
    │            Concept("retrieval", score=0.82)]
    │
    ├─→ [Step 3] Multi-hop graph traversal (Neo4j) ★ GNN-enhanced ★
    │   For each concept:
    │     - Get neighbors via RELATES_TO (max_hops=2)
    │     - Compute GAT attention weights
    │     - Rank neighbors by attention × confidence
    │   Output: [Document IDs with attention-weighted scores]
    │
    ├─→ [Step 4] Predict missing relationships ★ GNN ★ (optional)
    │   Input: GraphRAG concept + discovered concepts
    │   Model: TransE
    │   Predictions:
    │     - ("GraphRAG", "RELATES_TO", "vector search", confidence=0.89)
    │     - ("GraphRAG", "RELATES_TO", "semantic search", confidence=0.85)
    │   Add to traversal candidates
    │
    ├─→ [Step 5] Retrieve documents (Qdrant)
    │   Get full content for top document IDs
    │
    └─→ [Step 6] Learned fusion ★ GNN ★ (optional)
        Combine vector results + graph results with learned weights
        (Alternative to fixed RRF weights: alpha learned via GNN)

Final Result: Top-K documents with GNN-enhanced relevance
```

---

## Files to Create/Modify

### New Files to Create

**GNN Service Layer:**
```
cortex/rag/gnn/                     # New module
├── __init__.py                     # Module initialization
├── concept_embedder.py             # GraphSAGE concept embeddings (250 lines)
├── link_predictor.py               # TransE/RotatE link prediction (200 lines)
├── gat_ranker.py                   # Graph Attention ranking (180 lines)
├── community_detector.py           # Louvain/Label Propagation (150 lines)
├── models/                         # Model definitions
│   ├── __init__.py
│   ├── graphsage.py                # GraphSAGE model class
│   ├── transe.py                   # TransE model class
│   └── gat.py                      # GAT model class
└── utils.py                        # Graph utilities (edge index building, etc.)
```

**API Extensions:**
```
cortex/api/routes/
└── graph.py                        # NEW: Graph endpoints (150 lines)
    ├── GET /api/v1/graph/concepts
    ├── GET /api/v1/graph/communities
    ├── GET /api/v1/graph/relationships/predict
    └── POST /api/v1/graph/embeddings/generate
```

### Existing Files to Modify

1. **cortex/rag/graph/graph_store.py** (~470 lines → ~550 lines)
   - Add: `generate_concept_embedding()` method
   - Add: `add_predicted_relationship()` method
   - Add: `detect_and_store_communities()` method
   - Modify: `add_concept()` to call GNN embedder

2. **cortex/rag/vector_store.py** (~684 lines → ~750 lines)
   - Add: `create_concept_collection()` method
   - Add: `search_concept_embeddings()` method
   - Add: `add_concept_embedding()` method

3. **cortex/rag/retriever.py** (~800 lines → ~900 lines)
   - Modify: `graphrag_search()` to use semantic concept search
   - Add: `concept_similarity_search()` method
   - Modify: `graph_search()` to use GAT attention weights

4. **cortex/rag/document.py** (~500 lines → ~550 lines)
   - Add: Link prediction after entity extraction
   - Add: Community detection trigger (optional, periodic)

5. **cortex/platform/config/settings.py** (~270 lines → ~290 lines)
   - Add: `gnn_enabled: bool = False`
   - Add: `gnn_model_path: str = "models/gnn"`
   - Add: `concept_embedding_dim: int = 256`
   - Add: `link_prediction_threshold: float = 0.8`

6. **requirements.txt** (~50 lines → ~55 lines)
   - Add PyTorch + PyTorch Geometric dependencies:
     ```
     torch>=2.1.0
     torch-geometric>=2.4.0
     torch-scatter>=2.1.0
     torch-sparse>=0.6.0
     python-louvain>=0.16  # For community detection
     ```

---

## Storage Layer Changes

### Qdrant Collections

**Before:** 1 collection
```python
# Collection: "documents"
{
    "id": "doc-123",
    "vector": [1536 dimensions],  # OpenAI embedding
    "payload": {
        "content": "...",
        "tenant_id": "t1",
        "source": "upload"
    }
}
```

**After:** 2 collections
```python
# Collection 1: "documents" (unchanged)
{
    "id": "doc-123",
    "vector": [1536 dimensions],
    "payload": {...}
}

# Collection 2: "concepts" (NEW)
{
    "id": "concept-456",
    "vector": [256 dimensions],  # GraphSAGE embedding
    "payload": {
        "name": "GraphRAG",
        "category": "methodology",
        "tenant_id": "t1",
        "community": "2"  # Community assignment
    }
}
```

**Qdrant API Changes:**
```python
# Create concept collection
await vector_store.create_concept_collection(
    collection_name="concepts",
    vector_size=256,  # GraphSAGE output dim
    distance_metric="cosine"
)

# Search concept embeddings
results = await vector_store.search_concept_embeddings(
    query_vector=query_embedding,
    top_k=5,
    filter={"tenant_id": "t1"}
)
```

### Neo4j Property Changes

**Before:**
```cypher
(:Concept {
    id: String,
    name: String,
    category: String,
    tenant_id: String,
    created_at: DateTime
})
```

**After:**
```cypher
(:Concept {
    id: String,
    name: String,
    category: String,
    tenant_id: String,
    created_at: DateTime,
    community: String,            // NEW: Community assignment
    embedding_version: String     // NEW: GNN model version
})

// Relationships also get new properties
-[:RELATES_TO {
    strength: Float,
    context: String,
    predicted: Boolean,           // NEW: True if link predicted
    model: String                 // NEW: "TransE", "RotatE", etc.
}]-
```

---

## Summary

### Integration Points at a Glance

| Component | File | Method | GNN Model | Lines Added |
|-----------|------|--------|-----------|-------------|
| **Concept Embeddings** | `cortex/rag/graph/graph_store.py` | `add_concept()` | GraphSAGE | ~30 |
| **Concept Search** | `cortex/rag/retriever.py` | `graphrag_search()` | GraphSAGE embeddings | ~20 |
| **Link Prediction** | `cortex/rag/document.py` | `ingest_document()` | TransE/RotatE | ~25 |
| **Attention Ranking** | `cortex/rag/retriever.py` | `graph_search()` | GAT | ~25 |
| **Community Detection** | `cortex/rag/graph/graph_store.py` | `detect_communities()` | Louvain | ~20 |
| **Vector Storage** | `cortex/rag/vector_store.py` | `create_concept_collection()` | N/A | ~30 |

**Total Existing Code Modified:** ~150 lines across 6 files
**Total New Code Added:** ~1,000 lines across 8 new files

---

**Next:** See [MODELS.md](MODELS.md) for detailed GNN model selection guide and [GETTING_STARTED.md](GETTING_STARTED.md) for hands-on prototyping.

---

**Last Updated:** March 28, 2026
**Maintained By:** Cortex-AI Team
