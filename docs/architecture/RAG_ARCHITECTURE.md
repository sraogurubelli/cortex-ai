# RAG Architecture Documentation

**Visual guide to Regular RAG vs GraphRAG in Cortex-AI**

---

## Table of Contents

1. [Document Ingestion Flow](#1-document-ingestion-flow)
2. [Regular RAG Architecture](#2-regular-rag-architecture)
3. [GraphRAG Architecture](#3-graphrag-architecture)
4. [Query Embedding Reuse](#4-query-embedding-reuse)
5. [Concept Embeddings: Pre-compute vs Query-time](#5-concept-embeddings-pre-compute-vs-query-time)
6. [Storage Layer Architecture](#6-storage-layer-architecture)
7. [Current vs Proposed: Semantic Concept Search](#7-current-vs-proposed-semantic-concept-search)

---

## 1. Document Ingestion Flow

**Purpose:** How documents are processed and stored in the system

```
┌──────────────────────────────────────────────────────────────────────┐
│                    DOCUMENT INGESTION FLOW                            │
└──────────────────────────────────────────────────────────────────────┘

User Uploads Document
     │
     │ "Python_tutorial.pdf"
     │ Content: "Python is a high-level programming language..."
     │
     ▼
┌────────────────────────────┐
│ 1. Text Extraction         │  Extract text from PDF/DOCX/TXT
└────────┬───────────────────┘
         │
         │ Raw text content
         │
         ▼
┌────────────────────────────┐
│ 2. Text Chunking           │  Split into chunks (512 tokens)
│                            │  With overlap (50 tokens)
└────────┬───────────────────┘
         │
         │ Chunks: ["Python is...", "Python syntax...", ...]
         │
         ├─────────────────────┬─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ 3a. Embed      │    │ 3b. Extract    │    │ 3c. Store      │
│    Chunks      │    │    Entities    │    │    Document    │
│                │    │                │    │                │
│ OpenAI API     │    │ LLM (GPT-4o)   │    │ Neo4j          │
│ ↓              │    │ ↓              │    │ ↓              │
│ Vectors        │    │ Concepts +     │    │ Document node  │
│ (1536D each)   │    │ Relationships  │    │                │
└────────┬───────┘    └────────┬───────┘    └────────┬───────┘
         │                     │                     │
         │                     │                     │
         ▼                     ▼                     ▼
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ 4a. Store in   │    │ 4b. Store      │    │ 4c. Create     │
│    Qdrant      │    │    Concepts    │    │    MENTIONS    │
│ "documents"    │    │                │    │    edges       │
│                │    │ ┌────────────┐ │    │                │
│ Each chunk:    │    │ │ Neo4j      │ │    │ Document       │
│ - id           │    │ │ Concept    │ │    │    ↓           │
│ - vector       │    │ │ nodes      │ │    │ MENTIONS       │
│ - content      │    │ └──────┬─────┘ │    │    ↓           │
│ - metadata     │    │        │       │    │ Concepts       │
└────────────────┘    │        ▼       │    └────────────────┘
                      │ ┌────────────┐ │
                      │ │ Embed      │ │ ← NEW (Proposed)
                      │ │ Concepts   │ │
                      │ └──────┬─────┘ │
                      │        │       │
                      │        ▼       │
                      │ ┌────────────┐ │
                      │ │ Qdrant     │ │
                      │ │ "concepts" │ │
                      │ │            │ │
                      │ │ - name     │ │
                      │ │ - vector   │ │
                      │ │ - category │ │
                      │ └────────────┘ │
                      └────────────────┘
```

### Detailed Steps

**Step 1: Text Extraction**
- Input: PDF/DOCX/TXT file
- Process: Extract raw text using appropriate parser
- Output: Plain text string

**Step 2: Text Chunking**
- Input: Raw text (potentially thousands of tokens)
- Process: Split into overlapping chunks (512 tokens, 50 token overlap)
- Output: List of text chunks
- Why: Embedding models have token limits, overlap preserves context

**Step 3: Parallel Processing (3 paths)**

**Path 3a - Embed Chunks:**
- For each chunk: Call OpenAI embedding API
- Generate: 1536D vector per chunk
- Purpose: Enable semantic similarity search

**Path 3b - Extract Entities:**
- Use LLM (GPT-4o-mini) to extract concepts and relationships
- Prompt: "Extract key concepts and how they relate"
- Returns: Structured JSON with concepts + relationships
- Example: `{"concepts": [{"name": "Python", "category": "language"}], "relationships": [...]}`

**Path 3c - Store Document:**
- Create Neo4j Document node
- Store metadata: id, tenant_id, created_at
- Full content stored for reference

**Step 4: Storage (3 parallel operations)**

**4a - Store Chunk Vectors:**
- Collection: Qdrant "documents"
- Each point: vector + payload (content, doc_id, chunk_index)
- Enables: Fast semantic search at query time

**4b - Store Concepts:**
- Create Neo4j Concept nodes (deduplicated by name)
- **Current:** Store name and category only
- **Proposed:** Also embed concept name → store in Qdrant "concepts"
- Enables: Graph traversal + semantic concept search

**4c - Create Relationships:**
- Neo4j edges:
  - `(Document)-[MENTIONS]->(Concept)` - Which concepts appear in doc
  - `(Concept)-[RELATES_TO]-(Concept)` - How concepts relate
- Properties: count, confidence, strength, context

### Storage After Ingestion

```
After ingesting "Python_tutorial.pdf":

┌──────────────────────────────────────────────────────────────────┐
│  Qdrant "documents" Collection                                   │
├──────────────────────────────────────────────────────────────────┤
│  • chunk-1: [vector: 1536D] "Python is a high-level..."         │
│  • chunk-2: [vector: 1536D] "Python syntax is clean..."         │
│  • chunk-3: [vector: 1536D] "Python is used for web..."         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Neo4j Graph Database                                            │
├──────────────────────────────────────────────────────────────────┤
│  (:Document {id: "doc-123", content: "full text..."})           │
│       │                                                           │
│       ├─[MENTIONS {count: 5, confidence: 0.9}]→                 │
│       │         (:Concept {name: "Python"})                      │
│       │                                                           │
│       ├─[MENTIONS {count: 3, confidence: 0.8}]→                 │
│       │         (:Concept {name: "programming"})                 │
│       │                                                           │
│       └─[MENTIONS {count: 2, confidence: 0.7}]→                 │
│                 (:Concept {name: "web development"})             │
│                                                                   │
│  (:Concept {name: "Python"})                                     │
│       ├─[RELATES_TO {strength: 0.9}]→                           │
│       │         (:Concept {name: "programming"})                 │
│       │                                                           │
│       ├─[RELATES_TO {strength: 0.8}]→                           │
│       │         (:Concept {name: "web development"})             │
│       │                                                           │
│       └─[RELATES_TO {strength: 0.7}]→                           │
│                 (:Concept {name: "data science"})                │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Qdrant "concepts" Collection (Proposed)                         │
├──────────────────────────────────────────────────────────────────┤
│  • Python: [vector: 1536D] category="programming_language"      │
│  • programming: [vector: 1536D] category="domain"               │
│  • web development: [vector: 1536D] category="domain"           │
└──────────────────────────────────────────────────────────────────┘
```

### Key Insights

**Parallel Processing:**
- Embedding and entity extraction happen simultaneously
- Efficient use of API calls (batch where possible)
- Independent operations don't block each other

**Chunking Strategy:**
- 512 tokens: Optimal for embedding models
- 50 token overlap: Preserves context across boundaries
- Prevents information loss at chunk boundaries

**The Missing Piece (Current System):**
- ✅ Document chunks ARE embedded → Qdrant "documents"
- ✅ Concepts ARE extracted → Neo4j graph
- ❌ Concepts are NOT embedded → No Qdrant "concepts" collection
- ⚠️ This is what Phase 0 (semantic concept search) would add

---

## 2. Regular RAG Architecture (Query Flow)

**Purpose:** Direct semantic search for document retrieval at query time

```
┌──────────────────────────────────────────────────────────┐
│                   REGULAR RAG FLOW                        │
└──────────────────────────────────────────────────────────┘

User Query (text)
     │
     │ "How does Python work?"
     │
     ▼
┌────────────────┐
│ Embedding      │  OpenAI API
│ Service        │  text-embedding-3-small
└────────┬───────┘
         │
         │ [0.123, -0.456, ..., 0.789]  (1536D vector)
         │
         ▼
┌────────────────────────────────┐
│   Qdrant Vector Store          │
│                                │
│   Collection: "documents"      │
│   ┌─────────────────────────┐ │
│   │ Doc 1: "Python is..."   │ │ ← Similarity: 0.95
│   │ Doc 2: "Java is..."     │ │ ← Similarity: 0.72
│   │ Doc 3: "Python syntax"  │ │ ← Similarity: 0.89
│   │ Doc 4: "ML models..."   │ │ ← Similarity: 0.45
│   └─────────────────────────┘ │
└────────┬───────────────────────┘
         │
         │ Cosine similarity comparison
         │
         ▼
┌────────────────┐
│ Top K Results  │  Documents ranked by similarity
│                │
│ 1. Doc 1 (0.95)│
│ 2. Doc 3 (0.89)│
│ 3. Doc 2 (0.72)│
└────────────────┘
```

**Storage Requirements:**
- ✅ Qdrant: 1 collection (`documents`)
- ❌ Neo4j: Not needed
- ❌ Concept embeddings: Not needed

**Use Case:**
- Simple content retrieval
- Direct semantic matching
- No relationship navigation needed

---

## 3. GraphRAG Architecture (Query Flow)

**Purpose:** Hybrid search combining semantic similarity + graph relationships at query time

```
┌──────────────────────────────────────────────────────────────────────┐
│                        GRAPHRAG FLOW                                  │
└──────────────────────────────────────────────────────────────────────┘

User Query (text)
     │
     │ "How does Python work?"
     │
     ▼
┌────────────────┐
│ Embedding      │  Generate query embedding ONCE
│ Service        │
└────────┬───────┘
         │
         │ [0.123, -0.456, ..., 0.789]  (1536D vector)
         │
         ├─────────────────────┬─────────────────────┐
         │                     │                     │
         │ Path 1: Vector      │ Path 2: Graph       │
         │                     │                     │
         ▼                     ▼                     ▼
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ Qdrant         │    │ Qdrant         │    │ Neo4j          │
│ "documents"    │    │ "concepts"     │    │ Graph          │
│                │    │                │    │                │
│ Doc 1: 0.95    │    │ Python: 0.95   │───▶│ Traverse       │
│ Doc 3: 0.89    │    │ Programming:   │    │ relationships  │
│ Doc 2: 0.72    │    │   0.87         │    │                │
└────────┬───────┘    └────────┬───────┘    │ Python         │
         │                     │             │   ↓            │
         │                     └────────────▶│ RELATES_TO     │
         │                                   │   ↓            │
         │                                   │ - pandas       │
         │                                   │ - NumPy        │
         │                                   │ - Django       │
         │                                   └────────┬───────┘
         │                                            │
         │                                            ▼
         │                                   ┌────────────────┐
         │                                   │ Find Documents │
         │                                   │ mentioning:    │
         │                                   │ - pandas       │
         │                                   │ - NumPy        │
         │                                   │ - Django       │
         │                                   └────────┬───────┘
         │                                            │
         │                Graph Results               │
         └──────────────────┬─────────────────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  RRF Fusion     │  Reciprocal Rank Fusion
                   │                 │  Weights: 0.7 vector, 0.3 graph
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Final Results  │  Combined ranking
                   │                 │
                   │ Documents about │
                   │ Python + related│
                   │ libraries       │
                   └─────────────────┘
```

**Storage Requirements:**
- ✅ Qdrant: 2 collections (`documents` + `concepts`)
- ✅ Neo4j: Graph structure (Concept nodes + RELATES_TO edges)
- ✅ Concept embeddings: Pre-computed for semantic search

**Use Case:**
- Relationship-aware retrieval
- Multi-hop reasoning
- Find related concepts not explicitly mentioned in query

---

## 4. Query Embedding Reuse

**Key Insight:** Query is embedded ONCE, then the same embedding is used for multiple searches

```
┌────────────────────────────────────────────────────────────┐
│          QUERY EMBEDDING REUSE PATTERN                     │
└────────────────────────────────────────────────────────────┘

Step 1: Embed Query (ONCE)
┌──────────────────────────┐
│ Query: "Python ML"       │
│         ↓                │
│ Embedding Service        │
│         ↓                │
│ [0.1, 0.2, 0.3, ...]    │  1536D vector
└──────────┬───────────────┘
           │
           │ Computed ONCE, reused below
           │
     ┌─────┴─────┐
     │           │
     │           │
     ▼           ▼
┌─────────┐ ┌─────────┐
│ Search  │ │ Search  │
│ Qdrant  │ │ Qdrant  │
│ "docs"  │ │ "concpt"│
│         │ │         │
│ Compare │ │ Compare │
│ query   │ │ query   │
│ to doc  │ │ to cncpt│
│ embedds │ │ embedds │
└─────────┘ └─────────┘

Both searches use the SAME query embedding
(Efficient - no duplicate embedding calls)
```

**Efficiency:**
- ❌ **BAD:** Embed query twice (once per collection)
- ✅ **GOOD:** Embed query once, reuse for both searches

**Implementation:**
```
1. query_embedding = await embed(query)          ← ONCE
2. docs = await search("documents", query_embedding)   ← Reuse
3. concepts = await search("concepts", query_embedding) ← Reuse
```

---

## 5. Concept Embeddings: Pre-compute vs Query-time

**Two-phase process:** Index-time pre-computation + Query-time comparison

```
┌────────────────────────────────────────────────────────────┐
│                   INDEXING TIME                            │
│                (Pre-compute concept embeddings)            │
└────────────────────────────────────────────────────────────┘

Concept Creation
     │
     │ name: "Python"
     │ category: "programming_language"
     │
     ▼
┌────────────────┐
│ Embedding      │  embed("Python")
│ Service        │
└────────┬───────┘
         │
         │ [0.11, 0.21, 0.31, ...]  (1536D)
         │
         ▼
┌────────────────────────────────┐
│ Qdrant "concepts" collection   │
│                                │
│ Store:                         │
│ - id: concept-uuid-123         │
│ - vector: [0.11, 0.21, ...]   │
│ - payload:                     │
│     name: "Python"             │
│     category: "prog_lang"      │
│     tenant_id: "demo"          │
└────────────────────────────────┘

This happens ONCE per concept
(Pre-computed and stored)


┌────────────────────────────────────────────────────────────┐
│                    QUERY TIME                              │
│              (Compare query to concepts)                   │
└────────────────────────────────────────────────────────────┘

User Query
     │
     │ "How does Python work?"
     │
     ▼
┌────────────────┐
│ Embedding      │  embed("How does Python work?")
│ Service        │
└────────┬───────┘
         │
         │ [0.12, 0.19, 0.33, ...]  (1536D)
         │
         ▼
┌────────────────────────────────┐
│ Qdrant "concepts" collection   │
│                                │
│ Cosine Similarity:             │
│                                │
│ query_embedding vs concept_emb │
│   [0.12, 0.19, ...]           │
│   [0.11, 0.21, ...]  ← Python │
│        ↓                       │
│   similarity = 0.95            │
│                                │
│ Returns:                       │
│ - Python (score: 0.95)        │
│ - programming (score: 0.87)   │
│ - interpreter (score: 0.82)   │
└────────────────────────────────┘
```

**Timeline:**
- **Index-time:** Embed concepts and store (once per concept)
- **Query-time:** Embed query and compare (every search)

**Benefit:**
- Fast query-time (no need to re-embed concepts)
- Semantic matching (handles synonyms: "ML" finds "machine learning")

---

## 6. Storage Layer Architecture

**Complete storage topology for GraphRAG**

```
┌──────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                             │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│   Qdrant             │  │   Qdrant             │  │   Neo4j              │
│   Collection:        │  │   Collection:        │  │   Graph Database     │
│   "documents"        │  │   "concepts"         │  │                      │
├──────────────────────┤  ├──────────────────────┤  ├──────────────────────┤
│                      │  │                      │  │ (:Concept)           │
│ Stores:              │  │ Stores:              │  │   - id               │
│ - Document chunks    │  │ - Concept names      │  │   - name             │
│ - Vector: 1536D      │  │ - Vector: 1536D      │  │   - category         │
│ - Payload:           │  │ - Payload:           │  │   - tenant_id        │
│     content (text)   │  │     name (text)      │  │                      │
│     source           │  │     category         │  │ (:Document)          │
│     metadata         │  │     neo4j_id (link)  │  │   - id               │
│     tenant_id        │  │     tenant_id        │  │   - content          │
│                      │  │                      │  │   - tenant_id        │
│ Purpose:             │  │ Purpose:             │  │                      │
│ - Content retrieval  │  │ - Graph entry points │  │ Relationships:       │
│ - Semantic search    │  │ - Semantic concept   │  │ - RELATES_TO         │
│                      │  │   matching           │  │   (strength, context)│
│ Used by:             │  │                      │  │ - MENTIONS           │
│ - Regular RAG        │  │ Used by:             │  │   (count, confidence)│
│ - GraphRAG (vector)  │  │ - GraphRAG only      │  │                      │
│                      │  │                      │  │ Purpose:             │
│                      │  │                      │  │ - Multi-hop traversal│
│                      │  │                      │  │ - Relationship       │
│                      │  │                      │  │   discovery          │
│                      │  │                      │  │                      │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘
        ↑                          ↑                          ↑
        │                          │                          │
   Vector search            Semantic concept          Graph traversal
   (by similarity)          entry points              (by relationships)
```

**Data Relationships:**

```
Document Chunk ──[embedded via OpenAI]──→ Qdrant "documents" collection
     │
     │ [extracted entities]
     ▼
Concept ──[embedded via OpenAI]──→ Qdrant "concepts" collection
     │
     │ [same concept]
     ▼
Neo4j Concept Node ──[RELATES_TO]──→ Other Concepts
     │
     │ [MENTIONS]
     ▼
Neo4j Document Node
```

**Key Insight:**
- **Qdrant "documents"** = Content for retrieval
- **Qdrant "concepts"** = Entry points for graph
- **Neo4j** = Relationship structure

All three work together for GraphRAG!

---

## 7. Current vs Proposed: Semantic Concept Search

**The Problem:** Current keyword extraction fails for synonyms and abbreviations

### Current Architecture (BROKEN)

```
┌────────────────────────────────────────────────────────────┐
│              CURRENT: Keyword Extraction                   │
└────────────────────────────────────────────────────────────┘

User Query: "How does ML work?"
     │
     ▼
┌────────────────────────────┐
│ Keyword Extraction         │  String parsing
│ (No embedding used!)       │
│                            │
│ 1. Split by spaces         │
│ 2. Filter capitalized      │
│ 3. Filter length > 6       │
└────────┬───────────────────┘
         │
         │ Result: []  ← FAILS!
         │ (ML is 2 chars, lowercase)
         │
         ▼
┌────────────────────────────┐
│ Graph Traversal            │
│                            │
│ No concepts found!         │
│ ❌ Skipped                 │
└────────────────────────────┘

Problem: Can't find "ML", "machine learning", "deep learning"
```

### Proposed Architecture (FIXED)

```
┌────────────────────────────────────────────────────────────┐
│           PROPOSED: Semantic Concept Search                │
└────────────────────────────────────────────────────────────┘

User Query: "How does ML work?"
     │
     ▼
┌────────────────────────────┐
│ Embedding Service          │  Generate query embedding
└────────┬───────────────────┘
         │
         │ [0.15, 0.23, 0.41, ...]  (1536D)
         │
         ▼
┌────────────────────────────────────┐
│ Qdrant "concepts" collection       │
│                                    │
│ Semantic similarity search:        │
│                                    │
│ Query embedding vs stored concepts:│
│                                    │
│ - "machine learning" → 0.92 ✓     │
│ - "ML" → 0.89 ✓                   │
│ - "deep learning" → 0.85 ✓        │
│ - "artificial intelligence" → 0.81│
│ - "neural networks" → 0.78        │
└────────┬───────────────────────────┘
         │
         │ Returns top 3 concepts
         │
         ▼
┌────────────────────────────┐
│ Graph Traversal            │
│                            │
│ Start from:                │
│ - machine learning         │
│ - ML                       │
│ - deep learning            │
│                            │
│ ✅ Works!                  │
└────────────────────────────┘

Solution: Semantic search handles synonyms automatically!
```

### Before vs After Comparison

```
┌─────────────────────────────────────────────────────────────┐
│                  SIDE-BY-SIDE COMPARISON                    │
├────────────────────────────┬────────────────────────────────┤
│     BEFORE (Keyword)       │    AFTER (Semantic)            │
├────────────────────────────┼────────────────────────────────┤
│                            │                                │
│ Query: "ML tutorials"      │ Query: "ML tutorials"          │
│   ↓                        │   ↓                            │
│ Keyword extraction         │ Semantic embedding             │
│   ↓                        │   ↓                            │
│ Result: []                 │ Search concepts collection     │
│   ↓                        │   ↓                            │
│ ❌ No graph traversal      │ Found: ["ML", "machine         │
│                            │         learning",             │
│                            │         "tutorials"]           │
│                            │   ↓                            │
│                            │ ✅ Graph traversal works       │
│                            │                                │
├────────────────────────────┼────────────────────────────────┤
│ Query: "Python data tools" │ Query: "Python data tools"     │
│   ↓                        │   ↓                            │
│ Keyword extraction         │ Semantic embedding             │
│   ↓                        │   ↓                            │
│ Result: ["Python"]         │ Found: ["Python", "pandas",    │
│   ↓                        │         "NumPy", "data         │
│ Limited traversal          │         science", "matplotlib"]│
│                            │   ↓                            │
│ ⚠️ Misses related tools   │ ✅ Finds all related concepts  │
│                            │                                │
└────────────────────────────┴────────────────────────────────┘
```

**Expected Improvement:**
- **Recall:** +15-20% (finds more relevant concepts)
- **Synonym handling:** Perfect (semantic matching)
- **Abbreviation handling:** Perfect ("ML" = "machine learning")
- **Related concepts:** Better (finds semantically similar, not just exact matches)

---

## Summary

### Complete Pipeline

**Ingestion → Storage → Query**

```
Document Upload (Section 1)
       ↓
   Chunking + Embedding + Entity Extraction
       ↓
   Storage (Qdrant + Neo4j)
       ↓
   Query Time (Sections 2-3)
       ↓
   Search (Regular RAG or GraphRAG)
       ↓
   Results
```

### Feature Comparison

| Feature | Regular RAG | GraphRAG (Current) | GraphRAG (Proposed) |
|---------|-------------|-------------------|---------------------|
| **Storage** | 1 collection | 2 collections + Neo4j | 2 collections + Neo4j |
| **Concept Search** | N/A | Keyword (broken) | Semantic (fixed) |
| **Graph Traversal** | No | Yes (limited) | Yes (enhanced) |
| **Synonym Handling** | N/A | ❌ Fails | ✅ Works |
| **Embeddings** | Documents only | Documents only | Documents + Concepts |
| **Use Case** | Simple retrieval | Relationship-aware | Relationship-aware (improved) |

---

**Next Steps:**
- [Implementation Plan](../gnn/GETTING_STARTED.md) - How to implement semantic concept search
- [GNN Architecture](../gnn/ARCHITECTURE.md) - Future enhancements with Graph Neural Networks

---

**Last Updated:** March 28, 2026
**Status:** Architecture documentation
**Maintained By:** Cortex-AI Team
