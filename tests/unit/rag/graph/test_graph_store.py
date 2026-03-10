"""
Unit tests for GraphStore (Neo4j client).

Tests basic CRUD operations for the knowledge graph.
"""

import os
import uuid
import pytest
from datetime import datetime

from cortex.rag.graph.graph_store import GraphStore
from cortex.rag.graph.schema import Document, Concept


@pytest.fixture
async def graph_store():
    """Create and connect a GraphStore instance for testing."""
    store = GraphStore(
        url=os.getenv("CORTEX_NEO4J_URL", "bolt://localhost:7687"),
        user=os.getenv("CORTEX_NEO4J_USER", "neo4j"),
        password=os.getenv("CORTEX_NEO4J_PASSWORD", "cortex_neo4j_password"),
    )
    await store.connect()
    await store.create_constraints()

    yield store

    # Cleanup: delete all test data
    if store.driver:
        async with store.driver.session() as session:
            await session.run("MATCH (n) WHERE n.tenant_id = 'test-tenant' DETACH DELETE n")

    await store.disconnect()


@pytest.mark.asyncio
async def test_graph_store_connection(graph_store):
    """Test that GraphStore can connect to Neo4j."""
    assert graph_store._connected is True
    assert graph_store.driver is not None

    # Health check
    health = await graph_store.health_check()
    assert health is True


@pytest.mark.asyncio
async def test_add_document(graph_store):
    """Test adding a document to the graph."""
    doc_id = f"test-doc-{uuid.uuid4()}"

    result_id = await graph_store.add_document(
        doc_id=doc_id,
        content="Test content for GraphRAG",
        tenant_id="test-tenant",
    )

    assert result_id == doc_id

    # Verify document exists
    doc = await graph_store.get_document(doc_id)
    assert doc is not None
    assert doc.id == doc_id
    assert doc.content == "Test content for GraphRAG"
    assert doc.tenant_id == "test-tenant"


@pytest.mark.asyncio
async def test_add_concept(graph_store):
    """Test adding a concept to the graph."""
    concept_id = await graph_store.add_concept(
        name="GraphRAG",
        category="methodology",
        tenant_id="test-tenant",
    )

    assert concept_id is not None
    assert isinstance(concept_id, str)


@pytest.mark.asyncio
async def test_add_concept_duplicate(graph_store):
    """Test that adding duplicate concept returns same ID (MERGE behavior)."""
    # Add concept first time
    concept_id_1 = await graph_store.add_concept(
        name="Neo4j",
        category="technology",
        tenant_id="test-tenant",
    )

    # Add same concept again
    concept_id_2 = await graph_store.add_concept(
        name="Neo4j",
        category="technology",
        tenant_id="test-tenant",
    )

    # Should return the same concept ID
    assert concept_id_1 == concept_id_2


@pytest.mark.asyncio
async def test_add_relationship(graph_store):
    """Test adding a relationship between nodes."""
    # Create document
    doc_id = f"test-doc-{uuid.uuid4()}"
    await graph_store.add_document(
        doc_id=doc_id,
        content="GraphRAG uses Neo4j",
        tenant_id="test-tenant",
    )

    # Create concept
    concept_id = await graph_store.add_concept(
        name="GraphRAG",
        category="methodology",
        tenant_id="test-tenant",
    )

    # Add MENTIONS relationship
    await graph_store.add_relationship(
        source_id=doc_id,
        target_id=concept_id,
        rel_type="MENTIONS",
        properties={"count": 1, "confidence": 0.9},
    )

    # Verify relationship exists
    concepts = await graph_store.get_document_concepts(doc_id)
    assert len(concepts) == 1
    assert concepts[0].name == "GraphRAG"


