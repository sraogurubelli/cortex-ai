"""
Research Agent Demo

Demonstrates how to use the research tools with an orchestration agent.
"""

import asyncio
import logging

from cortex.orchestration import Agent, ModelConfig, ToolRegistry
from cortex.tools import create_web_research_tool, create_academic_research_tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def main():
    """Run research agent demos."""
    print("=" * 80)
    print("RESEARCH AGENT DEMO")
    print("=" * 80)
    print()

    # =========================================================================
    # Demo 1: Web Research Agent
    # =========================================================================
    print("Demo 1: Web Research Agent")
    print("-" * 80)

    # Create tool registry with research tools
    registry = ToolRegistry()
    registry.register(create_web_research_tool())

    # Optionally inject API key via context
    # registry.set_context(search_api_key="your-google-api-key")

    # Create research agent
    research_agent = Agent(
        name="research_assistant",
        description="An agent that can search the web for information",
        system_prompt="""
You are a research assistant with access to web search.

When the user asks about current events or topics requiring recent information,
use the search_web tool to find relevant information.

Always cite your sources by including the URLs from search results.
        """,
        model=ModelConfig(model="gpt-4o", temperature=0.7, use_gateway=False),
        tool_registry=registry,
        tools=None,  # Use all tools from registry
    )

    # Test query
    query = "What are the latest developments in AI agents?"
    print(f"\nQuery: {query}\n")

    result = await research_agent.run(query)

    print(f"Response:\n{result.response}\n")
    print(f"Token Usage: {result.token_usage}\n")
    print()

    # =========================================================================
    # Demo 2: Academic Research Agent
    # =========================================================================
    print("Demo 2: Academic Research Agent")
    print("-" * 80)

    # Create registry with academic search
    academic_registry = ToolRegistry()
    academic_registry.register(create_academic_research_tool())

    # Create academic research agent
    academic_agent = Agent(
        name="academic_researcher",
        description="An agent specialized in finding academic papers",
        system_prompt="""
You are an academic research assistant with access to research paper databases.

When asked about scientific topics, use the search_academic_papers tool to find
relevant research papers.

Provide summaries of the papers including:
- Title and authors
- Key findings from abstracts
- Publication dates
- Links to papers
        """,
        model=ModelConfig(model="gpt-4o", temperature=0.7, use_gateway=False),
        tool_registry=academic_registry,
        tools=None,
    )

    # Test query
    query = "Find recent papers on GraphRAG and knowledge graphs"
    print(f"\nQuery: {query}\n")

    result = await academic_agent.run(query)

    print(f"Response:\n{result.response}\n")
    print(f"Token Usage: {result.token_usage}\n")
    print()

    # =========================================================================
    # Demo 3: Combined Research Agent (Web + Academic)
    # =========================================================================
    print("Demo 3: Combined Research Agent")
    print("-" * 80)

    # Create registry with both tools
    combined_registry = ToolRegistry()
    combined_registry.register(create_web_research_tool())
    combined_registry.register(create_academic_research_tool())

    # Create comprehensive research agent
    combined_agent = Agent(
        name="comprehensive_researcher",
        description="An agent with web and academic search capabilities",
        system_prompt="""
You are a comprehensive research assistant with access to:
1. Web search for current information and news
2. Academic paper search for scientific research

Choose the appropriate tool based on the question:
- Use search_web for current events, news, or general information
- Use search_academic_papers for scientific topics requiring peer-reviewed sources

Provide well-researched answers with proper citations.
        """,
        model=ModelConfig(model="gpt-4o", temperature=0.7, use_gateway=False),
        tool_registry=combined_registry,
        tools=None,
    )

    # Test query requiring both tools
    query = "What is RAG in AI, and are there recent research papers about it?"
    print(f"\nQuery: {query}\n")

    result = await combined_agent.run(query)

    print(f"Response:\n{result.response}\n")
    print(f"Token Usage: {result.token_usage}\n")
    print()

    # =========================================================================
    # Demo 4: Multi-turn Research Session
    # =========================================================================
    print("Demo 4: Multi-turn Research Session")
    print("-" * 80)

    thread_id = "research-session-123"

    queries = [
        "Tell me about GraphRAG",
        "Find academic papers on this topic",
        "What are the key differences from traditional RAG?",
    ]

    print("\nStarting research conversation...\n")

    for i, query in enumerate(queries, 1):
        print(f"[Turn {i}] User: {query}")

        result = await combined_agent.run(query, thread_id=thread_id)

        print(f"[Turn {i}] Agent: {result.response[:200]}...")
        print(f"         Tokens: {result.token_usage}")
        print()

    print("=" * 80)
    print("Research agent demos completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
