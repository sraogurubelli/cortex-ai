"""
Document Manager for RAG.

Manages document lifecycle: ingestion, updates, and deletion.

Features:
- Single and batch document ingestion
- Automatic embedding generation
- Document updates with re-embedding
- Metadata management
- Chunking support for long documents

Usage:
    # Initialize
    from cortex.rag import EmbeddingService, VectorStore, DocumentManager

    embeddings = EmbeddingService(openai_api_key="sk-...")
    vector_store = VectorStore(url="http://localhost:6333")
    await embeddings.connect()
    await vector_store.connect()

    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
    )

    # Ingest single document
    await doc_manager.ingest_document(
        doc_id="doc-1",
        content="Python is a programming language...",
        metadata={"source": "docs", "author": "Alice"},
    )

    # Ingest batch
    await doc_manager.ingest_batch([
        {"doc_id": "doc-1", "content": "...", "metadata": {...}},
        {"doc_id": "doc-2", "content": "...", "metadata": {...}},
    ])

    # Update document
    await doc_manager.update_document(
        doc_id="doc-1",
        content="Updated content...",
    )

    # Delete document
    await doc_manager.delete_document("doc-1")
"""

import logging
from typing import Any

from cortex.rag.embeddings import EmbeddingService
from cortex.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class DocumentManager:
    """
    Manages document lifecycle for RAG.

    Handles ingestion, updates, and deletion with automatic embedding generation.
    """

    def __init__(
        self,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        """
        Initialize document manager.

        Args:
            embeddings: Embedding service
            vector_store: Vector store
            chunk_size: Maximum characters per chunk (optional, for long documents)
            chunk_overlap: Overlap between chunks (optional)

        Example:
            >>> doc_manager = DocumentManager(
            ...     embeddings=embeddings,
            ...     vector_store=vector_store,
            ...     chunk_size=2000,  # Split long documents
            ...     chunk_overlap=200,
            ... )
        """
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        logger.info("Document manager initialized")

    def _chunk_text(self, text: str) -> list[str]:
        """
        Chunk text into smaller pieces.

        Args:
            text: Text to chunk

        Returns:
            list[str]: List of text chunks

        Note:
            Simple character-based chunking. For production, consider:
            - Sentence-aware chunking
            - Paragraph-aware chunking
            - Token-based chunking
        """
        if not self.chunk_size:
            return [text]

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)

            if end >= text_len:
                break

            # Move start forward with overlap
            if self.chunk_overlap:
                start = end - self.chunk_overlap
            else:
                start = end

        logger.debug(f"Chunked text into {len(chunks)} pieces")
        return chunks

    async def ingest_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> int:
        """
        Ingest a document into the RAG system.

        Generates embeddings and stores in vector database.
        For long documents, splits into chunks and ingests separately.

        Args:
            doc_id: Unique document ID
            content: Document text content
            metadata: Optional metadata (source, author, etc.)
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            int: Number of chunks ingested (1 for non-chunked documents)

        Example:
            >>> num_chunks = await doc_manager.ingest_document(
            ...     doc_id="doc-1",
            ...     content="Python is a high-level programming language...",
            ...     metadata={"source": "wikipedia", "category": "programming"},
            ...     tenant_id="user-123",
            ... )
            >>> print(f"Ingested {num_chunks} chunks")
        """
        if not content.strip():
            raise ValueError("Document content cannot be empty")

        metadata = metadata or {}
        if tenant_id:
            metadata["tenant_id"] = tenant_id

        # Chunk text if needed
        chunks = self._chunk_text(content)

        # Generate embeddings for all chunks
        embeddings = await self.embeddings.generate_embeddings(chunks)

        # Ingest each chunk
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{doc_id}:{i}" if len(chunks) > 1 else doc_id

            payload = {
                "content": chunk,
                "doc_id": doc_id,
                "chunk_index": i,
                "total_chunks": len(chunks),
                **metadata,
            }

            await self.vector_store.ingest(
                doc_id=chunk_id,
                vector=embedding,
                payload=payload,
            )

        logger.info(f"Ingested document {doc_id} ({len(chunks)} chunks)")
        return len(chunks)

    async def ingest_batch(
        self,
        documents: list[dict[str, Any]],
        tenant_id: str | None = None,
    ) -> int:
        """
        Ingest multiple documents in batch.

        More efficient than calling ingest_document repeatedly.

        Args:
            documents: List of documents, each with:
                      - doc_id: str
                      - content: str
                      - metadata: dict (optional)
            tenant_id: Optional tenant ID for all documents

        Returns:
            int: Total number of chunks ingested

        Example:
            >>> total_chunks = await doc_manager.ingest_batch([
            ...     {
            ...         "doc_id": "doc-1",
            ...         "content": "Python is...",
            ...         "metadata": {"source": "wikipedia"},
            ...     },
            ...     {
            ...         "doc_id": "doc-2",
            ...         "content": "Java is...",
            ...         "metadata": {"source": "wikipedia"},
            ...     },
            ... ])
        """
        if not documents:
            return 0

        all_points = []
        total_chunks = 0

        for doc in documents:
            doc_id = doc["doc_id"]
            content = doc["content"]
            metadata = doc.get("metadata", {})

            if tenant_id:
                metadata["tenant_id"] = tenant_id

            # Chunk text
            chunks = self._chunk_text(content)
            total_chunks += len(chunks)

            # Generate embeddings for this document
            embeddings = await self.embeddings.generate_embeddings(chunks)

            # Create points
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_id = f"{doc_id}:{i}" if len(chunks) > 1 else doc_id

                payload = {
                    "content": chunk,
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    **metadata,
                }

                all_points.append(
                    {
                        "doc_id": chunk_id,
                        "vector": embedding,
                        "payload": payload,
                    }
                )

        # Batch ingest all points
        await self.vector_store.ingest_batch(all_points)

        logger.info(
            f"Ingested {len(documents)} documents "
            f"({total_chunks} total chunks) in batch"
        )
        return total_chunks

    async def update_document(
        self,
        doc_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """
        Update a document.

        Re-generates embeddings if content changed.

        Args:
            doc_id: Document ID to update
            content: New content (optional, re-embeds if provided)
            metadata: New metadata (optional, merges with existing)

        Returns:
            int: Number of chunks updated

        Example:
            >>> num_chunks = await doc_manager.update_document(
            ...     doc_id="doc-1",
            ...     content="Updated content...",
            ...     metadata={"updated_at": "2024-01-01"},
            ... )
        """
        if content is None and metadata is None:
            raise ValueError("Must provide content or metadata to update")

        # If only updating metadata, keep existing content
        if content is None:
            # Retrieve existing document
            existing = await self.vector_store.get_by_id(doc_id)
            if not existing:
                raise ValueError(f"Document {doc_id} not found")

            # Update metadata only
            updated_payload = {**existing["payload"], **(metadata or {})}
            await self.vector_store.ingest(
                doc_id=doc_id,
                vector=existing["vector"],
                payload=updated_payload,
            )
            logger.info(f"Updated metadata for document {doc_id}")
            return 1

        # Content changed - delete old chunks and re-ingest
        # First, delete all chunks for this document
        # Note: This is a simplified approach. Production systems might want to:
        # - Track chunks in a separate table
        # - Use a delete_by_filter operation if available
        # For now, we'll re-ingest with the same doc_id

        chunks_ingested = await self.ingest_document(
            doc_id=doc_id,
            content=content,
            metadata=metadata,
        )

        logger.info(f"Updated document {doc_id} (re-ingested {chunks_ingested} chunks)")
        return chunks_ingested

    async def delete_document(self, doc_id: str) -> None:
        """
        Delete a document and all its chunks.

        Args:
            doc_id: Document ID to delete

        Example:
            >>> await doc_manager.delete_document("doc-1")
        """
        # Delete main document
        await self.vector_store.delete(doc_id)

        # Delete chunks (doc_id:0, doc_id:1, etc.)
        # Note: Simplified approach - assumes max 100 chunks
        # Production systems should track chunks or use filter-based deletion
        for i in range(100):
            chunk_id = f"{doc_id}:{i}"
            try:
                await self.vector_store.delete(chunk_id)
            except Exception:
                # Chunk doesn't exist, stop trying
                break

        logger.info(f"Deleted document {doc_id}")

    async def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """
        Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            dict | None: Document with id, content, and metadata

        Example:
            >>> doc = await doc_manager.get_document("doc-1")
            >>> if doc:
            ...     print(doc["content"])
        """
        result = await self.vector_store.get_by_id(doc_id)
        if not result:
            return None

        return {
            "id": result["id"],
            "content": result["payload"].get("content", ""),
            "metadata": {
                k: v
                for k, v in result["payload"].items()
                if k not in ["content", "doc_id", "chunk_index", "total_chunks"]
            },
        }

    async def list_documents(
        self,
        limit: int = 100,
        offset: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        List documents with pagination.

        Args:
            limit: Number of documents per page
            offset: Pagination offset
            filter: Optional filter conditions

        Returns:
            tuple: (documents, next_offset)

        Example:
            >>> docs, next_offset = await doc_manager.list_documents(limit=10)
            >>> for doc in docs:
            ...     print(doc["id"], doc["metadata"])
        """
        documents, next_offset = await self.vector_store.scroll(
            limit=limit,
            offset=offset,
            filter=filter,
        )

        # Convert to document format
        result = [
            {
                "id": doc["id"],
                "content": doc["payload"].get("content", ""),
                "metadata": {
                    k: v
                    for k, v in doc["payload"].items()
                    if k not in ["content", "doc_id", "chunk_index", "total_chunks"]
                },
            }
            for doc in documents
        ]

        return result, next_offset

    async def count_documents(self, filter: dict[str, Any] | None = None) -> int:
        """
        Count documents.

        Args:
            filter: Optional filter conditions

        Returns:
            int: Number of documents

        Example:
            >>> total = await doc_manager.count_documents()
            >>> by_source = await doc_manager.count_documents(
            ...     filter={"source": "wikipedia"}
            ... )
        """
        return await self.vector_store.count(filter=filter)
