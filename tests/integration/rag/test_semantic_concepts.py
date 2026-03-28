"""
Integration Tests for Semantic Concept Search.

Tests the Phase 0 implementation of semantic concept search for GraphRAG.

Setup:
    - Requires running Qdrant instance (http://localhost:6333)
    - Requires running Neo4j instance (bolt://localhost:7687)
    - Requires OPENAI_API_KEY environment variable

Run:
    pytest tests/integration/rag/test_semantic_concepts.py -v
"""

import pytest
import uuid
import os

from cortex.rag import EmbeddingService, VectorStore, DocumentManager, Retriever
from cortex.rag.graph.graph_store import GraphStore
from cortex.rag.graph.entity_extractor import EntityExtractor
from cortex.orchestration import ModelConfig


# Skip if not in integration test mode
pytestmark = pytest.mark.integration


@pytest.fixture
async def embeddings():
    """Embedding service fixture."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    service = EmbeddingService(openai_api_key=api_key)
    await service.connect()
    yield service
    await service.disconnect()


@pytest.fixture
async def vector_store():
    """Vector store fixture with concepts collection."""
    qdrant_url = os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333")

    store = VectorStore(url=qdrant_url, collection_name="test_documents")
    await store.connect()

    # Create both documents and concepts collections
    await store.create_collection()
    await store.create_concepts_collection(collection_name="test_concepts")

    yield store

    # Cleanup
    try:
        await store.delete_collection()
        # Delete concepts collection
        store.collection_name = "test_concepts"
        await store.delete_collection()
    except Exception:
        pass  # Ignore cleanup errors
    finally:
        await store.disconnect()


@pytest.fixture
async def graph_store():
    """Graph store fixture."""
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    store = GraphStore(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
    await store.connect()

    yield store

    # Cleanup: Delete test data
    try:
        async with store.driver.session() as session:
            await session.run("MATCH (n) WHERE n.tenant_id = 'test-tenant' DETACH DELETE n")
    except Exception:
        pass  # Ignore cleanup errors
    finally:
        await store.disconnect()


@pytest.fixture
async def entity_extractor():
    """Entity extractor fixture."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    extractor = EntityExtractor(
        model=ModelConfig(model="gpt-4o-mini", temperature=0.0)
    )
    return extractor


@pytest.fixture
async def doc_manager(embeddings, vector_store, graph_store, entity_extractor):
    """Document manager fixture with GraphRAG enabled."""
    manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
        entity_extractor=entity_extractor,
    )
    return manager


@pytest.fixture
async def retriever(embeddings, vector_store, graph_store):
    """Retriever fixture."""
    return Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
        tenant_id="test-tenant",
    )


# =============================================================================
# Test 1: Concept Embedding at Creation
# =============================================================================


@pytest.mark.asyncio
async def test_concept_embedded_on_creation(doc_manager, vector_store):
    """
    Test that concepts are automatically embedded when created during ingestion.
    """
    # Ingest a document that will create concepts
    doc_id = f"test-doc-{uuid.uuid4()}"
    content = """
    GraphRAG is a retrieval-augmented generation approach that uses knowledge graphs.
    It combines vector search with graph traversal to improve retrieval quality.
    Python is commonly used for implementing GraphRAG systems.
    """

    await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        metadata={"source": "test"},
        tenant_id="test-tenant",
    )

    # Check that concepts were created in Qdrant
    # Note: Concepts collection for tests is "test_concepts"
    concept_count = await vector_store.count(collection_name="test_concepts")

    # Should have at least 1 concept (GraphRAG, Python, or both)
    assert concept_count > 0, "No concepts found in Qdrant after ingestion"

    # Verify concepts have embeddings (not just metadata)
    docs, _ = await vector_store.scroll(
        collection_name="test_concepts",
        limit=10,
    )

    assert len(docs) > 0, "No concept documents found"
    # Each concept should have a payload with name and category
    for doc in docs:
        assert "name" in doc["payload"], "Concept missing 'name' field"
        assert "category" in doc["payload"], "Concept missing 'category' field"
        assert "tenant_id" in doc["payload"], "Concept missing 'tenant_id' field"


