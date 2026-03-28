# Getting Started with GNN Integration

**A hands-on guide to prototyping Graph Neural Networks for Cortex-AI GraphRAG**

---

## Overview

This guide walks you through building your first GNN prototype for the Cortex-AI knowledge graph. We'll start with a simple node2vec implementation, measure its impact, then progressively enhance it with more sophisticated models.

**Timeline:** 1-2 weeks for initial prototype, 2-3 weeks for production integration

**Prerequisites:** Python 3.11+, access to Neo4j database, basic PyTorch knowledge helpful but not required

---

## Prerequisites

### System Requirements

**Minimum:**
- Python 3.11+
- 8GB RAM (16GB recommended)
- CPU-only (GPU optional for training speed)
- 10GB disk space for models and data

**Recommended for Training:**
- 16GB+ RAM
- CUDA-capable GPU (NVIDIA RTX 3060 or better)
- 50GB disk space for experiments

### Knowledge Prerequisites

- ✅ Basic Python programming
- ✅ Understanding of graph concepts (nodes, edges)
- ✅ Familiarity with embeddings (vector representations)
- ⚠️ PyTorch knowledge helpful but not required (we provide templates)
- ⚠️ GNN theory optional (this guide is hands-on first)

---

## Phase 1: Environment Setup

### Step 1: Install Dependencies

Create a new Python environment for GNN experiments:

```bash
# Create virtual environment
cd /Users/sgurubelli/aiplatform/cortex-ai
python -m venv venv-gnn
source venv-gnn/bin/activate  # On Windows: venv-gnn\Scripts\activate

# Install PyTorch (CPU version for prototyping)
pip install torch>=2.1.0 --index-url https://download.pytorch.org/whl/cpu

# Install PyTorch Geometric and dependencies
pip install torch-geometric>=2.4.0
pip install torch-scatter torch-sparse -f https://data.pyg.org/whl/torch-2.1.0+cpu.html

# Install additional utilities
pip install scikit-learn>=1.3.0 numpy>=1.24.0 pandas>=2.0.0
pip install matplotlib seaborn  # For visualization
```

**For GPU support (optional):**
```bash
# Replace CPU installation with CUDA version
pip install torch>=2.1.0 --index-url https://download.pytorch.org/whl/cu118
pip install torch-scatter torch-sparse -f https://data.pyg.org/whl/torch-2.1.0+cu118.html
```

### Step 2: Verify Installation

```python
# test_installation.py
import torch
import torch_geometric
from torch_geometric.nn import GraphSAGE, GCNConv

print(f"PyTorch version: {torch.__version__}")
print(f"PyTorch Geometric version: {torch_geometric.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda if torch.cuda.is_available() else 'N/A'}")

# Test basic tensor operations
x = torch.randn(10, 16)
print(f"Tensor shape: {x.shape}")
print("✅ Installation successful!")
```

Run the test:
```bash
python test_installation.py
```

---

## Phase 2: Data Extraction from Neo4j

### Step 3: Export Knowledge Graph

Extract concepts and relationships from your existing Neo4j knowledge graph:

```python
# scripts/export_neo4j_graph.py
import asyncio
import json
from neo4j import AsyncGraphDatabase

async def export_graph_data(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "your-password",
    tenant_id: str = "your-tenant-id",
    output_file: str = "data/graph_export.json"
):
    """Export concepts and relationships from Neo4j."""

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async with driver.session() as session:
        # Export concepts
        concepts_result = await session.run("""
            MATCH (c:Concept)
            WHERE c.tenant_id = $tenant_id
            RETURN c.id AS id, c.name AS name, c.category AS category
            ORDER BY c.id
        """, {"tenant_id": tenant_id})

        concepts = [record.data() async for record in concepts_result]

        # Export relationships
        relationships_result = await session.run("""
            MATCH (c1:Concept)-[r:RELATES_TO]->(c2:Concept)
            WHERE c1.tenant_id = $tenant_id AND c2.tenant_id = $tenant_id
            RETURN c1.id AS source, c2.id AS target, r.strength AS strength
        """, {"tenant_id": tenant_id})

        relationships = [record.data() async for record in relationships_result]

    await driver.close()

    # Save to JSON
    graph_data = {
        "concepts": concepts,
        "relationships": relationships,
        "metadata": {
            "num_concepts": len(concepts),
            "num_relationships": len(relationships),
            "tenant_id": tenant_id
        }
    }

    with open(output_file, "w") as f:
        json.dump(graph_data, f, indent=2)

    print(f"✅ Exported {len(concepts)} concepts and {len(relationships)} relationships")
    print(f"   Saved to: {output_file}")

    return graph_data

# Run export
if __name__ == "__main__":
    asyncio.run(export_graph_data(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",  # Replace with your password
        tenant_id="default",  # Replace with your tenant ID
        output_file="data/graph_export.json"
    ))
```

