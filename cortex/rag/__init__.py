"""
RAG (Retrieval-Augmented Generation) Module for Cortex-AI.

Provides document ingestion, vector search, and retrieval capabilities.

Features:
- Qdrant vector store integration
- OpenAI embeddings with Redis caching
- Semantic search and hybrid search
- Document lifecycle management
- Multi-tenancy support

Usage:
    # Initialize RAG components
    from cortex.rag import EmbeddingService, VectorStore, DocumentManager, Retriever

    # Setup embedding service
    embeddings = EmbeddingService(
        openai_api_key="sk-...",
        redis_url="redis://localhost:6379",  # Optional caching
    )

    # Setup vector store
    vector_store = VectorStore(
        url="http://localhost:6333",
        collection_name="documents",
    )
    await vector_store.connect()

    # Ingest documents
    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
    )
    await doc_manager.ingest_document(
        doc_id="doc-1",
        content="Python is a programming language...",
        metadata={"source": "docs", "author": "Alice"},
    )

    # Search documents
    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
    )
    results = await retriever.search(
        query="What is Python?",
        top_k=5,
    )

    # Use with Agent for RAG
    from cortex.orchestration import Agent, ModelConfig

    async def search_documents(query: str) -> str:
        results = await retriever.search(query, top_k=3)
        return "\\n\\n".join([r.content for r in results])

    agent = Agent(
        name="rag-assistant",
        model=ModelConfig(model="gpt-4o"),
        tools=[search_documents],
    )

Environment Variables:
    CORTEX_RAG_ENABLED: Enable RAG module (default: auto-detect from deps)
    CORTEX_QDRANT_URL: Qdrant server URL (default: http://localhost:6333)
    CORTEX_REDIS_URL: Redis URL for caching (default: redis://localhost:6379)
    CORTEX_OPENAI_API_KEY: OpenAI API key for embeddings
"""

from cortex.rag.document import DocumentManager
from cortex.rag.embeddings import EmbeddingService
from cortex.rag.retriever import Retriever, SearchResult
from cortex.rag.vector_store import VectorStore

# GraphRAG components (optional)
try:
    from cortex.rag.graph.graph_store import GraphStore
    from cortex.rag.graph.entity_extractor import EntityExtractor

    __all__ = [
        "EmbeddingService",
        "VectorStore",
        "DocumentManager",
        "Retriever",
        "SearchResult",
        "GraphStore",
        "EntityExtractor",
    ]
except ImportError:
    # GraphRAG dependencies not installed
    __all__ = [
        "EmbeddingService",
        "VectorStore",
        "DocumentManager",
        "Retriever",
        "SearchResult",
    ]