@pytest.mark.asyncio
async def test_get_document_concepts(graph_store):
    """Test retrieving concepts mentioned by a document."""
    # Create document
    doc_id = f"test-doc-{uuid.uuid4()}"
    await graph_store.add_document(
        doc_id=doc_id,
        content="GraphRAG uses Neo4j and Python",
        tenant_id="test-tenant",
    )

    # Create concepts
    concept_1 = await graph_store.add_concept(
        name="GraphRAG",
        category="methodology",
        tenant_id="test-tenant",
    )
    concept_2 = await graph_store.add_concept(
        name="Neo4j",
        category="technology",
        tenant_id="test-tenant",
    )
    concept_3 = await graph_store.add_concept(
        name="Python",
        category="language",
        tenant_id="test-tenant",
    )

    # Add MENTIONS relationships
    for concept_id in [concept_1, concept_2, concept_3]:
        await graph_store.add_relationship(
            source_id=doc_id,
            target_id=concept_id,
            rel_type="MENTIONS",
            properties={"count": 1},
        )

    # Get concepts
    concepts = await graph_store.get_document_concepts(doc_id)
    assert len(concepts) == 3

    concept_names = {c.name for c in concepts}
    assert concept_names == {"GraphRAG", "Neo4j", "Python"}


@pytest.mark.asyncio
async def test_get_document_concepts_with_tenant_filter(graph_store):
    """Test that tenant filtering works for concepts."""
    # Create document
    doc_id = f"test-doc-{uuid.uuid4()}"
    await graph_store.add_document(
        doc_id=doc_id,
        content="Test",
        tenant_id="test-tenant",
    )

    # Create concept in same tenant
    concept_1 = await graph_store.add_concept(
        name="Concept1",
        category="test",
        tenant_id="test-tenant",
    )
    await graph_store.add_relationship(
        source_id=doc_id,
        target_id=concept_1,
        rel_type="MENTIONS",
    )

    # Create concept in different tenant
    concept_2 = await graph_store.add_concept(
        name="Concept2",
        category="test",
        tenant_id="other-tenant",
    )
    await graph_store.add_relationship(
        source_id=doc_id,
        target_id=concept_2,
        rel_type="MENTIONS",
    )

    # Get concepts with tenant filter
    concepts = await graph_store.get_document_concepts(
        doc_id=doc_id,
        tenant_id="test-tenant",
    )

    # Should only return concept from same tenant
    assert len(concepts) == 1
    assert concepts[0].name == "Concept1"


@pytest.mark.asyncio
async def test_delete_document(graph_store):
    """Test deleting a document and its relationships."""
    # Create document
    doc_id = f"test-doc-{uuid.uuid4()}"
    await graph_store.add_document(
        doc_id=doc_id,
        content="Test",
        tenant_id="test-tenant",
    )

    # Delete document
    deleted = await graph_store.delete_document(doc_id)
    assert deleted is True

    # Verify document is gone
    doc = await graph_store.get_document(doc_id)
    assert doc is None

    # Try deleting again
    deleted_again = await graph_store.delete_document(doc_id)
    assert deleted_again is False


@pytest.mark.asyncio
async def test_get_document_not_found(graph_store):
    """Test getting a non-existent document."""
    doc = await graph_store.get_document("non-existent-doc")
    assert doc is None


@pytest.mark.asyncio
async def test_multi_tenancy_isolation(graph_store):
    """Test that tenant isolation works correctly."""
    # Create documents in different tenants
    doc_id_1 = f"test-doc-{uuid.uuid4()}"
    doc_id_2 = f"test-doc-{uuid.uuid4()}"

    await graph_store.add_document(
        doc_id=doc_id_1,
        content="Tenant 1 content",
        tenant_id="tenant-1",
    )
    await graph_store.add_document(
        doc_id=doc_id_2,
        content="Tenant 2 content",
        tenant_id="tenant-2",
    )

    # Create concept in tenant-1
    concept_id = await graph_store.add_concept(
        name="SharedConcept",
        category="test",
        tenant_id="tenant-1",
    )

    await graph_store.add_relationship(
        source_id=doc_id_1,
        target_id=concept_id,
        rel_type="MENTIONS",
    )

    # Get concepts for doc in tenant-1
    concepts_1 = await graph_store.get_document_concepts(
        doc_id=doc_id_1,
        tenant_id="tenant-1",
    )
    assert len(concepts_1) == 1

    # Get concepts for doc in tenant-2 (should be empty)
    concepts_2 = await graph_store.get_document_concepts(
        doc_id=doc_id_2,
        tenant_id="tenant-2",
    )
    assert len(concepts_2) == 0

    # Cleanup
    await graph_store.delete_document(doc_id_1)
    await graph_store.delete_document(doc_id_2)
