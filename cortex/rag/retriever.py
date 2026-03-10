"""
Retriever for RAG.

Provides semantic search and retrieval capabilities.

Features:
- Semantic search (vector similarity)
- Hybrid search (vector + keyword)
- Metadata filtering
- Reranking support
- Result formatting

Usage:
    # Initialize
    from cortex.rag import EmbeddingService, VectorStore, Retriever

    embeddings = EmbeddingService(openai_api_key="sk-...")
    vector_store = VectorStore(url="http://localhost:6333")
    await embeddings.connect()
    await vector_store.connect()

    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
    )

    # Semantic search
    results = await retriever.search(
        query="What is Python?",
        top_k=5,
        score_threshold=0.7,
    )

    # With metadata filtering
    results = await retriever.search(
        query="Python tutorials",
        top_k=5,
        filter={"source": "docs", "category": "tutorial"},
    )

    # Hybrid search
    results = await retriever.hybrid_search(
        query="machine learning algorithms",
        top_k=10,
        alpha=0.7,  # 70% semantic, 30% keyword
    )

    # Use with Agent
    from cortex.orchestration import Agent, ModelConfig

    async def search_knowledge_base(query: str, top_k: int = 3) -> str:
        '''Search the knowledge base for relevant information.'''
        results = await retriever.search(query, top_k=top_k)
        return retriever.format_results(results)

    agent = Agent(
        name="rag-assistant",
        model=ModelConfig(model="gpt-4o"),
        tools=[search_knowledge_base],
    )
"""

import logging
from dataclasses import dataclass
from typing import Any

from cortex.rag.embeddings import EmbeddingService
from cortex.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """
    Search result from retriever.

    Attributes:
        id: Document ID
        content: Document text content
        score: Similarity score (0.0 to 1.0)
        metadata: Document metadata
    """

    id: str
    content: str
    score: float
    metadata: dict[str, Any]

    def __repr__(self) -> str:
        content_preview = self.content[:100] + "..." if len(self.content) > 100 else self.content
        return f"SearchResult(id={self.id!r}, score={self.score:.3f}, content={content_preview!r})"


