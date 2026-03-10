"""
Unit tests for EntityExtractor (LLM-based entity extraction).

Tests entity extraction from text using the Agent core.
"""

import os
import pytest

from cortex.rag.graph.entity_extractor import EntityExtractor
from cortex.orchestration import ModelConfig


@pytest.fixture
def extractor():
    """Create an EntityExtractor instance for testing."""
    # Use gpt-4o-mini for faster, cheaper tests
    return EntityExtractor(
        model=ModelConfig(
            model="gpt-4o-mini",
            temperature=0.0,
        )
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_extract_basic(extractor):
    """Test basic entity extraction from simple text."""
    text = "GraphRAG uses Neo4j for building knowledge graphs with Python."

    result = await extractor.extract(text)

    # Verify structure
    assert hasattr(result, "concepts")
    assert hasattr(result, "relationships")
    assert isinstance(result.concepts, list)
    assert isinstance(result.relationships, list)

    # Verify concepts extracted
    assert len(result.concepts) > 0

    # Check for expected concepts (may vary based on LLM)
    concept_names = [c.get("name", "").lower() for c in result.concepts]
    assert any("graphrag" in name for name in concept_names)
    assert any("neo4j" in name for name in concept_names)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_extract_with_relationships(extractor):
    """Test that relationships are extracted between concepts."""
    text = """GraphRAG is a methodology that uses Neo4j for graph storage.
    It implements RAG patterns using Python and LangGraph for orchestration."""

    result = await extractor.extract(text)

    # Should extract relationships
    assert len(result.relationships) > 0

    # Verify relationship structure
    for rel in result.relationships:
        assert "source" in rel
        assert "target" in rel
        assert "type" in rel or "relationship" in rel
        assert "strength" in rel


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_extract_concept_categories(extractor):
    """Test that concepts are categorized correctly."""
    text = "Python is a programming language used with Neo4j database for GraphRAG methodology."

    result = await extractor.extract(text)

    # Verify concepts have categories
    for concept in result.concepts:
        assert "category" in concept
        assert isinstance(concept["category"], str)
        assert len(concept["category"]) > 0


@pytest.mark.asyncio
async def test_extract_empty_text(extractor):
    """Test that empty text raises ValueError."""
    with pytest.raises(ValueError, match="Text cannot be empty"):
        await extractor.extract("")

    with pytest.raises(ValueError, match="Text cannot be empty"):
        await extractor.extract("   ")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_extract_long_text_truncation(extractor):
    """Test that very long text is truncated."""
    # Create text longer than 15000 chars
    long_text = "GraphRAG uses Neo4j. " * 1000  # ~21000 chars

    # Should not raise error, will truncate
    result = await extractor.extract(long_text)

    # Should still extract concepts
    assert len(result.concepts) > 0


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_extract_with_fallback(extractor):
    """Test extract_with_fallback returns empty on error."""
    # Test with valid text first
    result = await extractor.extract_with_fallback(
        "GraphRAG uses Neo4j",
        fallback_to_empty=True,
    )
    assert len(result.concepts) > 0

    # Test with empty text (should return empty result, not raise)
    result_empty = await extractor.extract_with_fallback(
        "",
        fallback_to_empty=True,
    )
    assert result_empty.concepts == []
    assert result_empty.relationships == []


@pytest.mark.asyncio
async def test_extract_with_fallback_no_fallback(extractor):
    """Test extract_with_fallback raises when fallback disabled."""
    with pytest.raises(ValueError):
        await extractor.extract_with_fallback(
            "",
            fallback_to_empty=False,
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_extract_domain_specific_concepts(extractor):
    """Test extraction focuses on domain-specific concepts."""
    text = """Neo4j is a graph database that stores data in nodes and relationships.
    It uses Cypher query language for querying graphs. Many developers use Neo4j
    for building knowledge graphs in AI applications."""

    result = await extractor.extract(text)

    # Should extract specific concepts, not generic ones
    concept_names = [c.get("name", "").lower() for c in result.concepts]

    # Should include specific terms
    assert any("neo4j" in name for name in concept_names)
    assert any("cypher" in name for name in concept_names)

    # Should avoid generic terms (though LLM may vary)
    generic_count = sum(
        1 for name in concept_names
        if name in ["data", "system", "information", "thing"]
    )
    # Most concepts should be specific
    assert generic_count < len(concept_names) / 2


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_extract_technical_document(extractor):
    """Test extraction from a realistic technical document."""
    text = """
    GraphRAG is an advanced methodology that enhances Retrieval-Augmented Generation
    by incorporating knowledge graphs. Unlike traditional RAG systems that rely solely
    on vector similarity search in databases like Qdrant, GraphRAG uses Neo4j to store
    entities and their relationships.

    The process involves:
    1. Extracting entities from documents using LLMs
    2. Storing entities as nodes in Neo4j
    3. Creating relationships between entities
    4. Querying the graph using Cypher alongside vector search

    This hybrid approach enables more context-aware retrieval by traversing relationship
    paths in the knowledge graph. Python is commonly used to implement GraphRAG systems,
    often with frameworks like LangGraph for orchestration.
    """

    result = await extractor.extract(text)

    # Should extract multiple concepts
    assert len(result.concepts) >= 5

    # Should extract relationships
    assert len(result.relationships) >= 2

    # Verify concept structure
    for concept in result.concepts:
        assert "name" in concept
        assert "category" in concept
        assert isinstance(concept["name"], str)
        assert len(concept["name"]) > 0

    # Verify relationship structure
    for rel in result.relationships:
        assert "source" in rel
        assert "target" in rel
        assert "strength" in rel
        assert 0.0 <= rel["strength"] <= 1.0
