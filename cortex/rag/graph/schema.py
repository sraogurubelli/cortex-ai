"""
Graph schema definitions for GraphRAG.

Defines Pydantic models for nodes and relationships in the knowledge graph.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class Document(BaseModel):
    """
    Document node in knowledge graph.

    Represents an ingested document with its full content.
    """
    id: str = Field(..., description="Document ID (same as Qdrant doc_id)")
    content: str = Field(..., description="Full document text")
    tenant_id: str = Field(..., description="Tenant ID for multi-tenancy")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc-123",
                "content": "GraphRAG uses Neo4j for knowledge graphs.",
                "tenant_id": "tenant-1",
                "created_at": "2024-01-01T00:00:00Z"
            }
        }


class Concept(BaseModel):
    """
    Concept node in knowledge graph.

    Represents a topic, term, or theme extracted from documents.
    GNN-ready with embedding field for graph neural network applications.
    """
    id: str = Field(..., description="Concept ID (UUID)")
    name: str = Field(..., description="Concept name (e.g., 'GraphRAG', 'Neo4j')")
    category: str = Field(..., description="Concept category (e.g., 'technology', 'methodology')")
    embedding: list[float] | None = Field(None, description="Vector embedding for GNN (1536-dim)")
    tenant_id: str = Field(..., description="Tenant ID for multi-tenancy")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "concept-456",
                "name": "GraphRAG",
                "category": "methodology",
                "embedding": [0.1, 0.2, 0.3],
                "tenant_id": "tenant-1",
                "created_at": "2024-01-01T00:00:00Z"
            }
        }


class Entity(BaseModel):
    """
    Entity node in knowledge graph.

    Represents concrete things (people, companies, products, locations, events).
    GNN-ready with embedding field for graph neural network applications.
    """
    id: str = Field(..., description="Entity ID (UUID)")
    name: str = Field(..., description="Entity name (e.g., 'Alice Johnson', 'Acme Corp')")
    type: str = Field(..., description="Entity type: person, company, location, product, event")
    properties: dict[str, Any] = Field(default_factory=dict, description="Entity metadata")
    embedding: list[float] | None = Field(None, description="Vector embedding for GNN (1536-dim)")
    tenant_id: str = Field(..., description="Tenant ID for multi-tenancy")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "entity-789",
                "name": "Alice Johnson",
                "type": "person",
                "properties": {"title": "CEO", "email": "alice@acme.com"},
                "embedding": [0.1, 0.2, 0.3],
                "tenant_id": "tenant-1",
                "created_at": "2024-01-01T00:00:00Z"
            }
        }


class Relationship(BaseModel):
    """
    Relationship between nodes in knowledge graph.

    Represents connections between documents and concepts, or between concepts.
    """
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    type: str = Field(..., description="Relationship type (e.g., 'MENTIONS', 'RELATES_TO')")
    properties: dict[str, Any] = Field(default_factory=dict, description="Additional relationship properties")

    class Config:
        json_schema_extra = {
            "example": {
                "source_id": "doc-123",
                "target_id": "concept-456",
                "type": "MENTIONS",
                "properties": {"count": 3, "confidence": 0.95}
            }
        }


class EntityExtractionResult(BaseModel):
    """
    Result of entity and concept extraction from text.

    Contains extracted concepts (abstract ideas), entities (concrete things),
    and relationships for graph insertion.
    """
    concepts: list[dict[str, Any]] = Field(default_factory=list, description="Extracted concepts")
    entities: list[dict[str, Any]] = Field(default_factory=list, description="Extracted entities")
    relationships: list[dict[str, Any]] = Field(default_factory=list, description="Extracted relationships")

    class Config:
        json_schema_extra = {
            "example": {
                "concepts": [
                    {"name": "GraphRAG", "category": "methodology", "embedding": [0.1, 0.2]},
                    {"name": "Neo4j", "category": "technology", "embedding": [0.3, 0.4]}
                ],
                "entities": [
                    {"name": "Alice Johnson", "type": "person", "properties": {"title": "CEO"}, "embedding": [0.5, 0.6]},
                    {"name": "Acme Corp", "type": "company", "properties": {}, "embedding": [0.7, 0.8]}
                ],
                "relationships": [
                    {"source": "GraphRAG", "target": "Neo4j", "type": "USES", "properties": {"strength": 0.9}},
                    {"source": "Alice Johnson", "target": "Acme Corp", "type": "WORKS_AT", "properties": {}}
                ]
            }
        }
