"""
Local Tool Creation and Registration.

Provides decorators and factory functions for creating LangChain
``StructuredTool`` instances from plain Python functions with type
annotations.  Supports both sync and async functions.

Usage::

    from cortex.orchestration.local_tool import local_tool, create_local_tool, create_tools

    # Decorator without parentheses
    @local_tool
    def my_tool(x: int) -> str:
        '''My tool description.'''
        return f"Result: {x}"

    # Decorator with options
    @local_tool(name="custom_name", return_direct=True)
    def another_tool(x: int) -> str:
        '''Another tool.'''
        return f"Result: {x}"

    # Factory function
    tool = create_local_tool(my_function, name="custom_name")

    # Batch creation from mixed inputs
    tools = create_tools([search_fn, existing_tool, calculate_fn])

Ported from ml-infra orchestration_sdk/tools/local_tool.py.
"""

import asyncio
import inspect
from typing import Any, Callable, overload

from langchain_core.tools import BaseTool, StructuredTool

ToolErrorHandler = bool | str | Callable[[Exception], str]
"""Controls error handling when a tool raises an exception.

- ``True`` (default): return the exception message to the LLM as an
  error ToolMessage instead of propagating.
- ``str``: return a fixed error message string.
- ``Callable``: called with the exception to produce a custom error message.
- ``False``: propagate exceptions (not recommended for production agents).
"""


def create_local_tool(
    func: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
    return_direct: bool = False,
    args_schema: Any = None,
    handle_tool_error: ToolErrorHandler = True,
) -> BaseTool:
    """Create a LangChain tool from a Python function.

    Handles both sync and async functions automatically.

    Args:
        func: Function to wrap (sync or async).
        name: Tool name (defaults to function name).
        description: Tool description (defaults to docstring).
        return_direct: If True, return output directly without LLM processing.
        args_schema: Pydantic model for argument validation.
        handle_tool_error: Controls error handling.  Defaults to ``True``.

    Returns:
        LangChain ``BaseTool`` instance.
    """
    tool_name = name or func.__name__
    tool_desc = description or inspect.getdoc(func) or f"Execute {tool_name}"

    is_async = asyncio.iscoroutinefunction(func)

    if is_async:
        return StructuredTool.from_function(
            coroutine=func,
            name=tool_name,
            description=tool_desc,
            return_direct=return_direct,
            args_schema=args_schema,
            handle_tool_error=handle_tool_error,
        )

    return StructuredTool.from_function(
        func=func,
        name=tool_name,
        description=tool_desc,
        return_direct=return_direct,
        args_schema=args_schema,
        handle_tool_error=handle_tool_error,
    )


@overload
def local_tool(func: Callable[..., Any]) -> BaseTool: ...


@overload
def local_tool(
    *,
    name: str | None = None,
    description: str | None = None,
    return_direct: bool = False,
    args_schema: Any = None,
) -> Callable[[Callable[..., Any]], BaseTool]: ...


def local_tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    return_direct: bool = False,
    args_schema: Any = None,
) -> BaseTool | Callable[[Callable[..., Any]], BaseTool]:
    """Decorator to create a LangChain tool from a function.

    Works with or without parentheses.  Supports both sync and async functions.

    Examples::

        # Without parentheses
        @local_tool
        def my_tool(x: int) -> str:
            '''My tool description.'''
            return f"Result: {x}"

        # With options
        @local_tool(name="custom_search", return_direct=True)
        def search(query: str) -> str:
            '''Search for information.'''
            return f"Results: {query}"

        # With Pydantic schema
        from pydantic import BaseModel, Field

        class SearchArgs(BaseModel):
            query: str = Field(description="Search query")
            limit: int = Field(default=10, description="Max results")

        @local_tool(args_schema=SearchArgs)
        def validated_search(query: str, limit: int = 10) -> str:
            '''Search with validation.'''
            return f"Results for {query} (limit {limit})"
    """

    def decorator(fn: Callable[..., Any]) -> BaseTool:
        return create_local_tool(
            fn,
            name=name,
            description=description,
            return_direct=return_direct,
            args_schema=args_schema,
        )

    if func is not None:
        return decorator(func)

    return decorator


def create_tools(
    functions: list[BaseTool | Callable[..., Any]],
    *,
    return_direct: bool = False,
) -> list[BaseTool]:
    """Create a list of LangChain tools from functions.

    Accepts a mix of:

    * ``BaseTool`` instances (passed through unchanged)
    * Functions decorated with ``@tool`` (passed through)
    * Plain Python functions (converted to tools)

    Args:
        functions: List of functions or tools.
        return_direct: Default ``return_direct`` for newly created tools.

    Returns:
        List of ``BaseTool`` instances.

    Example::

        def search(query: str) -> str:
            '''Search for information.'''
            return f"Results: {query}"

        def calculate(x: int, y: int) -> int:
            '''Add two numbers.'''
            return x + y

        tools = create_tools([search, calculate])
    """
    tools: list[BaseTool] = []

    for item in functions:
        if isinstance(item, BaseTool):
            tools.append(item)
        elif callable(item):
            tools.append(create_local_tool(item, return_direct=return_direct))
        else:
            raise ValueError(f"Invalid tool input: {type(item)}")

    return tools
