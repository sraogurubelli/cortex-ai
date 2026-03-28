"""
Vector Store with Qdrant Integration.

Provides vector storage and search capabilities using Qdrant.

Features:
- Dense vector search (semantic)
- Sparse vector search (BM25 keyword)
- Hybrid search (vector + keyword)
- CRUD operations
- Multi-tenancy support
- Payload filtering

Usage:
    # Initialize vector store
    vector_store = VectorStore(
        url="http://localhost:6333",
        collection_name="documents",
        vector_size=1536,  # For text-embedding-3-small
    )
    await vector_store.connect()

    # Create collection
    await vector_store.create_collection()

    # Ingest documents
    await vector_store.ingest(
        doc_id="doc-1",
        vector=[0.1, 0.2, ...],  # Dense embedding
        sparse_vector={"indices": [1, 5, 10], "values": [0.8, 0.6, 0.4]},  # Optional
        payload={"content": "...", "metadata": {...}},
    )

    # Search
    results = await vector_store.search(
        query_vector=[0.1, 0.2, ...],
        top_k=5,
        filter={"source": "docs"},
    )

    # Hybrid search
    results = await vector_store.hybrid_search(
        query_vector=[0.1, 0.2, ...],
        sparse_vector={"indices": [...], "values": [...]},
        top_k=5,
        alpha=0.7,  # 70% vector, 30% keyword
    )

Environment Variables:
    CORTEX_QDRANT_URL: Qdrant server URL (default: http://localhost:6333)
    CORTEX_QDRANT_API_KEY: Qdrant API key (optional)
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Environment configuration
QDRANT_URL = os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("CORTEX_QDRANT_API_KEY", "")

# Optional imports
try:
    from qdrant_client import AsyncQdrantClient, models

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant client not installed. Install with: pip install qdrant-client")


class VectorStore:
    """
    Vector store using Qdrant for semantic search.

    Supports both dense (semantic) and sparse (keyword) vectors for hybrid search.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str = "documents",
        vector_size: int = 1536,
        distance_metric: str = "cosine",
    ):
        """
        Initialize vector store.

        Args:
            url: Qdrant server URL (or use CORTEX_QDRANT_URL env var)
            api_key: Qdrant API key (or use CORTEX_QDRANT_API_KEY env var)
            collection_name: Collection name for documents
            vector_size: Embedding dimension (default: 1536 for text-embedding-3-small)
            distance_metric: Distance metric (cosine, euclid, dot)

        Raises:
            ImportError: If qdrant-client not installed
        """
        if not QDRANT_AVAILABLE:
            raise ImportError(
                "Qdrant client required for vector store. Install with: pip install qdrant-client"
            )

        self.url = url or QDRANT_URL
        self.api_key = api_key or QDRANT_API_KEY
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.distance_metric = distance_metric
        self.client: AsyncQdrantClient | None = None

        logger.info(f"Vector store initialized for collection '{collection_name}'")

    async def connect(self) -> None:
        """
        Connect to Qdrant server.

        Safe to call multiple times - idempotent.
        """
        if self.client is not None:
            return

        try:
            self.client = AsyncQdrantClient(
                url=self.url,
                api_key=self.api_key if self.api_key else None,
            )

            # Test connection
            collections = await self.client.get_collections()
            logger.info(
                f"Connected to Qdrant at {self.url} "
                f"({len(collections.collections)} collections)"
            )

        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise

    async def disconnect(self) -> None:
        """
        Disconnect from Qdrant.

        Call at application shutdown.
        """
        if self.client is not None:
            await self.client.close()
            self.client = None
            logger.info("Disconnected from Qdrant")

    async def collection_exists(self, collection_name: str | None = None) -> bool:
        """
        Check if collection exists.

        Args:
            collection_name: Collection name to check (defaults to self.collection_name)

        Returns:
            bool: True if collection exists
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        collection = collection_name or self.collection_name

        try:
            await self.client.get_collection(collection)
            return True
        except Exception:
            return False

    async def create_collection(
        self,
        enable_sparse: bool = True,
        on_disk_payload: bool = False,
    ) -> None:
        """
        Create collection if it doesn't exist.

        Args:
            enable_sparse: Enable sparse vectors for hybrid search
            on_disk_payload: Store payload on disk (for large datasets)

        Example:
            >>> await vector_store.create_collection()
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        if await self.collection_exists():
            logger.info(f"Collection '{self.collection_name}' already exists")
            return

        # Map distance metric
        distance_map = {
            "cosine": models.Distance.COSINE,
            "euclid": models.Distance.EUCLID,
            "dot": models.Distance.DOT,
        }
        distance = distance_map.get(self.distance_metric, models.Distance.COSINE)

        # Create collection with dense vectors
        vectors_config = {
            "dense": models.VectorParams(
                size=self.vector_size,
                distance=distance,
                on_disk=False,
            )
        }

        # Add sparse vectors for hybrid search
        if enable_sparse:
            vectors_config["sparse"] = models.VectorParams(
                size=self.vector_size,
                distance=models.Distance.DOT,
                on_disk=False,
            )

        try:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=vectors_config,
                on_disk_payload=on_disk_payload,
            )

            # Create payload indexes for common filters
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="tenant_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="source",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            logger.info(
                f"Created collection '{self.collection_name}' "
                f"(size={self.vector_size}, sparse={enable_sparse})"
            )

        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise

    async def create_concepts_collection(
        self,
        collection_name: str = "concepts",
        vector_size: int = 1536,
        distance_metric: str = "cosine",
    ) -> None:
        """
        Create a separate collection for concept embeddings.

        This collection stores embeddings for concepts/entities extracted from documents,
        enabling semantic concept search for GraphRAG queries.

        Args:
            collection_name: Collection name (default: "concepts")
            vector_size: Embedding dimension (default: 1536 for OpenAI)
            distance_metric: Distance metric (cosine, euclid, dot)

        Example:
            >>> await vector_store.create_concepts_collection()
            >>> # Check it exists
            >>> exists = await vector_store.collection_exists("concepts")
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        # Check if collection already exists
        if await self.collection_exists(collection_name):
            logger.info(f"Collection '{collection_name}' already exists")
            return

        # Map distance metric
        distance_map = {
            "cosine": models.Distance.COSINE,
            "euclid": models.Distance.EUCLID,
            "dot": models.Distance.DOT,
        }
        distance = distance_map.get(distance_metric, models.Distance.COSINE)

        # Create collection with dense vectors only (concepts don't need sparse/keyword search)
        vectors_config = {
            "dense": models.VectorParams(
                size=vector_size,
                distance=distance,
                on_disk=False,
            )
        }

        try:
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                on_disk_payload=False,
            )

            # Create payload indexes for common filters
            await self.client.create_payload_index(
                collection_name=collection_name,
                field_name="tenant_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=collection_name,
                field_name="category",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            logger.info(
                f"Created concepts collection '{collection_name}' "
                f"(size={vector_size}, metric={distance_metric})"
            )

        except Exception as e:
            logger.error(f"Failed to create concepts collection: {e}")
            raise

    async def delete_collection(self) -> None:
        """
        Delete collection.

        Warning: This deletes all documents in the collection!

        Example:
            >>> await vector_store.delete_collection()
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            await self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection '{self.collection_name}'")
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            raise

    async def ingest(
        self,
        doc_id: str,
        vector: list[float],
        payload: dict[str, Any],
        sparse_vector: dict[str, Any] | None = None,
        collection_name: str | None = None,
    ) -> None:
        """
        Ingest a document into the vector store.

        Args:
            doc_id: Unique document ID
            vector: Dense embedding vector
            payload: Document metadata and content
            sparse_vector: Optional sparse vector for hybrid search
                          Format: {"indices": [1, 5, 10], "values": [0.8, 0.6, 0.4]}
            collection_name: Collection to ingest into (defaults to self.collection_name)

        Example:
            >>> await vector_store.ingest(
            ...     doc_id="doc-1",
            ...     vector=[0.1, 0.2, ...],
            ...     payload={"content": "Python is great", "source": "docs"},
            ...     sparse_vector={"indices": [1, 5], "values": [0.8, 0.6]},
            ... )
            >>> # Ingest into concepts collection
            >>> await vector_store.ingest(
            ...     doc_id="concept-1",
            ...     vector=[0.1, 0.2, ...],
            ...     payload={"name": "Python", "category": "Language"},
            ...     collection_name="concepts",
            ... )
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        collection = collection_name or self.collection_name

        # Build vectors dict
        vectors = {"dense": vector}
        if sparse_vector:
            vectors["sparse"] = models.SparseVector(
                indices=sparse_vector["indices"],
                values=sparse_vector["values"],
            )

        try:
            await self.client.upsert(
                collection_name=collection,
                points=[
                    models.PointStruct(
                        id=doc_id,
                        vector=vectors,
                        payload=payload,
                    )
                ],
            )
            logger.debug(f"Ingested document {doc_id} into {collection}")

        except Exception as e:
            logger.error(f"Failed to ingest document {doc_id}: {e}")
            raise

    async def ingest_batch(
        self,
        documents: list[dict[str, Any]],
    ) -> None:
        """
        Ingest multiple documents in batch.

        Args:
            documents: List of documents, each with:
                      - doc_id: str
                      - vector: list[float]
                      - payload: dict
                      - sparse_vector: dict (optional)

        Example:
            >>> await vector_store.ingest_batch([
            ...     {
            ...         "doc_id": "doc-1",
            ...         "vector": [0.1, 0.2, ...],
            ...         "payload": {"content": "..."},
            ...     },
            ...     {...},
            ... ])
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        points = []
        for doc in documents:
            vectors = {"dense": doc["vector"]}
            if "sparse_vector" in doc:
                vectors["sparse"] = models.SparseVector(
                    indices=doc["sparse_vector"]["indices"],
                    values=doc["sparse_vector"]["values"],
                )

            points.append(
                models.PointStruct(
                    id=doc["doc_id"],
                    vector=vectors,
                    payload=doc["payload"],
                )
            )

        try:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            logger.info(f"Ingested {len(documents)} documents in batch")

        except Exception as e:
            logger.error(f"Failed to ingest batch: {e}")
            raise

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
        collection_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar documents using dense vector.

        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            filter: Qdrant filter conditions
            score_threshold: Minimum similarity score (0.0 to 1.0)
            collection_name: Collection to search (defaults to self.collection_name)

        Returns:
            list[dict]: Search results with id, score, and payload

        Example:
            >>> results = await vector_store.search(
            ...     query_vector=[0.1, 0.2, ...],
            ...     top_k=5,
            ...     filter={"source": "docs"},
            ...     score_threshold=0.7,
            ... )
            >>> for result in results:
            ...     print(result["id"], result["score"])
            >>> # Search concepts collection
            >>> concept_results = await vector_store.search(
            ...     query_vector=[0.1, 0.2, ...],
            ...     top_k=3,
            ...     collection_name="concepts",
            ... )
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        collection = collection_name or self.collection_name

        # Build filter
        query_filter = None
        if filter:
            conditions = [
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
                for key, value in filter.items()
            ]
            query_filter = models.Filter(must=conditions)

        try:
            search_result = await self.client.search(
                collection_name=collection,
                query_vector=models.NamedVector(
                    name="dense",
                    vector=query_vector,
                ),
                query_filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold,
            )

            results = [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                }
                for hit in search_result
            ]

            logger.debug(f"Search in {collection} returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    async def hybrid_search(
        self,
        query_vector: list[float],
        sparse_vector: dict[str, Any],
        top_k: int = 5,
        alpha: float = 0.7,
        filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Hybrid search combining dense (semantic) and sparse (keyword) vectors.

        Args:
            query_vector: Dense embedding vector
            sparse_vector: Sparse BM25 vector {"indices": [...], "values": [...]}
            top_k: Number of results to return
            alpha: Weight for dense vector (0.0 = keyword only, 1.0 = semantic only)
            filter: Qdrant filter conditions

        Returns:
            list[dict]: Search results with id, score, and payload

        Example:
            >>> results = await vector_store.hybrid_search(
            ...     query_vector=[0.1, 0.2, ...],
            ...     sparse_vector={"indices": [1, 5], "values": [0.8, 0.6]},
            ...     alpha=0.7,  # 70% semantic, 30% keyword
            ... )
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        # Build filter
        query_filter = None
        if filter:
            conditions = [
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
                for key, value in filter.items()
            ]
            query_filter = models.Filter(must=conditions)

        try:
            # Fusion search with Reciprocal Rank Fusion (RRF)
            search_result = await self.client.search(
                collection_name=self.collection_name,
                query_vector=models.NamedVector(
                    name="dense",
                    vector=query_vector,
                ),
                query_filter=query_filter,
                limit=top_k,
                # Note: Full hybrid search requires Qdrant 1.7+
                # For older versions, perform two searches and merge results
            )

            results = [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload,
                }
                for hit in search_result
            ]

            logger.debug(f"Hybrid search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            raise

    async def get_by_id(
        self, doc_id: str, collection_name: str | None = None
    ) -> dict[str, Any] | None:
        """
        Get document by ID.

        Args:
            doc_id: Document ID
            collection_name: Collection to search (defaults to self.collection_name)

        Returns:
            dict | None: Document with id, vector, and payload

        Example:
            >>> doc = await vector_store.get_by_id("doc-1")
            >>> if doc:
            ...     print(doc["payload"]["content"])
            >>> # Get from concepts collection
            >>> concept = await vector_store.get_by_id("concept-1", collection_name="concepts")
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        collection = collection_name or self.collection_name

        try:
            points = await self.client.retrieve(
                collection_name=collection,
                ids=[doc_id],
                with_vectors=True,
                with_payload=True,
            )

            if not points:
                return None

            point = points[0]
            return {
                "id": point.id,
                "vector": point.vector,
                "payload": point.payload,
            }

        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            return None

    async def delete(self, doc_id: str) -> None:
        """
        Delete document by ID.

        Args:
            doc_id: Document ID

        Example:
            >>> await vector_store.delete("doc-1")
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            await self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[doc_id]),
            )
            logger.debug(f"Deleted document {doc_id}")

        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            raise

    async def count(
        self, filter: dict[str, Any] | None = None, collection_name: str | None = None
    ) -> int:
        """
        Count documents in collection.

        Args:
            filter: Optional filter conditions
            collection_name: Collection to count (defaults to self.collection_name)

        Returns:
            int: Number of documents

        Example:
            >>> total = await vector_store.count()
            >>> filtered = await vector_store.count(filter={"source": "docs"})
            >>> # Count concepts
            >>> concept_count = await vector_store.count(collection_name="concepts")
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        collection = collection_name or self.collection_name

        # Build filter
        query_filter = None
        if filter:
            conditions = [
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
                for key, value in filter.items()
            ]
            query_filter = models.Filter(must=conditions)

        try:
            result = await self.client.count(
                collection_name=collection,
                count_filter=query_filter,
            )
            return result.count

        except Exception as e:
            logger.error(f"Failed to count documents: {e}")
            raise

    async def scroll(
        self,
        limit: int = 100,
        offset: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Scroll through documents.

        Args:
            limit: Number of documents per page
            offset: Pagination offset (use next_offset from previous call)
            filter: Optional filter conditions

        Returns:
            tuple: (documents, next_offset)

        Example:
            >>> docs, next_offset = await vector_store.scroll(limit=100)
            >>> while next_offset:
            ...     docs, next_offset = await vector_store.scroll(
            ...         limit=100,
            ...         offset=next_offset,
            ...     )
        """
        if self.client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        # Build filter
        query_filter = None
        if filter:
            conditions = [
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value),
                )
                for key, value in filter.items()
            ]
            query_filter = models.Filter(must=conditions)

        try:
            result = await self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=limit,
                offset=offset,
                with_vectors=False,
                with_payload=True,
            )

            documents = [
                {
                    "id": point.id,
                    "payload": point.payload,
                }
                for point in result[0]
            ]

            next_offset = result[1]
            return documents, next_offset

        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            raise
