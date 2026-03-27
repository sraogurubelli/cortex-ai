---
description: Generate all necessary files for a new orchestration agent with tools and testing
---

You will create a new orchestration agent in cortex-ai based on the provided specification.

## Input Format

The user will provide a specification like this:

```yaml
agentName: DataAnalysisAgent          # PascalCase name
moduleName: data_analysis             # snake_case name for module
description: Analyzes data and generates insights
tools:                                # List of tools for the agent
  - name: query_database
    description: Query the database
    parameters:
      - name: query
        type: str
        description: SQL query to execute
  - name: generate_chart
    description: Generate visualization
    parameters:
      - name: data
        type: dict
        description: Data to visualize
systemPrompt: |
  You are a data analysis assistant.
  Your role is to analyze data and provide insights.
```

## Files to Create

### 1. Agent Module Structure

Create the following directory structure:
```
cortex/orchestration/agents/{moduleName}/
├── __init__.py
├── agent.py           # Main agent class
├── tools.py           # Tool definitions
└── config.py          # Agent configuration
```

### 2. Main Agent File

**Path:** `cortex/orchestration/agents/{moduleName}/agent.py`

```python
"""
{agentName} - {description}
"""

from cortex.orchestration import Agent, ModelConfig
from cortex.orchestration.agents.{moduleName}.tools import get_{moduleName}_tools
from cortex.orchestration.agents.{moduleName}.config import {agentName}Config


class {agentName}:
    """
    {description}

    Example:
        ```python
        agent = {agentName}()
        result = await agent.run("Analyze sales data for Q4")
        print(result.response)
        ```
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        config: {agentName}Config | None = None,
    ):
        """Initialize the {agentName}.

        Args:
            model: LLM model to use
            temperature: Model temperature
            config: Optional agent configuration
        """
        self.config = config or {agentName}Config()
        self.agent = Agent(
            name="{moduleName}_agent",
            description="{description}",
            system_prompt=self.config.system_prompt,
            model=ModelConfig(model=model, temperature=temperature),
            tools=get_{moduleName}_tools(),
        )

    async def run(
        self,
        query: str,
        thread_id: str | None = None,
    ) -> dict:
        """Run the agent with a query.

        Args:
            query: User query
            thread_id: Optional thread ID for conversation continuity

        Returns:
            Agent response with analysis results
        """
        result = await self.agent.run(query, thread_id=thread_id)

        return {
            "response": result.response,
            "token_usage": result.token_usage,
            "messages": result.messages,
        }

    async def stream(
        self,
        query: str,
        stream_writer,
        thread_id: str | None = None,
    ):
        """Stream agent response.

        Args:
            query: User query
            stream_writer: SSE writer for streaming
            thread_id: Optional thread ID for conversation continuity
        """
        return await self.agent.stream_to_writer(
            query,
            stream_writer=stream_writer,
            thread_id=thread_id,
        )
```

### 3. Tools File

**Path:** `cortex/orchestration/agents/{moduleName}/tools.py`

```python
"""
Tools for {agentName}
"""

from langchain_core.tools import tool
from pydantic import Field


# For each tool in the YAML:
@tool
def {tool_name}(
    {param_name}: {param_type} = Field(..., description="{param_description}"),
    # ... more parameters
) -> str:
    """
    {tool_description}

    Args:
        {param_name}: {param_description}
        # ... more args

    Returns:
        Tool execution result
    """
    # TODO: Implement tool logic
    raise NotImplementedError("Tool implementation pending")


def get_{moduleName}_tools() -> list:
    """Get all tools for {agentName}.

    Returns:
        List of LangChain tools
    """
    return [
        {tool_name},
        # ... more tools
    ]
```

### 4. Config File

**Path:** `cortex/orchestration/agents/{moduleName}/config.py`

```python
"""
Configuration for {agentName}
"""

from pydantic import BaseModel, Field


class {agentName}Config(BaseModel):
    """Configuration for {agentName}."""

    system_prompt: str = Field(
        default=\"""
{systemPrompt}
        \""",
        description="System prompt for the agent",
    )

    max_iterations: int = Field(
        default=25,
        description="Maximum tool call iterations",
    )

    # Add custom config fields here
```

### 5. __init__.py

**Path:** `cortex/orchestration/agents/{moduleName}/__init__.py`

```python
"""
{agentName} - {description}
"""

from cortex.orchestration.agents.{moduleName}.agent import {agentName}
from cortex.orchestration.agents.{moduleName}.config import {agentName}Config

__all__ = ["{agentName}", "{agentName}Config"]
```