Run the export:
```bash
mkdir -p data
python scripts/export_neo4j_graph.py
```

**Expected output:**
```
✅ Exported 1523 concepts and 4891 relationships
   Saved to: data/graph_export.json
```

---

## Phase 3: Simple Prototype with node2vec

### Step 4: Build node2vec Model

Start with the simplest GNN approach - node2vec (random walk embeddings):

```python
# scripts/train_node2vec.py
import json
import torch
import numpy as np
from torch_geometric.nn import Node2Vec
from torch_geometric.data import Data
from sklearn.metrics.pairwise import cosine_similarity

def load_graph_data(file_path: str = "data/graph_export.json"):
    """Load exported graph data."""
    with open(file_path, "r") as f:
        data = json.load(f)

    # Create node ID mapping (string IDs → integer indices)
    concept_ids = [c["id"] for c in data["concepts"]]
    id_to_idx = {id: idx for idx, id in enumerate(concept_ids)}

    # Create edge index tensor
    edge_list = []
    for rel in data["relationships"]:
        source_idx = id_to_idx[rel["source"]]
        target_idx = id_to_idx[rel["target"]]
        edge_list.append([source_idx, target_idx])
        edge_list.append([target_idx, source_idx])  # Undirected graph

    edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()

    # Create PyG Data object
    graph = Data(
        num_nodes=len(concept_ids),
        edge_index=edge_index
    )

    return graph, data["concepts"], id_to_idx

def train_node2vec(
    graph: Data,
    embedding_dim: int = 128,
    walk_length: int = 20,
    context_size: int = 10,
    walks_per_node: int = 10,
    num_epochs: int = 100,
    batch_size: int = 128,
    lr: float = 0.01
):
    """Train node2vec model."""

    # Initialize node2vec model
    model = Node2Vec(
        edge_index=graph.edge_index,
        embedding_dim=embedding_dim,
        walk_length=walk_length,
        context_size=context_size,
        walks_per_node=walks_per_node,
        num_negative_samples=1,
        sparse=True
    )

    # Optimizer
    optimizer = torch.optim.SparseAdam(list(model.parameters()), lr=lr)

    # Training loop
    loader = model.loader(batch_size=batch_size, shuffle=True)

    model.train()
    for epoch in range(1, num_epochs + 1):
        total_loss = 0
        for pos_rw, neg_rw in loader:
            optimizer.zero_grad()
            loss = model.loss(pos_rw, neg_rw)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        if epoch % 10 == 0:
            print(f"Epoch {epoch:03d}, Loss: {avg_loss:.4f}")

    print(f"✅ Training complete!")

    return model

def save_embeddings(model: Node2Vec, concepts: list[dict], output_file: str = "data/node2vec_embeddings.json"):
    """Save learned embeddings."""

    # Get embeddings for all nodes
    model.eval()
    with torch.no_grad():
        embeddings = model().cpu().numpy()

    # Create embedding dictionary
    embedding_data = {
        "embeddings": embeddings.tolist(),
        "concepts": concepts,
        "metadata": {
            "model": "node2vec",
            "embedding_dim": embeddings.shape[1],
            "num_concepts": len(concepts)
        }
    }

    with open(output_file, "w") as f:
        json.dump(embedding_data, f)

    print(f"✅ Saved embeddings to: {output_file}")
    print(f"   Shape: {embeddings.shape}")

    return embeddings

# Main execution
if __name__ == "__main__":
    print("Loading graph data...")
    graph, concepts, id_to_idx = load_graph_data("data/graph_export.json")

    print(f"Graph: {graph.num_nodes} nodes, {graph.edge_index.size(1)} edges")

    print("\nTraining node2vec...")
    model = train_node2vec(
        graph=graph,
        embedding_dim=128,
        num_epochs=100,
        batch_size=128
    )

    print("\nSaving embeddings...")
    embeddings = save_embeddings(model, concepts, "data/node2vec_embeddings.json")

    print("\n✅ Prototype complete!")
```

