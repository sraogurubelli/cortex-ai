"""
Document entity.

Stores metadata about uploaded documents and tracks processing status
across storage layers (PostgreSQL, Qdrant, Neo4j, S3/filesystem).
"""

from sqlalchemy import Column, String, Integer, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..base import MinimalEntity


class Document(MinimalEntity):
    """
    Document model for file metadata and processing status.

    Actual file content is stored in:
    - S3 or filesystem (file_url points to storage location)
    - Qdrant (chunked embeddings for RAG)
    - Neo4j (knowledge graph entities/concepts)

    This model tracks processing status across all three storage layers.
    """

    __tablename__ = "documents"

    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    # File metadata
    filename = Column(String(255), nullable=False)
    file_url = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    mime_type = Column(String(100), nullable=True)

    # Overall processing status
    status = Column(
        String(50), nullable=False, default="uploading", index=True
    )

    # RAG metadata (Qdrant vector store)
    qdrant_doc_id = Column(String(100), nullable=True, index=True)
    chunk_count = Column(Integer, nullable=False, default=0)
    embedding_status = Column(String(50), nullable=True)

    # GraphRAG metadata (Neo4j knowledge graph)
    neo4j_doc_id = Column(String(100), nullable=True, index=True)
    entity_count = Column(Integer, nullable=False, default=0)
    concept_count = Column(Integer, nullable=False, default=0)
    relationship_count = Column(Integer, nullable=False, default=0)
    graph_status = Column(String(50), nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="documents")

    __table_args__ = (
        Index("idx_documents_org_status", "organization_id", "status"),
        Index("idx_documents_org_created", "organization_id", "created_at"),
    )

    def __repr__(self):
        return (
            f"<Document(id={self.id}, filename={self.filename}, "
            f"status={self.status})>"
        )