### 6. Test File

**Path:** `tests/orchestration/agents/test_{moduleName}.py`

```python
"""
Tests for {agentName}
"""

import pytest
from cortex.orchestration.agents.{moduleName} import {agentName}, {agentName}Config


@pytest.mark.asyncio
async def test_{moduleName}_initialization():
    """Test {agentName} can be initialized."""
    agent = {agentName}()

    assert agent.agent.name == "{moduleName}_agent"
    assert agent.config is not None


@pytest.mark.asyncio
async def test_{moduleName}_run():
    """Test {agentName} can execute query."""
    agent = {agentName}()

    result = await agent.run("Test query")

    assert "response" in result
    assert "token_usage" in result
    assert result["response"] is not None


@pytest.mark.asyncio
async def test_{moduleName}_with_custom_config():
    """Test {agentName} with custom configuration."""
    config = {agentName}Config(
        system_prompt="Custom system prompt",
        max_iterations=10,
    )

    agent = {agentName}(config=config)

    assert agent.config.system_prompt == "Custom system prompt"
    assert agent.config.max_iterations == 10


# Add tests for each tool
@pytest.mark.asyncio
async def test_{tool_name}_tool():
    """Test {tool_name} tool."""
    from cortex.orchestration.agents.{moduleName}.tools import {tool_name}

    # Mock test - update with real assertions
    with pytest.raises(NotImplementedError):
        result = {tool_name}.invoke({{"param": "value"}})
```

### 7. Example Usage

**Path:** `examples/{moduleName}_demo.py`

```python
"""
Example usage of {agentName}
"""

import asyncio
from cortex.orchestration.agents.{moduleName} import {agentName}


async def main():
    """Run {agentName} example."""
    # Initialize agent
    agent = {agentName}(model="gpt-4o", temperature=0.7)

    # Single query
    result = await agent.run("Example query here")
    print(f"Response: {{result['response']}}")
    print(f"Tokens: {{result['token_usage']}}")

    # Multi-turn conversation
    thread_id = "example-session"
    result1 = await agent.run("First question", thread_id=thread_id)
    print(f"Turn 1: {{result1['response']}}")

    result2 = await agent.run("Follow-up question", thread_id=thread_id)
    print(f"Turn 2: {{result2['response']}}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 8. Documentation

**Path:** `docs/agents/{moduleName}.md`

```markdown
# {agentName}

{description}

## Installation

The agent is part of cortex-ai. No additional installation required.

## Usage

### Basic Usage

\```python
from cortex.orchestration.agents.{moduleName} import {agentName}

agent = {agentName}()
result = await agent.run("Your query here")
print(result['response'])
\```

### With Custom Configuration

\```python
from cortex.orchestration.agents.{moduleName} import {agentName}, {agentName}Config

config = {agentName}Config(
    system_prompt="Custom prompt",
    max_iterations=10,
)

agent = {agentName}(config=config)
\```

### Multi-turn Conversations

\```python
thread_id = "user-session-123"

result1 = await agent.run("First question", thread_id=thread_id)
result2 = await agent.run("Follow-up", thread_id=thread_id)
\```

## Tools

### {tool_name}

{tool_description}

**Parameters:**
- `{param_name}` ({param_type}): {param_description}

**Example:**
\```python
# Agent will automatically use this tool when needed
result = await agent.run("Query that needs {tool_name}")
\```

## Configuration

See `{agentName}Config` for all configuration options.

## Testing

Run tests with:
\```bash
pytest tests/orchestration/agents/test_{moduleName}.py -v
\```

## Examples

See `examples/{moduleName}_demo.py` for complete examples.
```

## Checklist

After creating all files, verify:

- [ ] Agent module created in `cortex/orchestration/agents/{moduleName}/`
- [ ] All 4 module files created (agent.py, tools.py, config.py, __init__.py)
- [ ] Test file created with basic tests
- [ ] Example file created and runnable
- [ ] Documentation created
- [ ] All imports work correctly
- [ ] Tests pass: `pytest tests/orchestration/agents/test_{moduleName}.py -v`
- [ ] Type checking passes: `mypy cortex/orchestration/agents/{moduleName}/`
- [ ] Example runs: `python examples/{moduleName}_demo.py`

## Next Steps

1. Implement tool logic in `tools.py`
2. Add more tests for edge cases
3. Update system prompt in `config.py` based on testing
4. Add to main README under "Available Agents"