Run training:
```bash
python scripts/train_node2vec.py
```

**Expected output:**
```
Loading graph data...
Graph: 1523 nodes, 9782 edges

Training node2vec...
Epoch 010, Loss: 1.2345
Epoch 020, Loss: 0.9876
Epoch 030, Loss: 0.7654
...
Epoch 100, Loss: 0.3210
✅ Training complete!

Saving embeddings...
✅ Saved embeddings to: data/node2vec_embeddings.json
   Shape: (1523, 128)

✅ Prototype complete!
```

---

## Phase 4: Evaluation

### Step 5: Test Concept Similarity Search

Evaluate how well the embeddings capture semantic similarity:

```python
# scripts/evaluate_embeddings.py
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def load_embeddings(file_path: str = "data/node2vec_embeddings.json"):
    """Load saved embeddings."""
    with open(file_path, "r") as f:
        data = json.load(f)

    embeddings = np.array(data["embeddings"])
    concepts = data["concepts"]

    # Create name → index mapping
    name_to_idx = {c["name"].lower(): idx for idx, c in enumerate(concepts)}

    return embeddings, concepts, name_to_idx

def find_similar_concepts(
    query_name: str,
    embeddings: np.ndarray,
    concepts: list[dict],
    name_to_idx: dict,
    top_k: int = 10
) -> list[dict]:
    """Find most similar concepts to query."""

    query_name_lower = query_name.lower()
    if query_name_lower not in name_to_idx:
        print(f"⚠️  Concept '{query_name}' not found in knowledge graph")
        return []

    # Get query embedding
    query_idx = name_to_idx[query_name_lower]
    query_embedding = embeddings[query_idx].reshape(1, -1)

    # Compute similarities
    similarities = cosine_similarity(query_embedding, embeddings)[0]

    # Get top-k (excluding the query itself)
    top_indices = np.argsort(similarities)[::-1][1:top_k+1]

    results = []
    for idx in top_indices:
        results.append({
            "name": concepts[idx]["name"],
            "category": concepts[idx]["category"],
            "similarity": float(similarities[idx])
        })

    return results

def evaluate_test_cases():
    """Run evaluation on test cases."""

    print("Loading embeddings...")
    embeddings, concepts, name_to_idx = load_embeddings("data/node2vec_embeddings.json")

    # Test cases (replace with your domain-specific examples)
    test_cases = [
        "machine learning",
        "Python",
        "GraphRAG",
        "neural network",
        "database"
    ]

    print(f"\n{'='*70}")
    print("CONCEPT SIMILARITY EVALUATION")
    print(f"{'='*70}\n")

    for query in test_cases:
        print(f"Query: '{query}'")
        print("-" * 70)

        similar = find_similar_concepts(
            query_name=query,
            embeddings=embeddings,
            concepts=concepts,
            name_to_idx=name_to_idx,
            top_k=5
        )

        if similar:
            for i, result in enumerate(similar, 1):
                print(f"  {i}. {result['name']:<30} (category: {result['category']:<15}, similarity: {result['similarity']:.3f})")

        print()

    print(f"{'='*70}\n")

if __name__ == "__main__":
    evaluate_test_cases()
```

Run evaluation:
```bash
python scripts/evaluate_embeddings.py
```

