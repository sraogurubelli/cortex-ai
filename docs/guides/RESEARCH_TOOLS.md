# Research Tools

Research tools for cortex-ai agents that enable web search and academic paper discovery.

## Overview

The research tools provide agents with the ability to:
- **Web Search** - Find current information, news, and general knowledge
- **Academic Search** - Discover research papers from arXiv, PubMed, etc.

## Available Tools

### 1. Web Research Tool

Search the web for current information.

```python
from cortex.tools import create_web_research_tool

tool = create_web_research_tool()
```

**Tool Name:** `search_web`

**Parameters:**
- `query` (str) - Search query
- `num_results` (int) - Number of results (1-10, default: 5)

**Returns:** Formatted search results with titles, snippets, and URLs

**Use Cases:**
- Current events and news
- Recent developments
- General information
- Product information
- Company data

### 2. Academic Research Tool

Search academic databases for research papers.

```python
from cortex.tools import create_academic_research_tool

tool = create_academic_research_tool()
```

**Tool Name:** `search_academic_papers`

**Parameters:**
- `query` (str) - Research topic or keywords
- `num_results` (int) - Number of papers (1-10, default: 3)

**Returns:** Formatted list of papers with titles, authors, abstracts, and links

**Use Cases:**
- Scientific research
- Academic literature reviews
- Technical deep dives
- Peer-reviewed sources
- Research validation

## Quick Start

### Basic Usage

```python
import asyncio
from cortex.orchestration import Agent, ModelConfig, ToolRegistry
from cortex.tools import create_web_research_tool

async def main():
    # Create tool registry
    registry = ToolRegistry()
    registry.register(create_web_research_tool())

    # Create agent with research capability
    agent = Agent(
        name="researcher",
        system_prompt="You are a research assistant. Use search_web to find information.",
        model=ModelConfig(model="gpt-4o"),
        tool_registry=registry,
        tools=None,  # Use all registry tools
    )

    # Ask a question
    result = await agent.run("What are the latest AI developments?")
    print(result.response)

asyncio.run(main())
```

### With API Key Injection

```python
# Create registry and inject API key via context
registry = ToolRegistry()
registry.register(create_web_research_tool())
registry.set_context(search_api_key="your-google-api-key")

agent = Agent(
    name="researcher",
    tool_registry=registry,
    tools=None,
)
```

### Both Web and Academic Search

```python
# Register both tools
registry = ToolRegistry()
registry.register(create_web_research_tool())
registry.register(create_academic_research_tool())

agent = Agent(
    name="comprehensive_researcher",
    system_prompt="""
You have access to both web search and academic paper search.
- Use search_web for current information
- Use search_academic_papers for scientific research
    """,
    tool_registry=registry,
    tools=None,
)
```

## Multi-turn Research Session

```python
thread_id = "research-session-123"

# First question
result1 = await agent.run(
    "What is GraphRAG?",
    thread_id=thread_id,
)

# Follow-up (agent remembers context)
result2 = await agent.run(
    "Find recent academic papers on this topic",
    thread_id=thread_id,
)

# Another follow-up
result3 = await agent.run(
    "What are the key benefits?",
    thread_id=thread_id,
)
```

## Integration with Existing APIs

### Google Custom Search API

To integrate real web search, update `cortex/tools/research.py`:

```python
import httpx

async def _web_search(query: str, num_results: int = 5, search_api_key: str = ""):
    """Search the web using Google Custom Search API."""
    api_key = search_api_key or os.getenv("GOOGLE_SEARCH_API_KEY")
    cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": api_key,
                "cx": cx,
                "q": query,
                "num": num_results,
            },
        )
        data = response.json()

        # Format results
        results = []
        for item in data.get("items", []):
            results.append(
                f"**{item['title']}**\n"
                f"{item['snippet']}\n"
                f"URL: {item['link']}\n"
            )

        return "\n".join(results)
```

