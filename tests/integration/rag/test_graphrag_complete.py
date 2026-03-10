"""
Integration tests for GraphRAG complete system (Phases 3-5).

Tests graph search, hybrid retrieval, and RRF fusion.
"""

import os
import pytest

from cortex.rag import (
    EmbeddingService,
    VectorStore,
    DocumentManager,
    Retriever,
    GraphStore,
    EntityExtractor,
)
from cortex.orchestration import ModelConfig


@pytest.fixture
async def graphrag_system():
    """Setup complete GraphRAG system."""
    # Embeddings
    embeddings = EmbeddingService(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        redis_url=os.getenv("CORTEX_REDIS_URL", "redis://localhost:6379"),
    )
    await embeddings.connect()

    # Vector store
    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="test_graphrag_complete",
    )
    await vector_store.connect()
    await vector_store.create_collection()

    # Graph store
    graph_store = GraphStore(
        url=os.getenv("CORTEX_NEO4J_URL", "bolt://localhost:7687"),
        password=os.getenv("CORTEX_NEO4J_PASSWORD", "cortex_neo4j_password"),
    )
    await graph_store.connect()
    await graph_store.create_constraints()

    # Entity extractor
    extractor = EntityExtractor(ModelConfig(model="gpt-4o-mini", temperature=0.0))

    # Document manager
    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
        entity_extractor=extractor,
    )

    # Retriever with GraphRAG
    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
    )

    # Ingest test documents
    documents = [
        {
            "doc_id": "test-langraph",
            "content": "LangGraph is a framework for building multi-agent systems with Python.",
        },
        {
            "doc_id": "test-python",
            "content": "Python is a programming language used for AI and machine learning.",
        },
        {
            "doc_id": "test-ai",
            "content": "Artificial intelligence applications use frameworks like LangGraph and libraries in Python.",
        },
    ]

    for doc in documents:
        await doc_manager.ingest_document(
            doc_id=doc["doc_id"],
            content=doc["content"],
            tenant_id="test",
            extract_entities=True,
        )

    yield {
        "embeddings": embeddings,
        "vector_store": vector_store,
        "graph_store": graph_store,
        "doc_manager": doc_manager,
        "retriever": retriever,
    }

    # Cleanup
    if graph_store.driver:
        async with graph_store.driver.session() as session:
            await session.run("MATCH (n) WHERE n.tenant_id = 'test' DETACH DELETE n")

    await vector_store.delete_collection()
    await embeddings.disconnect()
    await vector_store.disconnect()
    await graph_store.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_graph_search(graphrag_system):
    """Test Phase 3: Graph search."""
    retriever = graphrag_system["retriever"]

    # Search for a concept that should exist
    results = await retriever.graph_search(
        concept_name="LangGraph",
        max_hops=2,
        tenant_id="test",
    )

    # Should find at least one document
    assert len(results) > 0

    # Results should have correct structure
    for result in results:
        assert result.id is not None
        assert result.content is not None
        assert result.score >= 0.0
        assert result.score <= 1.0
        assert "source" in result.metadata
        assert result.metadata["source"] == "graph"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_graph_search_no_results(graphrag_system):
    """Test graph search with non-existent concept."""
    retriever = graphrag_system["retriever"]

    results = await retriever.graph_search(
        concept_name="NonExistentConcept",
        max_hops=2,
        tenant_id="test",
    )

    # Should return empty list
    assert results == []


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_graph_search_max_hops(graphrag_system):
    """Test graph search with different max_hops."""
    retriever = graphrag_system["retriever"]

    # Search with 0 hops (only direct mentions)
    results_0_hop = await retriever.graph_search(
        concept_name="Python",
        max_hops=0,
        tenant_id="test",
    )

    # Search with 2 hops (includes related concepts)
    results_2_hop = await retriever.graph_search(
        concept_name="Python",
        max_hops=2,
        tenant_id="test",
    )

    # 2-hop should find same or more results
    assert len(results_2_hop) >= len(results_0_hop)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_graphrag_search(graphrag_system):
    """Test Phase 4: Hybrid GraphRAG search."""
    retriever = graphrag_system["retriever"]

    results = await retriever.graphrag_search(
        query="What frameworks are used for AI development?",
        top_k=3,
        vector_weight=0.7,
        graph_weight=0.3,
        tenant_id="test",
    )

    # Should return results
    assert len(results) > 0
    assert len(results) <= 3

    # Results should have RRF scores
    for result in results:
        assert "rrf_score" in result.metadata
        assert "in_vector" in result.metadata
        assert "in_graph" in result.metadata


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_graphrag_search_weights(graphrag_system):
    """Test GraphRAG search with different weight configurations."""
    retriever = graphrag_system["retriever"]

    query = "Python programming"

    # Vector-only (graph_weight=0)
    vector_only = await retriever.graphrag_search(
        query=query,
        top_k=3,
        vector_weight=1.0,
        graph_weight=0.0,
        tenant_id="test",
    )

    # Graph-only (vector_weight=0)
    graph_only = await retriever.graphrag_search(
        query=query,
        top_k=3,
        vector_weight=0.0,
        graph_weight=1.0,
        tenant_id="test",
    )

    # Balanced
    balanced = await retriever.graphrag_search(
        query=query,
        top_k=3,
        vector_weight=0.5,
        graph_weight=0.5,
        tenant_id="test",
    )

    # All should return results
    assert len(vector_only) > 0
    assert len(graph_only) > 0
    assert len(balanced) > 0

    # Results may differ based on weights
    # (This is expected - different weights produce different rankings)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_graphrag_search_fallback(graphrag_system):
    """Test GraphRAG search fallback when graph store unavailable."""
    retriever_no_graph = Retriever(
        embeddings=graphrag_system["embeddings"],
        vector_store=graphrag_system["vector_store"],
        graph_store=None,  # No graph store
    )

    # Should fallback to pure vector search
    results = await retriever_no_graph.graphrag_search(
        query="Python programming",
        top_k=3,
        tenant_id="test",
    )

    # Should still return results (from vector search)
    assert len(results) > 0


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_rrf_fusion(graphrag_system):
    """Test Reciprocal Rank Fusion combines results correctly."""
    retriever = graphrag_system["retriever"]

    # Get both vector and GraphRAG results
    query = "AI frameworks"

    vector_results = await retriever.search(query, top_k=3, tenant_id="test")
    graphrag_results = await retriever.graphrag_search(
        query, top_k=3, vector_weight=0.5, graph_weight=0.5, tenant_id="test"
    )

    # GraphRAG results should have fusion metadata
    for result in graphrag_results:
        assert "rrf_score" in result.metadata


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_search_no_graph_store(graphrag_system):
    """Test graph search raises error when no graph store."""
    retriever_no_graph = Retriever(
        embeddings=graphrag_system["embeddings"],
        vector_store=graphrag_system["vector_store"],
        graph_store=None,
    )

    with pytest.raises(ValueError, match="GraphStore not configured"):
        await retriever_no_graph.graph_search(concept_name="Test", tenant_id="test")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_graph_search_tenant_isolation(graphrag_system):
    """Test graph search respects tenant isolation."""
    retriever = graphrag_system["retriever"]
    doc_manager = graphrag_system["doc_manager"]

    # Add document to different tenant
    await doc_manager.ingest_document(
        doc_id="test-other-tenant",
        content="LangGraph is great for building agents.",
        tenant_id="other-tenant",
        extract_entities=True,
    )

    # Search in original tenant
    results_test = await retriever.graph_search(
        concept_name="LangGraph",
        tenant_id="test",
    )

    # Search in other tenant
    results_other = await retriever.graph_search(
        concept_name="LangGraph",
        tenant_id="other-tenant",
    )

    # Both should have results but from different tenants
    assert len(results_test) > 0
    assert len(results_other) > 0

    # Results should not overlap
    test_ids = {r.id for r in results_test}
    other_ids = {r.id for r in results_other}
    assert test_ids.isdisjoint(other_ids)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
async def test_concept_extraction_from_query(graphrag_system):
    """Test concept extraction from query text."""
    retriever = graphrag_system["retriever"]

    # Test capitalized words
    concepts = retriever._extract_concepts_from_query("What is LangGraph and Python?")
    assert "LangGraph" in concepts
    assert "Python" in concepts

    # Test fallback to longer words
    concepts = retriever._extract_concepts_from_query("what is machine learning")
    assert "machine" in concepts or "learning" in concepts