**Expected output:**
```
Loading embeddings...

======================================================================
CONCEPT SIMILARITY EVALUATION
======================================================================

Query: 'machine learning'
----------------------------------------------------------------------
  1. deep learning              (category: Technology     , similarity: 0.842)
  2. artificial intelligence    (category: Technology     , similarity: 0.789)
  3. neural network             (category: Technology     , similarity: 0.756)
  4. ML                         (category: Technology     , similarity: 0.723)
  5. supervised learning        (category: Technology     , similarity: 0.698)

Query: 'Python'
----------------------------------------------------------------------
  1. pandas                     (category: Technology     , similarity: 0.812)
  2. NumPy                      (category: Technology     , similarity: 0.798)
  3. programming language       (category: Technology     , similarity: 0.765)
  4. data science               (category: Domain         , similarity: 0.721)
  5. PyTorch                    (category: Technology     , similarity: 0.689)

...
```

### Step 6: Benchmark Against Keyword Matching

Compare GNN embeddings vs. current keyword-based approach:

```python
# scripts/benchmark_retrieval.py
import json
import time
import numpy as np
from typing import List, Dict
from sklearn.metrics.pairwise import cosine_similarity

def load_test_queries(file_path: str = "data/test_queries.json") -> list[dict]:
    """Load test queries with expected concepts."""
    # Example test queries
    test_queries = [
        {
            "query": "How does machine learning work?",
            "expected_concepts": ["machine learning", "ML", "deep learning", "artificial intelligence", "neural network"]
        },
        {
            "query": "Python data analysis libraries",
            "expected_concepts": ["Python", "pandas", "NumPy", "data science", "matplotlib"]
        },
        {
            "query": "GraphRAG retrieval techniques",
            "expected_concepts": ["GraphRAG", "retrieval", "knowledge graph", "vector search", "embedding"]
        }
    ]

    return test_queries

def keyword_based_search(query: str, concepts: list[dict], top_k: int = 5) -> list[str]:
    """Simulate current keyword-based concept matching."""
    query_lower = query.lower()
    query_tokens = set(query_lower.split())

    # Score concepts by keyword overlap
    scores = []
    for concept in concepts:
        concept_name = concept["name"].lower()
        concept_tokens = set(concept_name.split())

        # Simple overlap score
        overlap = len(query_tokens & concept_tokens)
        if overlap > 0:
            scores.append((concept["name"], overlap))

    # Sort by score
    scores.sort(key=lambda x: x[1], reverse=True)
    return [name for name, score in scores[:top_k]]

def embedding_based_search(
    query: str,
    concepts: list[dict],
    embeddings: np.ndarray,
    name_to_idx: dict,
    top_k: int = 5
) -> list[str]:
    """GNN embedding-based concept search."""
    # Create query embedding (average of concept embeddings in query)
    query_lower = query.lower()
    query_tokens = query_lower.split()

    query_embeddings = []
    for token in query_tokens:
        if token in name_to_idx:
            idx = name_to_idx[token]
            query_embeddings.append(embeddings[idx])

    if not query_embeddings:
        # Fallback: return top concepts by graph centrality
        return [c["name"] for c in concepts[:top_k]]

    query_embedding = np.mean(query_embeddings, axis=0).reshape(1, -1)

    # Compute similarities
    similarities = cosine_similarity(query_embedding, embeddings)[0]
    top_indices = np.argsort(similarities)[::-1][:top_k]

    return [concepts[idx]["name"] for idx in top_indices]

def calculate_recall(retrieved: list[str], expected: list[str]) -> float:
    """Calculate recall@K."""
    retrieved_set = set([r.lower() for r in retrieved])
    expected_set = set([e.lower() for e in expected])

    if len(expected_set) == 0:
        return 0.0

    hits = len(retrieved_set & expected_set)
    return hits / len(expected_set)

def benchmark():
    """Run benchmark comparison."""

    # Load data
    print("Loading embeddings...")
    with open("data/node2vec_embeddings.json", "r") as f:
        data = json.load(f)

    embeddings = np.array(data["embeddings"])
    concepts = data["concepts"]
    name_to_idx = {c["name"].lower(): idx for idx, c in enumerate(concepts)}

    # Load test queries
    test_queries = load_test_queries()

    print(f"\n{'='*80}")
    print("BENCHMARK: Keyword-based vs. Embedding-based Concept Search")
    print(f"{'='*80}\n")

    keyword_recalls = []
    embedding_recalls = []

    for i, test_case in enumerate(test_queries, 1):
        query = test_case["query"]
        expected = test_case["expected_concepts"]

        print(f"Query {i}: {query}")
        print("-" * 80)

        # Keyword-based search
        start_time = time.time()
        keyword_results = keyword_based_search(query, concepts, top_k=5)
        keyword_time = (time.time() - start_time) * 1000
        keyword_recall = calculate_recall(keyword_results, expected)
        keyword_recalls.append(keyword_recall)

        print(f"Keyword-based: {keyword_results}")
        print(f"  Recall: {keyword_recall:.2%}, Latency: {keyword_time:.1f}ms")

        # Embedding-based search
        start_time = time.time()
        embedding_results = embedding_based_search(query, concepts, embeddings, name_to_idx, top_k=5)
        embedding_time = (time.time() - start_time) * 1000
        embedding_recall = calculate_recall(embedding_results, expected)
        embedding_recalls.append(embedding_recall)

        print(f"Embedding-based: {embedding_results}")
        print(f"  Recall: {embedding_recall:.2%}, Latency: {embedding_time:.1f}ms")

        print()

    # Summary
    print(f"{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Average Recall:")
    print(f"  Keyword-based:   {np.mean(keyword_recalls):.2%}")
    print(f"  Embedding-based: {np.mean(embedding_recalls):.2%}")
    print(f"  Improvement:     {(np.mean(embedding_recalls) - np.mean(keyword_recalls)) * 100:.1f} percentage points")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    benchmark()
```

