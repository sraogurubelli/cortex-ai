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
    """
    id: str = Field(..., description="Concept ID (UUID)")
    name: str = Field(..., description="Concept name (e.g., 'GraphRAG', 'Neo4j')")
    category: str = Field(..., description="Concept category (e.g., 'technology', 'methodology')")
    tenant_id: str = Field(..., description="Tenant ID for multi-tenancy")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "concept-456",
                "name": "GraphRAG",
                "category": "methodology",
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
    Result of entity extraction from text.

    Contains extracted concepts and relationships for graph insertion.
    """
    concepts: list[dict[str, str]] = Field(default_factory=list, description="Extracted concepts")
    relationships: list[dict[str, Any]] = Field(default_factory=list, description="Extracted relationships")

    class Config:
        json_schema_extra = {
            "example": {
                "concepts": [
                    {"name": "GraphRAG", "category": "methodology"},
                    {"name": "Neo4j", "category": "technology"}
                ],
                "relationships": [
                    {"source": "GraphRAG", "target": "Neo4j", "type": "USES", "strength": 0.9}
                ]
            }
        }
