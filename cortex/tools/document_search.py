"""
Document search tool for LangChain agents.

Provides a ``StructuredTool`` that searches project documents via the
cortex RAG pipeline, scoped to the current project using ToolRegistry
context injection.

Usage::

    from cortex.tools.document_search import create_document_search_tool

    tool = create_document_search_tool()
    registry.register(tool)
"""

import logging
import os
from typing import Any

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

_retriever_cache: dict[str, Any] = {}


async def _get_retriever():
    """Lazily create and cache a Retriever instance."""
    if "retriever" not in _retriever_cache:
        from cortex.rag import EmbeddingService, Retriever, VectorStore

        openai_key = os.getenv("OPENAI_API_KEY", "")
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        redis_url = os.getenv("REDIS_URL")
        collection = os.getenv("QDRANT_COLLECTION_NAME", "cortex_documents")

        embeddings = EmbeddingService(
            openai_api_key=openai_key,
            redis_url=redis_url,
        )
        vector_store = VectorStore(url=qdrant_url, collection_name=collection)
        await vector_store.connect()

        _retriever_cache["retriever"] = Retriever(
            embeddings=embeddings,
            vector_store=vector_store,
        )

    return _retriever_cache["retriever"]


async def _search_documents(
    query: str,
    top_k: int = 5,
    project_id: str = "",
) -> str:
    """Search project documents for relevant information.

    Args:
        query: Natural language search query.
        top_k: Number of results to return (1-20).

    Returns:
        Formatted text of matching document chunks, or a message
        indicating no results were found.
    """
    if not project_id:
        return "No project context available. Cannot search documents."

    try:
        retriever = await _get_retriever()
        results = await retriever.search(
            query=query,
            top_k=min(top_k, 20),
            tenant_id=project_id,
        )

        if not results:
            return f"No documents found matching '{query}' in this project."

        return retriever.format_results(results, include_scores=True)

    except Exception as exc:
        logger.warning("Document search failed: %s", exc)
        return f"Document search temporarily unavailable: {exc}"


def create_document_search_tool() -> StructuredTool:
    """Create a LangChain tool for searching project documents.

    The tool uses the ``project_id`` from the ToolRegistry context to
    scope searches to the current project.  Register with::

        tool_registry.register(create_document_search_tool())
    """
    return StructuredTool.from_function(
        coroutine=_search_documents,
        name="search_project_documents",
        description=(
            "Search the project's uploaded documents and knowledge base. "
            "Use this tool when the user asks questions that might be "
            "answered by project documentation, uploaded files, or "
            "stored knowledge. Returns relevant document excerpts."
        ),
        handle_tool_error=True,
    )