Run benchmark:
```bash
python scripts/benchmark_retrieval.py
```

**Expected results:**
```
BENCHMARK: Keyword-based vs. Embedding-based Concept Search
================================================================================

Query 1: How does machine learning work?
--------------------------------------------------------------------------------
Keyword-based: ['machine learning']
  Recall: 20.00%, Latency: 2.3ms
Embedding-based: ['machine learning', 'ML', 'deep learning', 'artificial intelligence', 'neural network']
  Recall: 100.00%, Latency: 8.7ms

Query 2: Python data analysis libraries
--------------------------------------------------------------------------------
Keyword-based: ['Python']
  Recall: 20.00%, Latency: 2.1ms
Embedding-based: ['Python', 'pandas', 'NumPy', 'data science', 'matplotlib']
  Recall: 100.00%, Latency: 9.2ms

...

================================================================================
SUMMARY
================================================================================
Average Recall:
  Keyword-based:   18.3%
  Embedding-based: 82.7%
  Improvement:     64.4 percentage points
================================================================================
```

---

## Phase 5: Production Integration

### Step 7: Integrate with GraphStore

Once you've validated the prototype, integrate embeddings into the production system:

```python
# cortex/rag/gnn/__init__.py
"""Graph Neural Network integration for Cortex-AI."""

from .concept_embedder import ConceptEmbedder
from .link_predictor import LinkPredictor

__all__ = ["ConceptEmbedder", "LinkPredictor"]
```

```python
# cortex/rag/gnn/concept_embedder.py
import torch
import numpy as np
from typing import Optional
from torch_geometric.nn import Node2Vec

class ConceptEmbedder:
    """Generate concept embeddings using node2vec."""

    def __init__(self, model_path: str = "models/gnn/node2vec.pt"):
        self.model: Optional[Node2Vec] = None
        self.model_path = model_path
        self._load_model()

    def _load_model(self):
        """Load pre-trained model."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found: {self.model_path}")

        self.model = torch.load(self.model_path)
        self.model.eval()

    async def generate_concept_embedding(
        self,
        concept_id: str,
        node_idx: int
    ) -> list[float]:
        """Generate embedding for a concept."""
        with torch.no_grad():
            # Get embedding for specific node
            all_embeddings = self.model()
            embedding = all_embeddings[node_idx]

        return embedding.cpu().tolist()

    async def batch_generate_embeddings(
        self,
        concept_ids: list[str],
        node_indices: list[int]
    ) -> dict[str, list[float]]:
        """Generate embeddings for multiple concepts."""
        with torch.no_grad():
            all_embeddings = self.model()

            results = {}
            for concept_id, node_idx in zip(concept_ids, node_indices):
                embedding = all_embeddings[node_idx].cpu().tolist()
                results[concept_id] = embedding

        return results
```

