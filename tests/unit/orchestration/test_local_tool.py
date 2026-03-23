"""Tests for local_tool decorator and create_tools factory."""

import pytest

from langchain_core.tools import BaseTool

from cortex.orchestration.local_tool import (
    create_local_tool,
    create_tools,
    local_tool,
)


@pytest.mark.unit
class TestLocalToolDecorator:
    """Tests for @local_tool decorator."""

    def test_decorator_without_parens(self):
        @local_tool
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello, {name}!"

        assert isinstance(greet, BaseTool)
        assert greet.name == "greet"
        assert "hello" in greet.description.lower()

    def test_decorator_with_custom_name(self):
        @local_tool(name="custom_greet")
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello, {name}!"

        assert greet.name == "custom_greet"

    def test_decorator_with_return_direct(self):
        @local_tool(return_direct=True)
        def lookup(key: str) -> str:
            """Look up a value."""
            return f"Value for {key}"

        assert lookup.return_direct is True

    def test_sync_function_invocation(self):
        @local_tool
        def add(x: int, y: int) -> int:
            """Add two numbers."""
            return x + y

        result = add.invoke({"x": 3, "y": 4})
        assert result == 7

    @pytest.mark.asyncio
    async def test_async_function_wrapping(self):
        @local_tool
        async def async_greet(name: str) -> str:
            """Async greeting."""
            return f"Hello, {name}!"

        assert isinstance(async_greet, BaseTool)
        result = await async_greet.ainvoke({"name": "World"})
        assert result == "Hello, World!"


@pytest.mark.unit
class TestCreateLocalTool:
    """Tests for create_local_tool() factory."""

    def test_basic_creation(self):
        def multiply(x: int, y: int) -> int:
            """Multiply two numbers."""
            return x * y

        tool = create_local_tool(multiply)
        assert isinstance(tool, BaseTool)
        assert tool.name == "multiply"

    def test_custom_description(self):
        def noop() -> str:
            return "ok"

        tool = create_local_tool(noop, description="Custom desc")
        assert tool.description == "Custom desc"

    def test_fallback_description_when_no_docstring(self):
        def bare_fn(x: int) -> int:
            return x

        tool = create_local_tool(bare_fn)
        assert "bare_fn" in tool.description


@pytest.mark.unit
class TestCreateTools:
    """Tests for create_tools() batch factory."""

    def test_mixed_inputs(self):
        def fn_a(x: int) -> int:
            """Function A."""
            return x

        @local_tool
        def fn_b(y: str) -> str:
            """Function B."""
            return y

        tools = create_tools([fn_a, fn_b])
        assert len(tools) == 2
        assert all(isinstance(t, BaseTool) for t in tools)

    def test_existing_tools_passed_through(self):
        @local_tool
        def existing(x: int) -> int:
            """Already a tool."""
            return x

        tools = create_tools([existing])
        assert len(tools) == 1
        assert tools[0] is existing

    def test_invalid_input_raises(self):
        with pytest.raises(ValueError, match="Invalid tool input"):
            create_tools([42])  # type: ignore
