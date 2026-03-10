"""
Tool Registry for managing agent tools.

Provides a unified registry for tools with:
- Context injection for tool calls
- Tool filtering and retrieval
- Dynamic tool registration
"""

import logging
from typing import Any, Callable

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field, create_model

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing agent tools with context injection.

    Example:
        registry = ToolRegistry()

        # Register tools
        registry.register(my_tool)
        registry.register(another_tool, name="custom_name")

        # Set context for injection
        registry.set_context(user_id="user123", session_id="sess456")

        # Get tools with context injection
        wrapped_tools = registry.all_wrapped()

        # Or get unwrapped tools
        tool = registry.get("my_tool")
        all_tools = registry.all()
    """

    # Tools that skip context injection (exact matches)
    SKIP_CONTEXT_TOOLS = frozenset({"get_prompt", "list_prompts", "complete_task"})

    # Tool name prefixes that skip context injection (pattern matching)
    # Used for swarm handoff tools: transfer_to_researcher, transfer_to_writer, etc.
    SKIP_CONTEXT_PREFIXES = frozenset({"transfer_to_"})

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._context: dict[str, Any] = {}

    @classmethod
    def with_defaults(cls) -> "ToolRegistry":
        """
        Create a new registry pre-populated with default tools.

        Returns a fresh copy — mutations do not affect the singleton.
        Use ``remove()`` to filter defaults or ``register()`` to add more.

        Example:
            registry = ToolRegistry.with_defaults()
            registry.remove("unwanted_tool")
            registry.register(my_custom_tool)
        """
        # For Cortex-AI, return empty registry by default
        # Users can add their own tools
        return cls()

    # =========================================================================
    # Tool Registration
    # =========================================================================

    def register(
        self,
        tool: BaseTool | Callable[..., Any],
        name: str | None = None,
        wrap_context: bool = False,
    ) -> "ToolRegistry":
        """
        Register a tool.

        Args:
            tool: Tool to register (BaseTool or callable)
            name: Optional name override
            wrap_context: If True, wrap tool for automatic context injection.
                         Usually set to False here, then use all_wrapped() to get
                         tools with context injection at retrieval time.

        Returns:
            Self for chaining

        Example:
            registry.register(my_tool)
            registry.register(my_func, name="custom_name")
        """
        # Wrap callable if needed
        if not isinstance(tool, BaseTool):
            tool = StructuredTool.from_function(tool)

        # Optionally wrap with context injection
        if wrap_context:
            tool = self.wrap_with_context(tool)

        # Determine name
        tool_name = name or tool.name
        self._tools[tool_name] = tool
        return self

    # =========================================================================
    # Tool Retrieval
    # =========================================================================

    def get(self, name: str) -> BaseTool:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            The tool

        Raises:
            KeyError: If tool not found
        """
        if name not in self._tools:
            raise KeyError(
                f"Tool '{name}' not found. Available: {list(self._tools.keys())}"
            )
        return self._tools[name]

    def all(self) -> list[BaseTool]:
        """Get all registered tools (unwrapped)."""
        return list(self._tools.values())

    def all_wrapped(self) -> list[BaseTool]:
        """
        Get all registered tools wrapped with context injection.

        Each tool is wrapped to automatically:
        1. Filter out None/empty values from LLM args
        2. Inject context values for matching schema parameters

        Use this when passing tools to agents that need context injection.

        Returns:
            List of wrapped tools

        Example:
            registry.set_context(user_id="user123")
            tools = registry.all_wrapped()  # Tools will auto-inject user_id
        """
        return [self.wrap_with_context(tool) for tool in self._tools.values()]

    def list_names(self) -> list[str]:
        """List registered tool names."""
        return list(self._tools.keys())

    def remove(self, name: str) -> bool:
        """
        Remove a tool by name.

        Returns:
            True if removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()

    def merge(self, other: "ToolRegistry") -> "ToolRegistry":
        """
        Merge another registry's tools into this one.

        Existing tools are NOT overwritten.

        Args:
            other: Registry to merge from

        Returns:
            Self for chaining
        """
        for name, tool in other._tools.items():
            if name not in self._tools:
                self._tools[name] = tool
        return self

    # =========================================================================
    # Context Management
    # =========================================================================

    def set_context(self, **kwargs) -> "ToolRegistry":
        """
        Set context values to inject into tool calls.

        Args:
            **kwargs: Context key-value pairs

        Returns:
            Self for chaining

        Example:
            registry.set_context(
                user_id="user123",
                session_id="sess456",
            )
        """
        self._context.update(kwargs)
        return self

    def update_context(self, updates: dict[str, Any]) -> None:
        """
        Update context values.

        Use this to sync context mid-execution.

        Args:
            updates: Context updates
        """
        self._context.update(updates)

    def get_context(self) -> dict[str, Any]:
        """Get current context (copy)."""
        return self._context.copy()

    # =========================================================================
    # Context Injection
    # =========================================================================

    def should_inject_context(self, tool_name: str) -> bool:
        """
        Check if tool should receive context injection.

        Args:
            tool_name: Name of the tool to check

        Returns:
            bool: False if tool matches SKIP_CONTEXT_TOOLS or SKIP_CONTEXT_PREFIXES,
                  True otherwise

        Example:
            # Exact match
            registry.should_inject_context("complete_task")  # False

            # Prefix match
            registry.should_inject_context("transfer_to_researcher")  # False
            registry.should_inject_context("transfer_to_writer")  # False

            # Regular tool
            registry.should_inject_context("search_documents")  # True
        """
        # Check exact match
        if tool_name in self.SKIP_CONTEXT_TOOLS:
            return False

        # Check prefix match
        for prefix in self.SKIP_CONTEXT_PREFIXES:
            if tool_name.startswith(prefix):
                return False

        return True

    def inject_context(self, tool: BaseTool, args: dict) -> dict:
        """
        Inject context values into tool args.

        Only injects values that match tool parameter names and
        aren't already provided in args. Validates that required
        context parameters are available.

        Args:
            tool: The tool being called
            args: Arguments provided by LLM

        Returns:
            Args with context values injected

        Raises:
            ValueError: If a required context parameter is missing

        Example:
            # Tool expects: get_data(user_id: str, query: str)
            # Context has: user_id="user123"
            # LLM provides: query="search term"
            # Result: {user_id="user123", query="search term"}
        """
        if not self.should_inject_context(tool.name):
            return args

        # Get tool parameter names and required fields from schema
        tool_params: set[str] = set()
        required_params: set[str] = set()
        if hasattr(tool, "args_schema") and tool.args_schema:
            for field_name, field_info in tool.args_schema.model_fields.items():
                tool_params.add(field_name)
                if field_info.is_required() and field_info.default is None:
                    required_params.add(field_name)

        # Inject context values that match and aren't already provided
        injected = dict(args)
        for key, value in self._context.items():
            if key in tool_params and key not in injected:
                injected[key] = value
                logger.debug(
                    f"Injected context key '{key}' for tool '{tool.name}'"
                )

        # Validate that all required parameters are present
        missing_params = required_params - set(injected.keys())
        if missing_params:
            missing_str = ", ".join(sorted(missing_params))
            available_context = ", ".join(sorted(self._context.keys()))
            raise ValueError(
                f"Tool '{tool.name}' missing required parameters: {missing_str}. "
                f"These must be provided by the LLM or set in registry context. "
                f"Available context keys: {available_context or '(none)'}"
            )

        return injected

    def wrap_with_context(self, tool: BaseTool) -> BaseTool:
        """
        Wrap a tool to automatically inject context at call time.

        This creates a new tool that:
        1. Modifies the schema so context-injectable params are optional
        2. Filters out None/empty values (handles LLM quirks like Claude passing null)
        3. Injects context values for matching schema parameters
        4. Calls the original tool

        Args:
            tool: Tool to wrap

        Returns:
            Wrapped tool with context injection

        Example:
            registry.set_context(user_id="user123")
            wrapped = registry.wrap_with_context(my_tool)
            # When wrapped is called, user_id is auto-injected if in schema
        """
        registry = self
        original_tool = tool

        # Get the original callable
        if tool.coroutine:
            original_fn = tool.coroutine
            is_async = True
        elif hasattr(tool, "func") and tool.func:
            original_fn = tool.func
            is_async = False
        else:
            # Can't wrap - return as-is
            return tool

        # Build modified schema that EXCLUDES context-injectable params.
        # Context-injected fields (user_id, session_id, etc.) should never be
        # visible to the LLM -- they are injected from the request context at
        # call time by inject_context(). Keeping them in the original tool's
        # args_schema allows inject_context to match by field name.
        modified_schema = None
        if tool.args_schema:
            context_keys = set(self._context.keys())
            field_definitions = {}
            stripped_any = False

            for field_name, field_info in tool.args_schema.model_fields.items():
                original_annotation = field_info.annotation
                original_default = field_info.default
                field_desc = field_info.description or ""

                # Skip context-injectable fields -- they are injected at call
                # time, not provided by the LLM
                if field_name in context_keys:
                    stripped_any = True
                    continue

                # Keep original field definition
                if original_default is not None:
                    field_definitions[field_name] = (
                        original_annotation,
                        Field(default=original_default, description=field_desc),
                    )
                elif field_info.is_required():
                    field_definitions[field_name] = (
                        original_annotation,
                        Field(description=field_desc),
                    )
                else:
                    field_definitions[field_name] = (
                        original_annotation,
                        Field(default=None, description=field_desc),
                    )

            if stripped_any:
                modified_schema = create_model(
                    f"{tool.name}_wrapped_args",
                    **field_definitions,
                )

        if is_async:

            async def wrapped_async(**kwargs) -> Any:
                # Step 1: Filter out None/empty values (LLM quirk handling)
                filtered = {
                    k: v for k, v in kwargs.items() if v is not None and v != ""
                }
                # Step 2: Inject context
                injected = registry.inject_context(original_tool, filtered)

                # Debug logging for context injection
                injected_keys = set(injected.keys()) - set(filtered.keys())
                if injected_keys:
                    logger.debug(
                        f"Context injection for tool '{original_tool.name}': {injected_keys}"
                    )

                # Step 3: Call original
                return await original_fn(**injected)

            return StructuredTool(
                name=tool.name,
                description=tool.description,
                coroutine=wrapped_async,
                args_schema=modified_schema or tool.args_schema,
                return_direct=getattr(tool, "return_direct", False),
            )
        else:

            def wrapped_sync(**kwargs) -> Any:
                # Step 1: Filter out None/empty values
                filtered = {
                    k: v for k, v in kwargs.items() if v is not None and v != ""
                }
                # Step 2: Inject context
                injected = registry.inject_context(original_tool, filtered)

                # Debug logging for context injection
                injected_keys = set(injected.keys()) - set(filtered.keys())
                if injected_keys:
                    logger.debug(
                        f"Context injection for tool '{original_tool.name}': {injected_keys}"
                    )

                # Step 3: Call original
                return original_fn(**injected)

            return StructuredTool(
                name=tool.name,
                description=tool.description,
                func=wrapped_sync,
                args_schema=modified_schema or tool.args_schema,
                return_direct=getattr(tool, "return_direct", False),
            )

    # =========================================================================
    # Magic Methods
    # =========================================================================

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())
