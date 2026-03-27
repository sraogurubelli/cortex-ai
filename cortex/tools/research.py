"""
Web research tool for LangChain agents.

Provides a ``StructuredTool`` that searches the web for information,
with optional API key injection via ToolRegistry context.

Usage::

    from cortex.tools.research import create_web_research_tool

    tool = create_web_research_tool()
    registry.register(tool)
    registry.set_context(search_api_key="your-api-key")  # Optional
"""

import logging
import os
from typing import Any

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


async def _web_search(
    query: str,
    num_results: int = 5,
    search_api_key: str = "",
) -> str:
    """Search the web for information.

    Args:
        query: Search query (what to search for).
        num_results: Number of results to return (1-10).
        search_api_key: API key for search service (injected via context).

    Returns:
        Formatted search results with titles, snippets, and URLs.
    """
    # Validate inputs
    if not query or not query.strip():
        return "Error: Search query cannot be empty."

    num_results = max(1, min(num_results, 10))

    try:
        # TODO: Replace with actual search API integration
        # Options: Google Custom Search API, Brave Search API, SerpAPI, etc.
        #
        # Example with Google Custom Search:
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(
        #         "https://www.googleapis.com/customsearch/v1",
        #         params={
        #             "key": search_api_key or os.getenv("GOOGLE_SEARCH_API_KEY"),
        #             "cx": os.getenv("GOOGLE_SEARCH_ENGINE_ID"),
        #             "q": query,
        #             "num": num_results,
        #         },
        #     )
        #     data = response.json()
        #     ...

        # For now, return mock response
        logger.info(f"Web search: {query} (requesting {num_results} results)")

        # Mock results for demonstration
        results = []
        for i in range(num_results):
            results.append(
                f"{i + 1}. **Example Result {i + 1}**\n"
                f"   - *Snippet:* Information about '{query}' ...\n"
                f"   - *URL:* https://example.com/result-{i + 1}\n"
            )

        if not results:
            return f"No results found for query: '{query}'"

        return (
            f"**Web Search Results for:** {query}\n\n"
            + "\n".join(results)
            + f"\n\n*Note: Showing {len(results)} of {num_results} requested results.*"
        )

    except Exception as exc:
        logger.error(f"Web search failed: {exc}", exc_info=True)
        return f"Web search temporarily unavailable: {exc}"


async def _academic_search(
    query: str,
    num_results: int = 3,
    arxiv_api_key: str = "",
) -> str:
    """Search academic papers (arXiv, PubMed, etc.).

    Args:
        query: Research topic or keywords.
        num_results: Number of papers to return (1-10).
        arxiv_api_key: API key if needed (injected via context).

    Returns:
        Formatted list of academic papers with titles, authors, and abstracts.
    """
    if not query or not query.strip():
        return "Error: Search query cannot be empty."

    num_results = max(1, min(num_results, 10))

    try:
        # TODO: Integrate with arXiv API, PubMed API, or Semantic Scholar
        #
        # Example with arXiv:
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(
        #         "http://export.arxiv.org/api/query",
        #         params={
        #             "search_query": f"all:{query}",
        #             "start": 0,
        #             "max_results": num_results,
        #         },
        #     )
        #     # Parse XML response
        #     ...

        logger.info(f"Academic search: {query} (requesting {num_results} papers)")

        # Mock results for demonstration
        results = []
        for i in range(num_results):
            results.append(
                f"{i + 1}. **Paper Title About {query}**\n"
                f"   - *Authors:* John Doe, Jane Smith\n"
                f"   - *Abstract:* This paper explores {query} and presents...\n"
                f"   - *Published:* 2024-03-{i + 1:02d}\n"
                f"   - *URL:* https://arxiv.org/abs/2403.{i + 1:05d}\n"
            )

        if not results:
            return f"No academic papers found for: '{query}'"

        return (
            f"**Academic Papers on:** {query}\n\n"
            + "\n".join(results)
            + f"\n\n*Found {len(results)} papers.*"
        )

    except Exception as exc:
        logger.error(f"Academic search failed: {exc}", exc_info=True)
        return f"Academic search temporarily unavailable: {exc}"


def create_web_research_tool() -> StructuredTool:
    """Create a LangChain tool for web research.

    The tool can search the web for current information. Optionally uses
    ``search_api_key`` from the ToolRegistry context for API authentication.

    Register with::

        tool_registry.register(create_web_research_tool())
        tool_registry.set_context(search_api_key="your-key")  # Optional
    """
    return StructuredTool.from_function(
        coroutine=_web_search,
        name="search_web",
        description=(
            "Search the web for current information on any topic. "
            "Use this when the user asks about current events, recent news, "
            "or information that may not be in your training data. "
            "Returns web search results with titles, snippets, and URLs."
        ),
        handle_tool_error=True,
    )


def create_academic_research_tool() -> StructuredTool:
    """Create a LangChain tool for academic research.

    Searches academic databases like arXiv, PubMed, or Semantic Scholar
    for research papers.

    Register with::

        tool_registry.register(create_academic_research_tool())
    """
    return StructuredTool.from_function(
        coroutine=_academic_search,
        name="search_academic_papers",
        description=(
            "Search academic databases for research papers on a topic. "
            "Use this when the user needs scientific or academic sources. "
            "Returns paper titles, authors, abstracts, and publication details."
        ),
        handle_tool_error=True,
    )