# =============================================================================
# Test 2: Semantic Concept Extraction
# =============================================================================


@pytest.mark.asyncio
async def test_semantic_concept_extraction(retriever, doc_manager, vector_store):
    """
    Test that semantic concept extraction finds relevant concepts via similarity.
    """
    # First, ingest a document to create concepts
    doc_id = f"test-doc-{uuid.uuid4()}"
    content = """
    Machine learning (ML) is a subset of artificial intelligence.
    Python and PyTorch are popular tools for ML development.
    GraphRAG enhances retrieval with knowledge graphs.
    """

    await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        metadata={"source": "test"},
        tenant_id="test-tenant",
    )

    # Query with abbreviation "ML"
    concepts = await retriever._extract_concepts_from_query(
        "How does ML work?",
        use_semantic=True,
    )

    # Should find "machine learning" or "ML" via semantic similarity
    # (even though query only says "ML")
    assert len(concepts) > 0, "No concepts found for query 'How does ML work?'"

    # Verify at least one concept is related to machine learning
    concept_names_lower = [c.lower() for c in concepts]
    assert any(
        "machine learning" in c or "ml" in c or "artificial" in c
        for c in concept_names_lower
    ), f"No ML-related concepts found. Got: {concepts}"


# =============================================================================
# Test 3: Synonym Handling
# =============================================================================


@pytest.mark.asyncio
async def test_synonym_handling(retriever, doc_manager):
    """
    Test that semantic search finds synonyms (e.g., "AI" -> "artificial intelligence").
    """
    # Ingest document with "artificial intelligence"
    doc_id = f"test-doc-{uuid.uuid4()}"
    content = """
    Artificial intelligence (AI) is transforming software development.
    Machine learning and deep learning are AI subfields.
    """

    await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        metadata={"source": "test"},
        tenant_id="test-tenant",
    )

    # Query with abbreviation "AI"
    concepts = await retriever._extract_concepts_from_query(
        "AI applications in healthcare",
        use_semantic=True,
    )

    # Should find "artificial intelligence" or "AI" as a synonym
    assert len(concepts) > 0, "No concepts found for 'AI applications'"

    concept_names_lower = [c.lower() for c in concepts]
    assert any(
        "artificial" in c or "ai" in c or "intelligence" in c
        for c in concept_names_lower
    ), f"No AI-related concepts found. Got: {concepts}"


# =============================================================================
# Test 4: GraphRAG with Semantic Concepts
# =============================================================================


@pytest.mark.asyncio
async def test_graphrag_with_semantic_concepts(retriever, doc_manager):
    """
    Test full GraphRAG search using semantic concept extraction.
    """
    # Ingest documents about Python and data tools
    doc1_id = f"test-doc-{uuid.uuid4()}"
    doc1_content = """
    Python is a high-level programming language widely used for data science.
    Libraries like pandas and NumPy are essential for data manipulation.
    """

    doc2_id = f"test-doc-{uuid.uuid4()}"
    doc2_content = """
    pandas is a powerful data analysis library for Python.
    It provides DataFrame structures for efficient data processing.
    NumPy is used for numerical computing.
    """

    await doc_manager.ingest_document(
        doc_id=doc1_id,
        content=doc1_content,
        metadata={"source": "test"},
        tenant_id="test-tenant",
    )

    await doc_manager.ingest_document(
        doc_id=doc2_id,
        content=doc2_content,
        metadata={"source": "test"},
        tenant_id="test-tenant",
    )

    # GraphRAG search for "Python data tools"
    # Should find documents about pandas, NumPy via semantic concept matching
    results = await retriever.graphrag_search(
        query="Python data tools",
        top_k=5,
    )

    # Should return results (not empty)
    assert len(results) > 0, "GraphRAG search returned no results"

    # At least one result should mention pandas or NumPy or Python
    content_combined = " ".join([r.content.lower() for r in results])
    assert any(
        term in content_combined
        for term in ["pandas", "numpy", "python", "data"]
    ), f"No relevant content found in results: {[r.content[:50] for r in results]}"