class Retriever:
    """
    Retriever for semantic search and RAG.

    Combines embedding service and vector store for retrieval.
    """

    def __init__(
        self,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
    ):
        """
        Initialize retriever.

        Args:
            embeddings: Embedding service
            vector_store: Vector store

        Example:
            >>> retriever = Retriever(
            ...     embeddings=embeddings,
            ...     vector_store=vector_store,
            ... )
        """
        self.embeddings = embeddings
        self.vector_store = vector_store

        logger.info("Retriever initialized")

    async def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float | None = None,
        filter: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> list[SearchResult]:
        """
        Semantic search for similar documents.

        Args:
            query: Search query text
            top_k: Number of results to return
            score_threshold: Minimum similarity score (0.0 to 1.0)
            filter: Metadata filter conditions
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            list[SearchResult]: Search results sorted by relevance

        Example:
            >>> results = await retriever.search(
            ...     query="What is Python?",
            ...     top_k=5,
            ...     score_threshold=0.7,
            ...     filter={"source": "docs"},
            ... )
            >>> for result in results:
            ...     print(f"{result.score:.3f} - {result.content[:100]}")
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")

        # Generate query embedding
        query_embedding = await self.embeddings.generate_embedding(query)

        # Add tenant_id to filter if provided
        if tenant_id:
            filter = filter or {}
            filter["tenant_id"] = tenant_id

        # Search vector store
        raw_results = await self.vector_store.search(
            query_vector=query_embedding,
            top_k=top_k,
            score_threshold=score_threshold,
            filter=filter,
        )

        # Convert to SearchResult objects
        results = [
            SearchResult(
                id=r["id"],
                content=r["payload"].get("content", ""),
                score=r["score"],
                metadata={
                    k: v
                    for k, v in r["payload"].items()
                    if k not in ["content", "doc_id", "chunk_index", "total_chunks"]
                },
            )
            for r in raw_results
        ]

        logger.info(f"Search for '{query[:50]}...' returned {len(results)} results")
        return results

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        alpha: float = 0.7,
        filter: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> list[SearchResult]:
        """
        Hybrid search combining semantic and keyword search.

        Args:
            query: Search query text
            top_k: Number of results to return
            alpha: Weight for semantic search (0.0 = keyword only, 1.0 = semantic only)
            filter: Metadata filter conditions
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            list[SearchResult]: Search results sorted by combined relevance

        Example:
            >>> results = await retriever.hybrid_search(
            ...     query="machine learning algorithms",
            ...     top_k=10,
            ...     alpha=0.7,  # 70% semantic, 30% keyword
            ... )
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")

        # Generate query embedding
        query_embedding = await self.embeddings.generate_embedding(query)

        # Generate sparse vector (simple BM25-like approach)
        # In production, use a proper BM25 implementation
        # For now, use a simple word-based approach
        sparse_vector = self._generate_sparse_vector(query)

        # Add tenant_id to filter if provided
        if tenant_id:
            filter = filter or {}
            filter["tenant_id"] = tenant_id

        # Hybrid search
        raw_results = await self.vector_store.hybrid_search(
            query_vector=query_embedding,
            sparse_vector=sparse_vector,
            top_k=top_k,
            alpha=alpha,
            filter=filter,
        )

        # Convert to SearchResult objects
        results = [
            SearchResult(
                id=r["id"],
                content=r["payload"].get("content", ""),
                score=r["score"],
                metadata={
                    k: v
                    for k, v in r["payload"].items()
                    if k not in ["content", "doc_id", "chunk_index", "total_chunks"]
                },
            )
            for r in raw_results
        ]

        logger.info(
            f"Hybrid search for '{query[:50]}...' (alpha={alpha}) "
            f"returned {len(results)} results"
        )
        return results

    def _generate_sparse_vector(self, query: str) -> dict[str, Any]:
        """
        Generate sparse vector for keyword search.

        Simple implementation using word frequency.
        Production systems should use proper BM25 implementation.

        Args:
            query: Query text

        Returns:
            dict: Sparse vector with indices and values
        """
        # Tokenize and count words
        words = query.lower().split()
        word_counts: dict[str, int] = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1

        # Convert to sparse vector format
        # Note: This is a simplified approach
        # Production should use proper vocabulary and BM25 scoring
        indices = list(range(len(word_counts)))
        values = [float(count) / len(words) for count in word_counts.values()]

        return {"indices": indices, "values": values}

    async def find_similar(
        self,
        doc_id: str,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Find documents similar to a given document.

        Args:
            doc_id: Document ID to find similar documents for
            top_k: Number of results to return
            filter: Metadata filter conditions

        Returns:
            list[SearchResult]: Similar documents

        Example:
            >>> similar = await retriever.find_similar(
            ...     doc_id="doc-1",
            ...     top_k=5,
            ... )
        """
        # Get the document
        doc = await self.vector_store.get_by_id(doc_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        # Use its vector for search
        raw_results = await self.vector_store.search(
            query_vector=doc["vector"]["dense"],  # Assuming dense vector
            top_k=top_k + 1,  # +1 to account for the document itself
            filter=filter,
        )

        # Remove the document itself from results
        results = [
            SearchResult(
                id=r["id"],
                content=r["payload"].get("content", ""),
                score=r["score"],
                metadata={
                    k: v
                    for k, v in r["payload"].items()
                    if k not in ["content", "doc_id", "chunk_index", "total_chunks"]
                },
            )
            for r in raw_results
            if r["id"] != doc_id
        ][:top_k]

        logger.info(f"Found {len(results)} similar documents to {doc_id}")
        return results

    def format_results(
        self,
        results: list[SearchResult],
        include_metadata: bool = False,
        include_scores: bool = False,
        separator: str = "\n\n---\n\n",
    ) -> str:
        """
        Format search results as text.

        Useful for providing context to LLM agents.

        Args:
            results: Search results to format
            include_metadata: Include metadata in output
            include_scores: Include relevance scores
            separator: Separator between results

        Returns:
            str: Formatted results

        Example:
            >>> results = await retriever.search("Python", top_k=3)
            >>> formatted = retriever.format_results(results, include_scores=True)
            >>> print(formatted)
        """
        if not results:
            return "No results found."

        formatted_parts = []
        for i, result in enumerate(results, 1):
            parts = []

            # Add header
            if include_scores:
                parts.append(f"Result {i} (score: {result.score:.3f}):")
            else:
                parts.append(f"Result {i}:")

            # Add content
            parts.append(result.content)

            # Add metadata
            if include_metadata and result.metadata:
                metadata_str = ", ".join(
                    f"{k}={v}" for k, v in result.metadata.items()
                )
                parts.append(f"Metadata: {metadata_str}")

            formatted_parts.append("\n".join(parts))

        return separator.join(formatted_parts)

    def format_context(
        self,
        results: list[SearchResult],
        max_tokens: int | None = None,
    ) -> str:
        """
        Format results as context for LLM.

        Optimized for token efficiency.

        Args:
            results: Search results
            max_tokens: Maximum tokens to include (approximate)

        Returns:
            str: Formatted context

        Example:
            >>> results = await retriever.search("Python", top_k=5)
            >>> context = retriever.format_context(results, max_tokens=1000)
            >>> # Use in agent prompt
            >>> prompt = f"Context:\\n{context}\\n\\nQuestion: {question}"
        """
        if not results:
            return ""

        # Simple concatenation with numbering
        parts = []
        total_chars = 0
        max_chars = max_tokens * 4 if max_tokens else None  # ~4 chars per token

        for i, result in enumerate(results, 1):
            part = f"[{i}] {result.content}"

            if max_chars and (total_chars + len(part)) > max_chars:
                # Truncate if exceeds limit
                remaining = max_chars - total_chars
                if remaining > 50:  # Only add if meaningful
                    part = part[:remaining] + "..."
                    parts.append(part)
                break

            parts.append(part)
            total_chars += len(part)

        return "\n\n".join(parts)

    async def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """
        Rerank results using LLM.

        Note: This is a placeholder for reranking functionality.
        Production implementations might use:
        - Cross-encoder models (e.g., Cohere Rerank, BGE Reranker)
        - LLM-based reranking
        - Custom scoring models

        Args:
            query: Original query
            results: Results to rerank
            top_k: Number of results to return after reranking

        Returns:
            list[SearchResult]: Reranked results

        Example:
            >>> results = await retriever.search("Python", top_k=20)
            >>> reranked = await retriever.rerank("Python tutorials", results, top_k=5)
        """
        # Placeholder - return as-is
        # In production, implement proper reranking
        logger.warning("Reranking not implemented - returning original results")

        if top_k:
            return results[:top_k]
        return results
