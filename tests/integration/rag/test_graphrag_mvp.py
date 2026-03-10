"""
Integration tests for GraphRAG MVP.

Tests the full flow: document ingestion → entity extraction → graph population.

Requirements:
- Docker running with Neo4j, Qdrant, Redis
- OpenAI API key set

Setup:
    docker-compose up -d neo4j qdrant redis

Run:
    OPENAI_API_KEY=sk-... pytest tests/integration/rag/test_graphrag_mvp.py -v
"""

import os
import uuid
import pytest

from cortex.rag import (
    EmbeddingService,
    VectorStore,
    DocumentManager,
    GraphStore,
    EntityExtractor,
)
from cortex.orchestration import ModelConfig


@pytest.fixture
async def rag_components():
    """Setup RAG components with GraphRAG support."""
    # Embeddings
    embeddings = EmbeddingService(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        redis_url=os.getenv("CORTEX_REDIS_URL", "redis://localhost:6379"),
    )
    await embeddings.connect()

    # Vector store
    collection_name = f"test_graphrag_{uuid.uuid4().hex[:8]}"
    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name=collection_name,
    )
    await vector_store.connect()
    await vector_store.create_collection()

    # Graph store
    graph_store = GraphStore(
        url=os.getenv("CORTEX_NEO4J_URL", "bolt://localhost:7687"),
        user=os.getenv("CORTEX_NEO4J_USER", "neo4j"),
        password=os.getenv("CORTEX_NEO4J_PASSWORD", "cortex_neo4j_password"),
    )
    await graph_store.connect()
    await graph_store.create_constraints()

    # Entity extractor
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

    yield {
        "embeddings": embeddings,
        "vector_store": vector_store,
        "graph_store": graph_store,
        "extractor": extractor,
        "doc_manager": doc_manager,
    }

    # Cleanup
    # Delete test documents from graph
    if graph_store.driver:
        async with graph_store.driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.tenant_id = 'integration-test' DETACH DELETE n"
            )

    # Delete vector collection
    await vector_store.delete_collection()

    # Disconnect
    await embeddings.disconnect()
    await vector_store.disconnect()
    await graph_store.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_graphrag_mvp_full_flow(rag_components):
    """Test complete GraphRAG flow: ingest → extract → verify graph."""
    doc_manager = rag_components["doc_manager"]
    graph_store = rag_components["graph_store"]

    # Ingest document with entity extraction
    doc_id = f"test-doc-{uuid.uuid4()}"
    content = """GraphRAG uses Neo4j for building knowledge graphs with Python.
    It combines vector search in Qdrant with graph traversal in Neo4j for
    relationship-aware retrieval."""

    num_chunks = await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        metadata={"source": "test"},
        tenant_id="integration-test",
        extract_entities=True,
    )

    # Verify vector store ingestion
    assert num_chunks >= 1

    # Verify graph populated
    concepts = await graph_store.get_document_concepts(doc_id)
    assert len(concepts) > 0

    # Verify at least some expected concepts
    concept_names = [c.name.lower() for c in concepts]
    assert any("graphrag" in name for name in concept_names)
    assert any("neo4j" in name for name in concept_names)

    # Verify document in graph
    doc = await graph_store.get_document(doc_id)
    assert doc is not None
    assert doc.id == doc_id
    assert doc.tenant_id == "integration-test"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_graphrag_multiple_documents(rag_components):
    """Test GraphRAG with multiple documents sharing concepts."""
    doc_manager = rag_components["doc_manager"]
    graph_store = rag_components["graph_store"]

    # Ingest multiple documents
    documents = [
        {
            "doc_id": f"test-doc-{uuid.uuid4()}",
            "content": "GraphRAG uses Neo4j for knowledge graphs.",
        },
        {
            "doc_id": f"test-doc-{uuid.uuid4()}",
            "content": "Neo4j is a graph database that stores nodes and relationships.",
        },
        {
            "doc_id": f"test-doc-{uuid.uuid4()}",
            "content": "Python is commonly used with Neo4j for graph applications.",
        },
    ]

    for doc in documents:
        await doc_manager.ingest_document(
            doc_id=doc["doc_id"],
            content=doc["content"],
            tenant_id="integration-test",
            extract_entities=True,
        )

    # Verify all documents have concepts
    for doc in documents:
        concepts = await graph_store.get_document_concepts(doc["doc_id"])
        assert len(concepts) > 0

    # Verify shared concepts (Neo4j should appear in multiple docs)
    # This tests that MERGE correctly handles duplicate concepts
    doc1_concepts = await graph_store.get_document_concepts(documents[0]["doc_id"])
    doc2_concepts = await graph_store.get_document_concepts(documents[1]["doc_id"])

    # Both should have Neo4j concept
    doc1_names = {c.name.lower() for c in doc1_concepts}
    doc2_names = {c.name.lower() for c in doc2_concepts}

    assert any("neo4j" in name for name in doc1_names)
    assert any("neo4j" in name for name in doc2_names)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_graphrag_disabled(rag_components):
    """Test that document ingestion works when extract_entities=False."""
    doc_manager = rag_components["doc_manager"]
    graph_store = rag_components["graph_store"]

    # Ingest without entity extraction
    doc_id = f"test-doc-{uuid.uuid4()}"
    content = "This document should not populate the graph."

    num_chunks = await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        tenant_id="integration-test",
        extract_entities=False,  # Disable GraphRAG
    )

    # Verify vector store ingestion still works
    assert num_chunks >= 1

    # Verify graph NOT populated (document should not exist)
    doc = await graph_store.get_document(doc_id)
    assert doc is None


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_graphrag_tenant_isolation(rag_components):
    """Test that tenant isolation works in GraphRAG."""
    doc_manager = rag_components["doc_manager"]
    graph_store = rag_components["graph_store"]

    # Ingest documents in different tenants
    doc_id_1 = f"test-doc-{uuid.uuid4()}"
    doc_id_2 = f"test-doc-{uuid.uuid4()}"

    await doc_manager.ingest_document(
        doc_id=doc_id_1,
        content="GraphRAG in tenant 1",
        tenant_id="tenant-1",
        extract_entities=True,
    )

    await doc_manager.ingest_document(
        doc_id=doc_id_2,
        content="GraphRAG in tenant 2",
        tenant_id="tenant-2",
        extract_entities=True,
    )

    # Verify tenant isolation
    concepts_1 = await graph_store.get_document_concepts(
        doc_id_1,
        tenant_id="tenant-1",
    )
    concepts_2 = await graph_store.get_document_concepts(
        doc_id_2,
        tenant_id="tenant-2",
    )

    # Both should have concepts
    assert len(concepts_1) > 0
    assert len(concepts_2) > 0

    # Verify concepts belong to correct tenants
    for concept in concepts_1:
        assert concept.tenant_id == "tenant-1"

    for concept in concepts_2:
        assert concept.tenant_id == "tenant-2"

    # Cleanup
    await graph_store.delete_document(doc_id_1)
    await graph_store.delete_document(doc_id_2)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_graphrag_error_handling(rag_components):
    """Test that vector ingestion succeeds even if graph extraction fails."""
    # Create doc manager WITHOUT entity extractor (will fail gracefully)
    embeddings = rag_components["embeddings"]
    vector_store = rag_components["vector_store"]
    graph_store = rag_components["graph_store"]

    doc_manager_no_extractor = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
        entity_extractor=None,  # Missing extractor
    )

    # Ingest should succeed (vector store) even though graph extraction is skipped
    doc_id = f"test-doc-{uuid.uuid4()}"
    num_chunks = await doc_manager_no_extractor.ingest_document(
        doc_id=doc_id,
        content="Test content",
        tenant_id="integration-test",
        extract_entities=True,  # Will be skipped since extractor is None
    )

    # Vector ingestion should succeed
    assert num_chunks >= 1

    # Graph should be empty
    doc = await graph_store.get_document(doc_id)
    assert doc is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graphrag_health_check(rag_components):
    """Test GraphStore health check."""
    graph_store = rag_components["graph_store"]

    health = await graph_store.health_check()
    assert health is True


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_graphrag_realistic_document(rag_components):
    """Test GraphRAG with a realistic technical document."""
    doc_manager = rag_components["doc_manager"]
    graph_store = rag_components["graph_store"]

    doc_id = f"test-doc-{uuid.uuid4()}"
    content = """
    GraphRAG is an advanced methodology that enhances Retrieval-Augmented Generation
    by incorporating knowledge graphs. Unlike traditional RAG systems that rely solely
    on vector similarity search in databases like Qdrant, GraphRAG uses Neo4j to store
    entities and their relationships.

    The process involves extracting entities from documents using LLMs like GPT-4,
    storing entities as nodes in Neo4j, and creating relationships between entities.
    This hybrid approach enables more context-aware retrieval by traversing relationship
    paths in the knowledge graph alongside vector search.

    Python is commonly used to implement GraphRAG systems, often with frameworks like
    LangGraph for agent orchestration and LangChain for LLM integration.
    """

    num_chunks = await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        metadata={"source": "documentation", "category": "technical"},
        tenant_id="integration-test",
        extract_entities=True,
    )

    # Verify ingestion
    assert num_chunks >= 1

    # Verify rich graph extraction
    concepts = await graph_store.get_document_concepts(doc_id)
    assert len(concepts) >= 5  # Should extract multiple concepts

    # Verify expected concepts
    concept_names = {c.name.lower() for c in concepts}
    assert any("graphrag" in name for name in concept_names)
    assert any("neo4j" in name for name in concept_names)

    # Verify concepts have categories
    for concept in concepts:
        assert concept.category is not None
        assert len(concept.category) > 0