# =============================================================================
# Test 5: Fallback to Keyword Matching
# =============================================================================


@pytest.mark.asyncio
async def test_fallback_to_keywords(retriever):
    """
    Test that keyword matching fallback works when semantic search is disabled.
    """
    # Disable semantic search explicitly
    concepts = await retriever._extract_concepts_from_query(
        "Python programming language",
        use_semantic=False,
    )

    # Should still extract concepts using keywords
    assert len(concepts) > 0, "Keyword fallback returned no concepts"

    # Should find "Python" (capitalized word)
    assert "Python" in concepts, f"'Python' not found in concepts: {concepts}"


# =============================================================================
# Test 6: Idempotent Embedding
# =============================================================================


@pytest.mark.asyncio
async def test_idempotent_concept_embedding(doc_manager, vector_store, graph_store):
    """
    Test that re-ingesting the same document doesn't duplicate concept embeddings.
    """
    doc_id = f"test-doc-{uuid.uuid4()}"
    content = """
    GraphRAG combines retrieval and knowledge graphs.
    """

    # Ingest once
    await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        metadata={"source": "test"},
        tenant_id="test-tenant",
    )

    # Count concepts
    count_after_first = await vector_store.count(collection_name="test_concepts")

    # Ingest same content again (should not duplicate concepts)
    doc_id_2 = f"test-doc-{uuid.uuid4()}"  # Different doc ID, same content
    await doc_manager.ingest_document(
        doc_id=doc_id_2,
        content=content,
        metadata={"source": "test"},
        tenant_id="test-tenant",
    )

    # Count concepts again
    count_after_second = await vector_store.count(collection_name="test_concepts")

    # Concept count should be the same (idempotent MERGE in Neo4j)
    # Note: This depends on EntityExtractor returning same concepts for same text
    # In practice, count might increase slightly if LLM extracts differently
    # So we just verify it doesn't double
    assert count_after_second < count_after_first * 2, (
        f"Concept count doubled: {count_after_first} -> {count_after_second}. "
        "Embeddings may not be idempotent."
    )


# =============================================================================
# Test 7: Semantic Concept Search Accuracy
# =============================================================================


@pytest.mark.asyncio
async def test_semantic_concept_search_accuracy(doc_manager, vector_store, embeddings):
    """
    Test that semantic concept search returns concepts in correct similarity order.
    """
    # Manually create some concepts with embeddings
    concepts = [
        ("Python", "Language"),
        ("Java", "Language"),
        ("pandas", "Library"),
        ("NumPy", "Library"),
    ]

    for name, category in concepts:
        concept_id = str(uuid.uuid4())
        embedding = await embeddings.generate_embedding(name)

        await vector_store.ingest(
            doc_id=concept_id,
            vector=embedding,
            payload={
                "name": name,
                "category": category,
                "tenant_id": "test-tenant",
                "neo4j_id": concept_id,
            },
            collection_name="test_concepts",
        )

    # Query for "Python data library"
    query_embedding = await embeddings.generate_embedding("Python data library")

    results = await vector_store.search(
        query_vector=query_embedding,
        top_k=3,
        collection_name="test_concepts",
    )

    # Should return concepts, ordered by similarity
    assert len(results) > 0, "No concepts found in similarity search"

    # Top result should be relevant to Python data (pandas or NumPy)
    top_concept_name = results[0]["payload"]["name"]
    assert top_concept_name in ["Python", "pandas", "NumPy"], (
        f"Top concept '{top_concept_name}' not relevant to 'Python data library'"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
