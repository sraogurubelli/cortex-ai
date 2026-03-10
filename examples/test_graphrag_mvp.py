"""
GraphRAG MVP Demo - Knowledge Graph Building

Demonstrates automatic entity extraction and graph building during document ingestion.

This MVP shows:
1. Document ingestion with automatic entity extraction
2. Knowledge graph population in Neo4j
3. Querying the graph to see extracted entities

Requirements:
- Docker running with Neo4j (docker-compose up -d neo4j)
- OpenAI API key for embeddings and entity extraction
- Qdrant and Redis running

Setup:
    docker-compose up -d neo4j qdrant redis

Run:
    OPENAI_API_KEY=sk-... python examples/test_graphrag_mvp.py
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cortex.rag import (
    EmbeddingService,
    VectorStore,
    DocumentManager,
    GraphStore,
    EntityExtractor,
)
from cortex.orchestration import ModelConfig


async def demo_graphrag_mvp():
    """Demonstrate GraphRAG MVP with automatic entity extraction."""

    print("=" * 80)
    print("GraphRAG MVP Demo - Knowledge Graph Building")
    print("=" * 80)
    print()

    # Initialize components
    print("📦 Initializing RAG components...")

    # Embeddings
    embeddings = EmbeddingService(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        redis_url=os.getenv("CORTEX_REDIS_URL", "redis://localhost:6379"),
    )
    await embeddings.connect()
    print("✅ Embedding service connected")

    # Vector store
    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="graphrag_demo",
    )
    await vector_store.connect()
    await vector_store.create_collection()
    print("✅ Vector store connected")

    # Graph store
    graph_store = GraphStore(
        url=os.getenv("CORTEX_NEO4J_URL", "bolt://localhost:7687"),
        user=os.getenv("CORTEX_NEO4J_USER", "neo4j"),
        password=os.getenv("CORTEX_NEO4J_PASSWORD", "cortex_neo4j_password"),
    )
    await graph_store.connect()
    await graph_store.create_constraints()
    print("✅ Graph store connected")

    # Entity extractor
    extractor = EntityExtractor(
        model=ModelConfig(
            model="gpt-4o-mini",  # Cheaper model for extraction
            temperature=0.0,
        )
    )
    print("✅ Entity extractor initialized")

    # Document manager with GraphRAG
    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
        entity_extractor=extractor,
    )
    print("✅ Document manager initialized with GraphRAG support")
    print()

    # Demo documents
    documents = [
        {
            "doc_id": "graphrag-intro",
            "content": """GraphRAG is a methodology that combines knowledge graphs with
            Retrieval-Augmented Generation. It uses Neo4j as a graph database to store
            entities and relationships extracted from documents. GraphRAG enables
            relationship-aware retrieval by traversing the knowledge graph alongside
            traditional vector search. Python is commonly used to implement GraphRAG
            systems, often leveraging frameworks like LangGraph for orchestration.""",
            "metadata": {"source": "docs", "category": "methodology"},
        },
        {
            "doc_id": "neo4j-overview",
            "content": """Neo4j is a native graph database that uses the Cypher query
            language. It excels at storing and querying highly connected data through
            nodes and relationships. Neo4j supports ACID transactions and horizontal
            scaling. Many AI applications use Neo4j for knowledge graph storage because
            it efficiently handles complex relationship traversals. Python developers
            can access Neo4j using the official neo4j-driver package.""",
            "metadata": {"source": "docs", "category": "technology"},
        },
        {
            "doc_id": "python-ai",
            "content": """Python is the dominant language for AI and machine learning
            development. It provides rich ecosystems for deep learning (PyTorch, TensorFlow),
            natural language processing (transformers, spaCy), and AI orchestration
            (LangChain, LangGraph). Python's simplicity and extensive libraries make it
            ideal for building RAG systems, chatbots, and knowledge graph applications.""",
            "metadata": {"source": "docs", "category": "language"},
        },
    ]

    # Ingest documents with entity extraction
    print("📄 Ingesting documents with entity extraction...")
    print()

    for i, doc in enumerate(documents, 1):
        print(f"Processing document {i}/{len(documents)}: {doc['doc_id']}")
        print(f"Content preview: {doc['content'][:100]}...")
        print()

        num_chunks = await doc_manager.ingest_document(
            doc_id=doc["doc_id"],
            content=doc["content"],
            metadata=doc["metadata"],
            tenant_id="demo-tenant",
            extract_entities=True,  # Enable entity extraction
        )

        print(f"✅ Ingested {num_chunks} chunk(s)")
        print()

    print("=" * 80)
    print("📊 Verifying Knowledge Graph")
    print("=" * 80)
    print()

    # Verify graph populated
    for doc in documents:
        doc_id = doc["doc_id"]
        concepts = await graph_store.get_document_concepts(doc_id)

        print(f"Document: {doc_id}")
        print(f"Extracted concepts ({len(concepts)}):")
        for concept in concepts:
            print(f"  - {concept.name} ({concept.category})")
        print()

    # Check graph health
    health = await graph_store.health_check()
    print(f"Graph store health: {'✅ Healthy' if health else '❌ Unhealthy'}")
    print()

    print("=" * 80)
    print("🎉 GraphRAG MVP Demo Complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. View the graph in Neo4j Browser: http://localhost:7474")
    print("   - Username: neo4j")
    print("   - Password: cortex_neo4j_password")
    print()
    print("2. Run Cypher queries to explore:")
    print("   MATCH (d:Document)-[:MENTIONS]->(c:Concept) RETURN d, c")
    print("   MATCH (c1:Concept)-[:RELATES_TO]->(c2:Concept) RETURN c1, c2")
    print()
    print("3. Ready for Phase 3: Graph search and hybrid retrieval")
    print()

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    await graph_store.disconnect()


if __name__ == "__main__":
    # Check environment
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print()
        print("Set it with: export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    # Run demo
    asyncio.run(demo_graphrag_mvp())
