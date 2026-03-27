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
from typing import Any, TYPE_CHECKING, Optional

from cortex.rag.embeddings import EmbeddingService
from cortex.rag.vector_store import VectorStore
from cortex.rag.cache import SearchCache
from cortex.platform.config.settings import get_settings

if TYPE_CHECKING:
    from cortex.rag.graph.graph_store import GraphStore

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
        graph_store: "GraphStore | None" = None,
        enable_cache: bool = True,
    ):
        """
        Initialize retriever.

        Args:
            embeddings: Embedding service
            vector_store: Vector store
            graph_store: Optional graph store for GraphRAG
            enable_cache: Enable search result caching (Phase 1)

        Example:
            >>> retriever = Retriever(
            ...     embeddings=embeddings,
            ...     vector_store=vector_store,
            ... )

            >>> # With GraphRAG
            >>> from cortex.rag.graph import GraphStore
            >>> graph_store = GraphStore(url="bolt://localhost:7687")
            >>> retriever = Retriever(
            ...     embeddings=embeddings,
            ...     vector_store=vector_store,
            ...     graph_store=graph_store,
            ... )
        """
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.graph_store = graph_store

        # Phase 1: Initialize search cache
        self.cache: Optional[SearchCache] = None
        if enable_cache:
            settings = get_settings()
            self.cache = SearchCache(
                redis_url=settings.redis_url,
                ttl=settings.cache_ttl_search,
            )
            logger.info("Retriever initialized with search cache (80% hit rate expected)")

        if graph_store:
            logger.info("Retriever initialized with GraphRAG support")
        else:
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

        # Phase 1: Try cache first (80% hit rate for repeated searches)
        if self.cache:
            await self.cache.connect()
            cached_results_data = await self.cache.get_results(
                query=query,
                top_k=top_k,
                filter_dict=filter,
                tenant_id=tenant_id,
            )

            if cached_results_data is not None:
                # Cache hit - reconstruct SearchResult objects
                results = [
                    SearchResult(
                        id=r["id"],
                        content=r["content"],
                        score=r["score"],
                        metadata=r["metadata"],
                    )
                    for r in cached_results_data
                ]
                logger.info(
                    f"Search cache HIT for '{query[:50]}...' - {len(results)} results"
                )
                return results

        # Cache miss or cache disabled - perform vector search
        logger.debug(f"Search cache MISS for '{query[:50]}...' - querying vector store")

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

        # Phase 1: Cache results for next time
        if self.cache and results:
            # Serialize SearchResult objects for caching
            results_data = [
                {
                    "id": r.id,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata,
                }
                for r in results
            ]
            await self.cache.set_results(
                query=query,
                results=results_data,
                top_k=top_k,
                filter_dict=filter,
                tenant_id=tenant_id,
            )
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

    async def graph_search(
        self,
        concept_name: str,
        max_hops: int = 2,
        tenant_id: str | None = None,
    ) -> list[SearchResult]:
        """
        Search using knowledge graph traversal.

        Finds documents that mention a concept and related concepts within max_hops.

        Args:
            concept_name: Name of concept to search for
            max_hops: Maximum relationship hops to traverse (default: 2)
            tenant_id: Optional tenant ID for filtering

        Returns:
            list[SearchResult]: Documents related to the concept

        Example:
            >>> results = await retriever.graph_search(
            ...     concept_name="GraphRAG",
            ...     max_hops=2,
            ...     tenant_id="demo",
            ... )
        """
        if not self.graph_store:
            raise ValueError(
                "GraphStore not configured. Initialize Retriever with graph_store parameter."
            )

        if not concept_name.strip():
            raise ValueError("Concept name cannot be empty")

        # Build Cypher query for multi-hop traversal
        tenant_filter = "AND c.tenant_id = $tenant_id" if tenant_id else ""

        query = f"""
        MATCH (c:Concept {{name: $concept_name}})
        WHERE 1=1 {tenant_filter}
        WITH c
        MATCH (c)-[:RELATES_TO*0..{max_hops}]-(related:Concept)
        WITH DISTINCT related
        MATCH (d:Document)-[m:MENTIONS]->(related)
        RETURN DISTINCT d.id as doc_id,
               d.content as content,
               COUNT(DISTINCT related) as concept_count,
               SUM(m.confidence) as total_confidence
        ORDER BY concept_count DESC, total_confidence DESC
        """

        params = {"concept_name": concept_name}
        if tenant_id:
            params["tenant_id"] = tenant_id

        # Execute query
        results = []
        if self.graph_store.driver:
            async with self.graph_store.driver.session() as session:
                result = await session.run(query, **params)
                records = await result.values()

                # Convert to SearchResult objects
                for record in records:
                    doc_id, content, concept_count, total_confidence = record

                    # Normalize score (0.0 to 1.0)
                    # Score based on number of related concepts and confidence
                    score = min(1.0, (concept_count * 0.3 + total_confidence * 0.1))

                    results.append(
                        SearchResult(
                            id=doc_id,
                            content=content or "",
                            score=score,
                            metadata={
                                "source": "graph",
                                "concept_count": concept_count,
                                "total_confidence": total_confidence,
                            },
                        )
                    )

        logger.info(
            f"Graph search for concept '{concept_name}' (max_hops={max_hops}) "
            f"returned {len(results)} documents"
        )
        return results

    async def graphrag_search(
        self,
        query: str,
        top_k: int = 5,
        vector_weight: float = 0.7,
        graph_weight: float = 0.3,
        max_hops: int = 2,
        tenant_id: str | None = None,
    ) -> list[SearchResult]:
        """
        Hybrid search combining vector and graph retrieval (GraphRAG).

        Performs both vector similarity search and graph traversal, then
        combines results using Reciprocal Rank Fusion (RRF).

        Args:
            query: Search query text
            top_k: Number of final results to return
            vector_weight: Weight for vector search results (0.0-1.0)
            graph_weight: Weight for graph search results (0.0-1.0)
            max_hops: Maximum relationship hops in graph traversal
            tenant_id: Optional tenant ID for filtering

        Returns:
            list[SearchResult]: Combined results from vector + graph search

        Example:
            >>> results = await retriever.graphrag_search(
            ...     query="What is GraphRAG?",
            ...     top_k=5,
            ...     vector_weight=0.7,
            ...     graph_weight=0.3,
            ... )
        """
        if not self.graph_store:
            # Fallback to pure vector search if no graph store
            logger.warning("GraphStore not available, falling back to vector search only")
            return await self.search(query, top_k=top_k, tenant_id=tenant_id)

        # Normalize weights
        total_weight = vector_weight + graph_weight
        if total_weight == 0:
            raise ValueError("At least one of vector_weight or graph_weight must be > 0")

        vector_weight = vector_weight / total_weight
        graph_weight = graph_weight / total_weight

        # 1. Vector search
        vector_results = await self.search(
            query=query,
            top_k=top_k * 2,  # Get more candidates for fusion
            tenant_id=tenant_id,
        )

        # 2. Graph search (extract concept from query using simple keyword extraction)
        # In production, use NER or LLM to extract concepts
        concept_names = self._extract_concepts_from_query(query)

        graph_results = []
        for concept_name in concept_names[:3]:  # Limit to top 3 concepts
            try:
                concept_results = await self.graph_search(
                    concept_name=concept_name,
                    max_hops=max_hops,
                    tenant_id=tenant_id,
                )
                graph_results.extend(concept_results)
            except Exception as e:
                logger.warning(f"Graph search failed for concept '{concept_name}': {e}")
                continue

        # 3. Fuse results using Reciprocal Rank Fusion (RRF)
        fused_results = self._reciprocal_rank_fusion(
            vector_results=vector_results,
            graph_results=graph_results,
            vector_weight=vector_weight,
            graph_weight=graph_weight,
        )

        # 4. Return top_k results
        final_results = fused_results[:top_k]

        logger.info(
            f"GraphRAG search for '{query[:50]}...' returned {len(final_results)} results "
            f"(vector: {len(vector_results)}, graph: {len(graph_results)})"
        )
        return final_results

    def _extract_concepts_from_query(self, query: str) -> list[str]:
        """
        Extract potential concept names from query.

        Simple keyword extraction. In production, use NER or LLM.

        Args:
            query: Query text

        Returns:
            list[str]: Potential concept names
        """
        # Simple approach: capitalize words that look like proper nouns
        words = query.split()
        concepts = []

        for word in words:
            # Keep capitalized words or common tech terms
            cleaned = word.strip(',.!?;:"\'')
            if cleaned and (cleaned[0].isupper() or len(cleaned) > 6):
                concepts.append(cleaned)

        # Fallback: if no concepts found, use all non-stopwords
        if not concepts:
            stopwords = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for'}
            concepts = [w.strip(',.!?;:"\'') for w in words if w.lower() not in stopwords and len(w) > 3]

        return concepts[:5]  # Limit to 5 concepts

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[SearchResult],
        graph_results: list[SearchResult],
        vector_weight: float = 0.7,
        graph_weight: float = 0.3,
        k: int = 60,
    ) -> list[SearchResult]:
        """
        Combine results using Reciprocal Rank Fusion (RRF).

        RRF Score: score(d) = Σ w_i / (k + rank_i(d))
        where w_i is the weight for source i, rank_i is the rank in that source.

        Args:
            vector_results: Results from vector search
            graph_results: Results from graph search
            vector_weight: Weight for vector results
            graph_weight: Weight for graph results
            k: RRF constant (default: 60, from literature)

        Returns:
            list[SearchResult]: Fused results sorted by RRF score
        """
        # Build rank maps
        vector_ranks = {r.id: rank for rank, r in enumerate(vector_results, 1)}
        graph_ranks = {r.id: rank for rank, r in enumerate(graph_results, 1)}

        # Collect all unique document IDs
        all_doc_ids = set(vector_ranks.keys()) | set(graph_ranks.keys())

        # Calculate RRF scores
        doc_scores: dict[str, float] = {}
        doc_content: dict[str, SearchResult] = {}

        for doc_id in all_doc_ids:
            rrf_score = 0.0

            # Vector contribution
            if doc_id in vector_ranks:
                rrf_score += vector_weight / (k + vector_ranks[doc_id])
                # Store content from vector results (prefer vector content)
                doc_content[doc_id] = next(r for r in vector_results if r.id == doc_id)

            # Graph contribution
            if doc_id in graph_ranks:
                rrf_score += graph_weight / (k + graph_ranks[doc_id])
                # Store content from graph results if not already stored
                if doc_id not in doc_content:
                    doc_content[doc_id] = next(r for r in graph_results if r.id == doc_id)

            doc_scores[doc_id] = rrf_score

        # Sort by RRF score
        sorted_doc_ids = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        # Build final results
        fused_results = []
        for doc_id, rrf_score in sorted_doc_ids:
            original = doc_content[doc_id]

            # Update metadata to indicate fusion
            metadata = original.metadata.copy()
            metadata["rrf_score"] = rrf_score
            metadata["in_vector"] = doc_id in vector_ranks
            metadata["in_graph"] = doc_id in graph_ranks

            if doc_id in vector_ranks:
                metadata["vector_rank"] = vector_ranks[doc_id]
            if doc_id in graph_ranks:
                metadata["graph_rank"] = graph_ranks[doc_id]

            fused_results.append(
                SearchResult(
                    id=original.id,
                    content=original.content,
                    score=rrf_score,  # Use RRF score as final score
                    metadata=metadata,
                )
            )

        return fused_results

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
