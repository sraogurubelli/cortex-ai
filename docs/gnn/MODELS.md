# GNN Model Selection Guide

**Comprehensive guide to choosing the right GNN model for each use case**

---

## Table of Contents

1. [Model Comparison Matrix](#model-comparison-matrix)
2. [Model Deep-Dives](#model-deep-dives)
3. [Technology Stack](#technology-stack)
4. [Training Considerations](#training-considerations)
5. [Model Serving Patterns](#model-serving-patterns)
6. [Use Case → Model Mapping](#use-case--model-mapping)

---

## Model Comparison Matrix

| Model | Use Case | Complexity | Training Time | Inference Speed | Works With |
|-------|----------|------------|---------------|-----------------|------------|
| **node2vec** | Node embeddings (simple) | Low | Fast (minutes) | Very Fast (1ms) | NetworkX |
| **GraphSAGE** | Node embeddings (inductive) | Medium | Medium (1-2 hrs) | Fast (5-10ms) | PyTorch Geometric |
| **GCN** | Node classification | Low | Fast (30 min) | Fast (5-10ms) | PyTorch Geometric |
| **GAT** | Attention-based ranking | Medium-High | Medium (2-4 hrs) | Medium (10-20ms) | PyTorch Geometric |
| **TransE** | Link prediction | Low | Fast (1 hr) | Fast (2-5ms) | PyTorch Geometric |
| **RotatE** | Asymmetric link prediction | Medium | Medium (2-3 hrs) | Fast (2-5ms) | PyTorch Geometric |
| **ComplEx** | Complex link prediction | Medium | Medium (2-3 hrs) | Fast (2-5ms) | PyTorch Geometric |
| **Louvain** | Community detection | N/A | Very Fast (seconds) | Very Fast (<1ms) | python-louvain |

---

## Model Deep-Dives

### 1. GraphSAGE (Graph Sample and Aggregate)

**Best For:** Generating graph-aware embeddings for concepts

**How It Works:**
- Samples a fixed-size neighborhood for each node
- Aggregates neighbor features using mean/max/LSTM pooling
- Learns to combine node's own features with neighbor aggregations
- **Inductive:** Can generate embeddings for new nodes without retraining

**Architecture:**
```python
class GraphSAGE(torch.nn.Module):
    def __init__(self, in_features, hidden_dim, out_dim):
        super().__init__()
        self.conv1 = SAGEConv(in_features, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, out_dim)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.5, training=self.training)
        x = self.conv2(x, edge_index)
        return x
```

**Training:**
```python
from torch_geometric.nn import GraphSAGE
from torch_geometric.data import Data

# Prepare data
x = initial_embeddings  # OpenAI embeddings (1536D)
edge_index = concept_relationships  # (2, num_edges)

# Create model
model = GraphSAGE(in_channels=1536, hidden_channels=128, num_layers=2, out_channels=256)

# Training loop
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
for epoch in range(100):
    model.train()
    optimizer.zero_grad()
    out = model(x, edge_index)
    loss = F.mse_loss(out, target_embeddings)  # Or contrastive loss
    loss.backward()
    optimizer.step()
```

**Pros:**
- ✅ Inductive learning (handles new nodes)
- ✅ Scalable (samples neighborhoods, doesn't need full graph)
- ✅ Well-tested on knowledge graphs

**Cons:**
- ❌ Requires neighbor sampling (complexity)
- ❌ Needs initial features (we use OpenAI embeddings)

**Paper:** [Inductive Representation Learning on Large Graphs](https://arxiv.org/abs/1706.02216) (Hamilton et al., 2017)

---

### 2. node2vec (Random Walk Embeddings)

**Best For:** Quick prototyping of node embeddings

**How It Works:**
- Performs random walks on the graph (like word2vec on text)
- Learns embeddings by predicting co-occurrence of nodes in walks
- No neural network (just embedding lookup + skip-gram objective)
- **Much simpler than GraphSAGE** but not inductive

**Architecture:**
```python
from node2vec import Node2Vec
import networkx as nx

# Build NetworkX graph
G = nx.Graph()
for concept in concepts:
    G.add_node(concept.id)
for rel in relationships:
    G.add_edge(rel['source_id'], rel['target_id'], weight=rel['strength'])

# Train node2vec
node2vec = Node2Vec(
    G,
    dimensions=256,      # Embedding size
    walk_length=30,      # Length of random walks
    num_walks=200,       # Walks per node
    workers=4
)
model = node2vec.fit(window=10, min_count=1, batch_words=4)

# Get embeddings
embeddings = {node: model.wv[node] for node in G.nodes()}
```

**Pros:**
- ✅ Very simple to implement (5 lines of code)
- ✅ Fast training (minutes for 10k nodes)
- ✅ No need for initial features

**Cons:**
- ❌ Not inductive (must retrain for new nodes)
- ❌ Doesn't use node features (only graph structure)
- ❌ Outdated (GraphSAGE is strictly better for inductive tasks)

**Paper:** [node2vec: Scalable Feature Learning for Networks](https://arxiv.org/abs/1607.00653) (Grover & Leskovec, 2016)

**Recommendation:** Use for quick PoC, then upgrade to GraphSAGE for production.

---

### 3. GCN (Graph Convolutional Network)

**Best For:** Node classification (refining concept categories)

**How It Works:**
- Aggregates neighbor features using normalized adjacency matrix
- Multiple layers propagate information across graph
- Simplest graph neural network architecture

**Architecture:**
```python
from torch_geometric.nn import GCNConv

class GCN(torch.nn.Module):
    def __init__(self, in_features, hidden_dim, num_classes):
        super().__init__()
        self.conv1 = GCNConv(in_features, hidden_dim)
        self.conv2 = GCNConv(hidden_dim, num_classes)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.5, training=self.training)
        x = self.conv2(x, edge_index)
        return F.log_softmax(x, dim=1)

# Training for concept categorization
model = GCN(in_features=1536, hidden_dim=128, num_classes=5)  # 5 categories
criterion = torch.nn.NLLLoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

for epoch in range(200):
    model.train()
    optimizer.zero_grad()
    out = model(x, edge_index)
    loss = criterion(out[train_mask], labels[train_mask])
    loss.backward()
    optimizer.step()

# Predict categories
model.eval()
predictions = model(x, edge_index).argmax(dim=1)
```

**Pros:**
- ✅ Simple and interpretable
- ✅ Proven effective for node classification
- ✅ Fast training and inference

**Cons:**
- ❌ Transductive (requires full graph during inference)
- ❌ Oversimplified aggregation (mean pooling only)

**Paper:** [Semi-Supervised Classification with Graph Convolutional Networks](https://arxiv.org/abs/1609.02907) (Kipf & Welling, 2017)

**Use Case:** Refine LLM-extracted concept categories using graph context.

---

### 4. GAT (Graph Attention Networks)

**Best For:** Learning relationship importance for ranking

**How It Works:**
- Attention mechanism learns to focus on important neighbors
- Each neighbor gets a learned attention weight
- More flexible than GCN (adaptive aggregation vs fixed mean)

**Architecture:**
```python
from torch_geometric.nn import GATConv

class GAT(torch.nn.Module):
    def __init__(self, in_features, hidden_dim, out_dim, heads=4):
        super().__init__()
        self.conv1 = GATConv(in_features, hidden_dim, heads=heads)
        self.conv2 = GATConv(hidden_dim * heads, out_dim, heads=1)

    def forward(self, x, edge_index, return_attention_weights=False):
        x = self.conv1(x, edge_index)
        x = F.elu(x)
        x = F.dropout(x, p=0.6, training=self.training)

        if return_attention_weights:
            x, (edge_index, attention_weights) = self.conv2(
                x, edge_index, return_attention_weights=True
            )
            return x, attention_weights
        else:
            x = self.conv2(x, edge_index)
            return x

# Training
model = GAT(in_features=256, hidden_dim=128, out_dim=256, heads=4)
optimizer = torch.optim.Adam(model.parameters(), lr=0.005)

for epoch in range(300):
    model.train()
    optimizer.zero_grad()
    out = model(x, edge_index)
    loss = contrastive_loss(out)  # Or link prediction loss
    loss.backward()
    optimizer.step()

# Inference with attention weights
model.eval()
embeddings, attention_weights = model(
    x, edge_index, return_attention_weights=True
)
```

**Pros:**
- ✅ Learns adaptive attention (which neighbors matter)
- ✅ More expressive than GCN
- ✅ Can return attention weights for interpretability

**Cons:**
- ❌ Slower training than GCN (attention computation overhead)
- ❌ More hyperparameters (number of heads, dropout rates)

**Paper:** [Graph Attention Networks](https://arxiv.org/abs/1710.10903) (Veličković et al., 2018)

**Use Case:** Weight graph traversal neighbors by learned attention for better ranking.

---

### 5. TransE (Translating Embeddings)

**Best For:** Link prediction on knowledge graphs

**How It Works:**
- Models relationships as translations in embedding space
- For triple (head, relation, tail): `embedding(head) + embedding(relation) ≈ embedding(tail)`
- Score function: `score = -||h + r - t||` (lower is better)

**Architecture:**
```python
from torch_geometric.nn.kge import TransE

# Create model
model = TransE(
    num_nodes=len(concepts),
    num_relations=1,  # Single relation type: RELATES_TO
    embedding_dim=256
)

# Training data: triples (head_idx, relation_type, tail_idx)
triples = torch.tensor([
    [concept_a_idx, 0, concept_b_idx],  # (GraphRAG, RELATES_TO, knowledge graph)
    [concept_c_idx, 0, concept_d_idx],  # (Python, RELATES_TO, data science)
    # ...
])

# Training loop
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
for epoch in range(100):
    model.train()
    optimizer.zero_grad()

    # Positive samples
    pos_scores = model(triples)

    # Negative samples (corrupt tail)
    neg_triples = triples.clone()
    neg_triples[:, 2] = torch.randint(0, len(concepts), (len(triples),))
    neg_scores = model(neg_triples)

    # Margin ranking loss
    loss = F.margin_ranking_loss(
        pos_scores, neg_scores,
        target=torch.ones(len(triples)),
        margin=1.0
    )
    loss.backward()
    optimizer.step()

# Predict link
with torch.no_grad():
    score = model(torch.tensor([[head_idx, 0, tail_idx]]))
    # score < 0.5 → likely relationship
```

**Pros:**
- ✅ Simple and interpretable
- ✅ Works well on knowledge graphs
- ✅ Fast training and inference

**Cons:**
- ❌ Cannot model symmetric relationships well (assumes translation)
- ❌ Struggles with 1-to-N and N-to-1 relations

**Paper:** [Translating Embeddings for Modeling Multi-relational Data](https://papers.nips.cc/paper/2013/hash/1cecc7a77928ca8133fa24680a88d2f9-Abstract.html) (Bordes et al., 2013)

**Use Case:** Predict missing RELATES_TO relationships between concepts.

---

### 6. RotatE (Rotation-based Embeddings)

**Best For:** Asymmetric link prediction (better than TransE for complex relationships)

**How It Works:**
- Models relationships as rotations in complex vector space
- For triple (h, r, t): `h ◦ r ≈ t` where `◦` is element-wise complex multiplication
- Handles symmetric, antisymmetric, inverse, and compositional patterns

**Architecture:**
```python
from torch_geometric.nn.kge import RotatE

model = RotatE(
    num_nodes=len(concepts),
    num_relations=1,
    embedding_dim=128  # Must be even (complex embeddings)
)

# Training similar to TransE but with phase-based scoring
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
for epoch in range(100):
    # ... same as TransE ...
    pass

# Inference
score = model.predict_link(head_idx, relation=0, tail_idx)
```

**Pros:**
- ✅ Better than TransE for complex relationship patterns
- ✅ Handles symmetric and antisymmetric relations
- ✅ Can model inverse relationships

**Cons:**
- ❌ More complex than TransE
- ❌ Slightly slower inference (complex multiplication)

**Paper:** [RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space](https://arxiv.org/abs/1902.10197) (Sun et al., 2019)

**Use Case:** Link prediction when relationship types have complex patterns (e.g., inverse, composition).

---

### 7. Louvain (Community Detection)

**Best For:** Clustering concepts into topics

**How It Works:**
- Modularity optimization algorithm (not a neural network)
- Iteratively merges nodes into communities to maximize modularity
- Very fast (linear time)

**Implementation:**
```python
import community as community_louvain
import networkx as nx

# Build graph
G = nx.Graph()
for rel in relationships:
    G.add_edge(rel['source_id'], rel['target_id'], weight=rel['strength'])

# Detect communities
partition = community_louvain.best_partition(G)

# Group by community
communities = {}
for node, community_id in partition.items():
    if community_id not in communities:
        communities[community_id] = []
    communities[community_id].append(node)

# Modularity score (higher is better)
modularity = community_louvain.modularity(partition, G)
print(f"Modularity: {modularity:.3f}")
```

**Pros:**
- ✅ Very fast (seconds for 100k nodes)
- ✅ No training required
- ✅ Deterministic and interpretable

**Cons:**
- ❌ Resolution limit (may miss small communities)
- ❌ Not learning-based (doesn't leverage node features)

**Paper:** [Fast unfolding of communities in large networks](https://arxiv.org/abs/0803.0476) (Blondel et al., 2008)

**Alternative:** Label Propagation (even faster, but less accurate)

**Use Case:** Auto-generate topic clusters for large concept graphs (10k+ nodes).

---

## Technology Stack

### Recommended: PyTorch + PyTorch Geometric

**Why PyTorch Geometric (PyG)?**
1. **Rich Model Zoo**: GraphSAGE, GCN, GAT, TransE, RotatE all built-in
2. **Production-Ready**: Used by companies like Twitter, Alibaba, Pinterest
3. **GPU Acceleration**: Automatic CUDA support (but CPU inference works fine)
4. **Inductive Learning**: Supports dynamic graphs (critical for growing knowledge graphs)
5. **Excellent Documentation**: [pytorch-geometric.readthedocs.io](https://pytorch-geometric.readthedocs.io/)

**Installation:**
```bash
# Install PyTorch first
pip install torch>=2.1.0

# Install PyTorch Geometric
pip install torch-geometric>=2.4.0

# Install supporting libraries
pip install torch-scatter torch-sparse -f https://data.pyg.org/whl/torch-2.1.0+cpu.html

# For node2vec and community detection
pip install node2vec python-louvain networkx
```

### Alternative: DGL (Deep Graph Library)

**Pros:**
- Multiple backend support (PyTorch, TensorFlow, MXNet)
- Good performance on very large graphs (100M+ nodes)
- Clean API design

**Cons:**
- Steeper learning curve
- Smaller community than PyG
- Less documentation

**Recommendation:** Start with PyTorch Geometric. Only consider DGL if you need multi-framework support or have 100M+ node graphs.

---

## Training Considerations

### GPU vs CPU

| Model | GPU Required? | CPU Training Time (10k nodes) | GPU Training Time |
|-------|---------------|--------------------------------|-------------------|
| node2vec | No | 5 minutes | 2 minutes |
| GraphSAGE | Recommended | 2-4 hours | 30-60 minutes |
| GCN | Recommended | 1-2 hours | 15-30 minutes |
| GAT | Recommended | 3-6 hours | 45-90 minutes |
| TransE | No | 1 hour | 15 minutes |
| RotatE | No | 2 hours | 30 minutes |

**Recommendation:**
- **Training**: Use GPU for GraphSAGE, GAT (AWS p3.2xlarge ~$3/hour)
- **Inference**: CPU is sufficient for all models (<20ms per query)

### Training Data Requirements

| Model | Training Data | Data Source | Notes |
|-------|---------------|-------------|-------|
| GraphSAGE | Node features + graph structure | OpenAI embeddings + Neo4j | Unsupervised (contrastive loss) |
| GCN | Node features + labels | LLM-extracted categories | Supervised (classification) |
| GAT | Node features + graph structure | OpenAI embeddings + Neo4j | Unsupervised or supervised |
| TransE | Triple data (h, r, t) | Neo4j relationships | Unsupervised (margin ranking) |
| RotatE | Triple data (h, r, t) | Neo4j relationships | Unsupervised (margin ranking) |
| node2vec | Graph structure only | Neo4j relationships | Unsupervised (skip-gram) |
| Louvain | Graph structure only | Neo4j relationships | No training |

**Key Insight:** Most GNN models can be trained **unsupervised** using only the graph structure. This is critical because we don't have labeled data for most concepts.

### Hyperparameters

**GraphSAGE:**
```python
{
    "in_channels": 1536,        # OpenAI embedding dim (fixed)
    "hidden_channels": 128,     # Try: [64, 128, 256]
    "num_layers": 2,            # Try: [2, 3] (more = slower)
    "out_channels": 256,        # Concept embedding dim (fixed)
    "dropout": 0.5,             # Try: [0.3, 0.5, 0.7]
    "learning_rate": 0.01,      # Try: [0.001, 0.01, 0.1]
    "batch_size": 512,          # Depends on GPU memory
    "epochs": 100               # Early stopping recommended
}
```

**TransE:**
```python
{
    "embedding_dim": 256,       # Same as concept embeddings
    "margin": 1.0,              # Margin for ranking loss (fixed)
    "learning_rate": 0.01,      # Try: [0.001, 0.01]
    "negative_samples": 10,     # Try: [5, 10, 20]
    "epochs": 100
}
```

**GAT:**
```python
{
    "in_channels": 256,         # Concept embedding dim
    "hidden_channels": 128,     # Try: [64, 128]
    "out_channels": 256,        # Output dim
    "heads": 4,                 # Try: [2, 4, 8]
    "dropout": 0.6,             # Higher than GraphSAGE
    "learning_rate": 0.005,     # Lower than GraphSAGE
    "epochs": 300               # Slower convergence
}
```

---

## Model Serving Patterns

### Pattern 1: Pre-computed Embeddings (Recommended)

**Strategy:** Train model once, generate all concept embeddings, store in Qdrant

**Flow:**
```
Training (offline):
    Train GraphSAGE on current graph → Save model checkpoint

Embedding Generation (periodic):
    Load model → Generate embeddings for all concepts → Store in Qdrant

Query Time (online):
    Query embedding → Search Qdrant → No GNN inference needed
```

**Pros:**
- ✅ Fast inference (vector search only, no GNN computation)
- ✅ Simple deployment (no model serving infrastructure)
- ✅ Consistent performance (no model latency variance)

**Cons:**
- ❌ Stale embeddings (need periodic regeneration)
- ❌ Not real-time (new concepts don't have embeddings immediately)

**Update Frequency:** Daily or weekly batch job

---

### Pattern 2: On-Demand Inference

**Strategy:** Run GNN model at query time for new concepts

**Flow:**
```
Query Time:
    New concept → Load neighbors → GraphSAGE inference → Generate embedding → Cache
```

**Pros:**
- ✅ Real-time embeddings for new concepts
- ✅ Always up-to-date

**Cons:**
- ❌ Slower inference (10-20ms overhead)
- ❌ Requires model serving infrastructure

**Use Case:** When concept graph changes frequently (100+ new concepts/day)

---

### Pattern 3: Hybrid Approach (Best of Both)

**Strategy:** Pre-compute for existing concepts, on-demand for new concepts

**Flow:**
```
Existing Concepts:
    Lookup pre-computed embedding from Qdrant

New Concepts:
    GraphSAGE inference → Generate embedding → Cache → Store in Qdrant
```

**Pros:**
- ✅ Fast for existing concepts (vector lookup)
- ✅ Real-time for new concepts
- ✅ Eventually consistent (periodic batch updates)

**Cons:**
- ❌ More complex implementation

**Recommendation:** Use this for production.

---

### Model Versioning

```python
# Store model metadata with embeddings
{
    "concept_id": "concept-123",
    "embedding": [...],
    "metadata": {
        "model": "GraphSAGE",
        "version": "v1.2",
        "trained_at": "2026-03-28T10:00:00Z",
        "embedding_dim": 256
    }
}
```

**Benefits:**
- Track which embeddings need regeneration after model updates
- A/B test new model versions
- Rollback to previous version if needed

---

## Use Case → Model Mapping

### Decision Tree

```
What are you trying to do?

├─ Generate concept embeddings
│  ├─ Quick prototype? → node2vec
│  └─ Production? → GraphSAGE
│
├─ Predict missing relationships
│  ├─ Simple relationships (symmetric)? → TransE
│  └─ Complex relationships (asymmetric, inverse)? → RotatE
│
├─ Refine concept categories
│  └─ GCN (node classification)
│
├─ Learn relationship importance
│  └─ GAT (attention-based ranking)
│
└─ Cluster concepts into topics
   └─ Louvain (community detection)
```

### Recommended Starting Stack

**Phase 1: Proof of Concept (Week 1-2)**
```python
models = {
    "concept_embeddings": "node2vec",        # Simplest, fastest to prototype
    "link_prediction": None,                  # Skip for PoC
    "community_detection": "Louvain"         # No training required
}
```

**Phase 2: Production (Week 3-6)**
```python
models = {
    "concept_embeddings": "GraphSAGE",       # Inductive, production-ready
    "link_prediction": "TransE",             # Simple, interpretable
    "community_detection": "Louvain"         # Already works well
}
```

**Phase 3: Advanced (Month 3+)**
```python
models = {
    "concept_embeddings": "GraphSAGE",       # Keep
    "link_prediction": "RotatE",             # Upgrade for complex patterns
    "attention_ranking": "GAT",              # Add attention weights
    "community_detection": "Louvain"         # Keep
}
```

---

## Research Papers & Resources

### Must-Read Papers

1. **GraphSAGE** (2017)
   - [Inductive Representation Learning on Large Graphs](https://arxiv.org/abs/1706.02216)
   - Hamilton, Ying, Leskovec
   - 2,000+ citations

2. **GAT** (2018)
   - [Graph Attention Networks](https://arxiv.org/abs/1710.10903)
   - Veličković et al.
   - 8,000+ citations

3. **TransE** (2013)
   - [Translating Embeddings for Modeling Multi-relational Data](https://papers.nips.cc/paper/2013/hash/1cecc7a77928ca8133fa24680a88d2f9-Abstract.html)
   - Bordes et al.
   - 6,000+ citations

4. **RotatE** (2019)
   - [RotatE: Knowledge Graph Embedding by Relational Rotation in Complex Space](https://arxiv.org/abs/1902.10197)
   - Sun et al.
   - 1,500+ citations

### Tutorials & Guides

- **PyTorch Geometric Tutorial**: https://pytorch-geometric.readthedocs.io/en/latest/get_started/introduction.html
- **Stanford CS224W (Graph ML)**: https://web.stanford.edu/class/cs224w/
- **DGL Tutorial**: https://docs.dgl.ai/tutorials/blitz/index.html

---

**Next:** See [GETTING_STARTED.md](GETTING_STARTED.md) for hands-on prototyping guide.

---

**Last Updated:** March 28, 2026
**Maintained By:** Cortex-AI Team