**Setup:**
1. Get API key from [Google Cloud Console](https://console.cloud.google.com/)
2. Create Custom Search Engine at [CSE Control Panel](https://programmablesearchengine.google.com/)
3. Set environment variables:
   ```bash
   export GOOGLE_SEARCH_API_KEY="your-key"
   export GOOGLE_SEARCH_ENGINE_ID="your-cx"
   ```

### arXiv API

For academic papers, integrate with arXiv:

```python
import httpx
import xml.etree.ElementTree as ET

async def _academic_search(query: str, num_results: int = 3):
    """Search arXiv for research papers."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": num_results,
            },
        )

        # Parse XML
        root = ET.fromstring(response.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        results = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns).text
            summary = entry.find("atom:summary", ns).text
            published = entry.find("atom:published", ns).text
            link = entry.find("atom:id", ns).text

            results.append(
                f"**{title}**\n"
                f"Abstract: {summary[:200]}...\n"
                f"Published: {published}\n"
                f"URL: {link}\n"
            )

        return "\n".join(results)
```

**No API key needed** - arXiv API is free to use.

## Alternative Search APIs

### Brave Search API

Fast, privacy-focused search with generous free tier:

```bash
# Get API key from https://brave.com/search/api/
export BRAVE_SEARCH_API_KEY="your-key"
```

```python
async with httpx.AsyncClient() as client:
    response = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": api_key},
        params={"q": query, "count": num_results},
    )
```

### SerpAPI

Multiple search engines (Google, Bing, DuckDuckGo):

```bash
export SERPAPI_KEY="your-key"
```

```python
from serpapi import GoogleSearch

search = GoogleSearch({"q": query, "api_key": api_key})
results = search.get_dict()
```

## Example Demo

Run the research agent demo:

```bash
python examples/research_agent_demo.py
```

This demonstrates:
1. Web research agent
2. Academic research agent
3. Combined research agent (both tools)
4. Multi-turn research session

## Configuration

### Environment Variables

```bash
# Optional - for real API integration
export GOOGLE_SEARCH_API_KEY="your-key"
export GOOGLE_SEARCH_ENGINE_ID="your-cx"
export BRAVE_SEARCH_API_KEY="your-key"
export SERPAPI_KEY="your-key"
```

### Tool Registration

```python
# Register tools
registry = ToolRegistry()
registry.register(create_web_research_tool())
registry.register(create_academic_research_tool())

# Inject API keys (optional)
registry.set_context(
    search_api_key="your-google-key",
    # Keys are injected automatically, LLM never sees them
)
```

## Best Practices

### ✅ Do

- Use `search_web` for current/recent information
- Use `search_academic_papers` for scientific research
- Include both tools for comprehensive research agents
- Use `thread_id` for multi-turn research sessions
- Inject API keys via `ToolRegistry.set_context()`
- Log tool usage for monitoring

### ❌ Don't

- Don't put API keys in system prompts
- Don't skip error handling
- Don't request too many results (rate limits)
- Don't forget to cite sources in agent responses

## Testing

### Unit Tests

```python
import pytest
from cortex.tools import create_web_research_tool

@pytest.mark.asyncio
async def test_web_research_tool():
    """Test web research tool can be invoked."""
    tool = create_web_research_tool()

    result = await tool.ainvoke({"query": "test query", "num_results": 3})

    assert isinstance(result, str)
    assert len(result) > 0
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_research_agent_with_web_search():
    """Test agent can use web search tool."""
    registry = ToolRegistry()
    registry.register(create_web_research_tool())

    agent = Agent(
        name="researcher",
        tool_registry=registry,
        tools=None,
    )

    result = await agent.run("Search for Python tutorials")

    assert result.response is not None
    assert "gpt-4o" in result.token_usage
```

## Troubleshooting

### Tool not being called

**Problem:** Agent doesn't use search tools

**Solution:**
1. Check system prompt mentions the tools
2. Verify tool descriptions are clear
3. Ensure question requires external information

### API rate limits

**Problem:** Too many requests

**Solution:**
1. Implement caching for repeated queries
2. Use `num_results` parameter efficiently
3. Add rate limiting in tool implementation

### Empty results

**Problem:** No search results returned

**Solution:**
1. Check API key is valid
2. Verify query format
3. Check API quotas/limits
4. Review search engine configuration

## Next Steps

1. **Integrate real APIs** - Replace mock responses with actual API calls
2. **Add caching** - Cache search results to reduce API costs
3. **Add more sources** - Wikipedia, news APIs, domain-specific databases
4. **Improve formatting** - Better result presentation
5. **Add filtering** - Date ranges, domains, content types

## Reference

- **Source Code:** `cortex/tools/research.py`
- **Example Demo:** `examples/research_agent_demo.py`
- **Tool Registry:** `cortex/orchestration/tools.py`
- **Agent Documentation:** `docs/ORCHESTRATION_ARCHITECTURE.md`

---

**Created:** March 2026