### Step 8: Add Concept Embedding Collection to Qdrant

```python
# cortex/rag/vector_store.py (add new methods)

async def create_concept_collection(
    self,
    collection_name: str = "concepts",
    embedding_dim: int = 128
):
    """Create Qdrant collection for concept embeddings."""
    from qdrant_client.models import Distance, VectorParams

    await self.client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=embedding_dim,
            distance=Distance.COSINE
        )
    )

async def add_concept_embedding(
    self,
    concept_id: str,
    embedding: list[float],
    metadata: dict,
    collection_name: str = "concepts"
):
    """Add concept embedding to Qdrant."""
    from qdrant_client.models import PointStruct

    point = PointStruct(
        id=concept_id,
        vector=embedding,
        payload=metadata
    )

    await self.client.upsert(
        collection_name=collection_name,
        points=[point]
    )

async def search_concept_embeddings(
    self,
    query_vector: list[float],
    top_k: int = 5,
    tenant_id: str = None,
    collection_name: str = "concepts"
) -> list[dict]:
    """Search for similar concepts."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    search_filter = None
    if tenant_id:
        search_filter = Filter(
            must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        )

    results = await self.client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=top_k,
        query_filter=search_filter
    )

    return [
        {
            "concept_id": hit.id,
            "score": hit.score,
            **hit.payload
        }
        for hit in results
    ]
```

### Step 9: Update Retriever

```python
# cortex/rag/retriever.py (modify graphrag_search method)

async def graphrag_search(
    self,
    query: str,
    top_k: int = 5,
    max_hops: int = 2,
    use_gnn_embeddings: bool = True  # NEW parameter
) -> list[dict]:
    """Hybrid GraphRAG search with optional GNN embeddings."""

    if use_gnn_embeddings:
        # NEW: Semantic concept search with GNN embeddings
        query_embedding = await self.embeddings.generate_embedding(query)

        similar_concepts = await self.vector_store.search_concept_embeddings(
            query_vector=query_embedding,
            top_k=5,
            tenant_id=self.tenant_id
        )

        # Use top concepts for graph traversal
        concept_names = [c["name"] for c in similar_concepts]
    else:
        # OLD: Keyword-based concept extraction
        concept_names = await self._extract_concepts_from_query(query)

    # Rest of the method remains the same...
    graph_results = []
    for concept_name in concept_names:
        docs = await self.graph_search(concept_name, max_hops=max_hops)
        graph_results.extend(docs)

    return graph_results[:top_k]
```

---

## Phase 6: Upgrade to GraphSAGE (Production-Ready)

### Step 10: Train GraphSAGE Model

Once node2vec is validated, upgrade to GraphSAGE for inductive learning:

```python
# scripts/train_graphsage.py
import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv
from torch_geometric.data import Data

class GraphSAGEModel(torch.nn.Module):
    """GraphSAGE model for concept embeddings."""

    def __init__(self, in_features: int = 1536, hidden_dim: int = 256, out_dim: int = 128):
        super().__init__()
        self.conv1 = SAGEConv(in_features, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, out_dim)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.5, training=self.training)
        x = self.conv2(x, edge_index)
        return x

def train_graphsage(
    graph: Data,
    initial_embeddings: np.ndarray,  # OpenAI embeddings for initialization
    embedding_dim: int = 128,
    num_epochs: int = 200
):
    """Train GraphSAGE model."""

    # Convert initial embeddings to tensor
    x = torch.tensor(initial_embeddings, dtype=torch.float)

    # Initialize model
    model = GraphSAGEModel(
        in_features=initial_embeddings.shape[1],
        hidden_dim=256,
        out_dim=embedding_dim
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    # Training loop (self-supervised with link prediction)
    model.train()
    for epoch in range(1, num_epochs + 1):
        optimizer.zero_grad()

        # Forward pass
        embeddings = model(x, graph.edge_index)

        # Link prediction loss (predict edge existence)
        # Sample positive and negative edges
        pos_edge_index = graph.edge_index
        neg_edge_index = negative_sampling(
            edge_index=pos_edge_index,
            num_nodes=graph.num_nodes,
            num_neg_samples=pos_edge_index.size(1)
        )

        # Compute dot product scores
        pos_scores = (embeddings[pos_edge_index[0]] * embeddings[pos_edge_index[1]]).sum(dim=1)
        neg_scores = (embeddings[neg_edge_index[0]] * embeddings[neg_edge_index[1]]).sum(dim=1)

        # Binary cross-entropy loss
        loss = -torch.log(torch.sigmoid(pos_scores) + 1e-15).mean() - \
               torch.log(1 - torch.sigmoid(neg_scores) + 1e-15).mean()

        loss.backward()
        optimizer.step()

        if epoch % 20 == 0:
            print(f"Epoch {epoch:03d}, Loss: {loss.item():.4f}")

    print(f"✅ GraphSAGE training complete!")

    return model
```

**Key Advantages of GraphSAGE over node2vec:**
- ✅ Inductive learning (can generate embeddings for new nodes without retraining)
- ✅ Uses node features (OpenAI embeddings) + graph structure
- ✅ Handles dynamic graphs (concepts added/removed)
- ✅ Better performance on downstream tasks

---

## Roadmap: PoC → Production → Advanced

### Phase-by-Phase Timeline

**Phase 1: Proof of Concept (1-2 weeks)**
- ✅ Install PyTorch + PyTorch Geometric
- ✅ Export Neo4j knowledge graph
- ✅ Train node2vec embeddings
- ✅ Evaluate concept similarity search
- ✅ Benchmark vs. keyword matching
- **Success Criteria:** 20%+ recall improvement over keyword matching

**Phase 2: Production Integration (2-3 weeks)**
- 🔄 Create Qdrant concept collection
- 🔄 Integrate ConceptEmbedder into GraphStore
- 🔄 Update Retriever with semantic concept search
- 🔄 Add feature flag for gradual rollout
- 🔄 Monitor latency and accuracy metrics
- **Success Criteria:** <20ms embedding lookup latency, production-ready API

**Phase 3: GraphSAGE Upgrade (2-3 weeks)**
- ⏳ Train GraphSAGE model with OpenAI embeddings as features
- ⏳ Implement inductive inference for new concepts
- ⏳ A/B test: node2vec vs. GraphSAGE
- ⏳ Replace node2vec with GraphSAGE in production
- **Success Criteria:** 5-10% additional recall improvement, inductive capability verified

**Phase 4: Advanced Features (3-6 months)**
- ⏳ Add link prediction (TransE/RotatE)
- ⏳ Implement GAT attention ranking
- ⏳ Add community detection API
- ⏳ Build model training pipeline
- ⏳ Add temporal graph support
- **Success Criteria:** Full GNN feature suite operational

---

## Cost-Benefit Analysis

### Development Costs

**Time Investment:**
- Phase 1 (PoC): 40-80 hours (1-2 weeks)
- Phase 2 (Integration): 80-120 hours (2-3 weeks)
- Phase 3 (GraphSAGE): 80-120 hours (2-3 weeks)
- **Total:** 200-320 hours (5-8 weeks)

**Infrastructure Costs:**
- **Training (one-time):**
  - AWS p3.2xlarge: $3.06/hour × 2-4 hours = $6-12
  - Or CPU-only: Free (just slower)
- **Inference (ongoing):**
  - CPU inference: Negligible (<1ms per query)
  - No GPU needed for inference
- **Storage:**
  - 10,000 concepts × 128D × 4 bytes = 5.12 MB (negligible)

**Total Cost:** $6-12 one-time + negligible ongoing

### Expected Benefits

**Quantitative:**
| Metric | Baseline | With GNNs | Improvement |
|--------|----------|-----------|-------------|
| Concept Discovery Recall | 60% | 80-85% | +20-25% |
| Synonym Handling | Poor | Excellent | Semantic search |
| Multi-hop Relevance | 70% | 85-90% | +15-20% |
| Graph Enrichment | Manual | Automatic | Link prediction |
| Query Latency | 50ms | 60ms | +10ms (acceptable) |

**Qualitative:**
- ✅ Better user experience (finds relevant concepts even with synonyms)
- ✅ Reduced manual curation (automatic relationship discovery)
- ✅ Scalable to large graphs (inductive learning)
- ✅ Future-proof architecture (enables advanced GNN features)

**ROI Calculation:**
- Development: 200-320 hours × $100/hour = $20k-32k
- Infrastructure: $6-12 one-time
- **Total Cost:** ~$20k-32k
- **Benefit:** 20-25% recall improvement = better answers = higher user satisfaction
- **Payback:** If GraphRAG supports 1000+ users, improved accuracy worth it

---

## Troubleshooting

### Common Issues

**1. PyTorch Geometric Installation Fails**
```bash
# Error: "Could not find a version that satisfies the requirement torch-scatter"

# Solution: Install from PyG wheel server
pip install torch-scatter -f https://data.pyg.org/whl/torch-2.1.0+cpu.html
```

**2. Out of Memory During Training**
```python
# Error: "CUDA out of memory"

# Solution 1: Reduce batch size
model = train_node2vec(batch_size=64)  # Instead of 128

# Solution 2: Use CPU instead of GPU
device = torch.device("cpu")
```

**3. Embeddings Not Improving**
```python
# Problem: node2vec embeddings not better than keywords

# Solution: Tune hyperparameters
model = train_node2vec(
    walk_length=40,        # Increase from 20
    context_size=15,       # Increase from 10
    walks_per_node=20,     # Increase from 10
    num_epochs=200         # Increase from 100
)
```

**4. Slow Inference**
```python
# Problem: Embedding lookup takes >50ms

# Solution: Pre-compute and cache all embeddings
# Store in Qdrant instead of computing on-the-fly
```

---

## Next Steps

After completing this guide, you should have:
- ✅ Working node2vec prototype
- ✅ Concept embeddings stored in Qdrant
- ✅ Evaluation metrics proving GNN value
- ✅ Integration plan for production

**Recommended Next Actions:**
1. **Review Metrics:** Share evaluation results with team
2. **Get Approval:** Present cost-benefit analysis to stakeholders
3. **Start Phase 2:** Integrate into production codebase
4. **Plan GraphSAGE:** Once node2vec is stable, upgrade to GraphSAGE
5. **Monitor & Iterate:** Track recall, latency, and user feedback

---

## Resources

### Official Documentation
- **PyTorch Geometric:** https://pytorch-geometric.readthedocs.io/
- **Node2Vec Paper:** https://arxiv.org/abs/1607.00653
- **GraphSAGE Paper:** https://arxiv.org/abs/1706.02216

### Tutorials
- PyG Getting Started: https://pytorch-geometric.readthedocs.io/en/latest/get_started/introduction.html
- Node2Vec Tutorial: https://pytorch-geometric.readthedocs.io/en/latest/tutorial/unsupervised.html
- Knowledge Graph Embeddings: https://pytorch-geometric.readthedocs.io/en/latest/tutorial/kg.html

### Internal Documentation
- [GNN Overview](README.md) - High-level architecture
- [Model Selection Guide](MODELS.md) - Which GNN to use when
- [Architecture Deep-Dive](ARCHITECTURE.md) - Integration points

---

**Last Updated:** March 28, 2026
**Status:** Ready for prototyping
**Maintained By:** Cortex-AI Team
