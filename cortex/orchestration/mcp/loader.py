"""MCP Server Loader for loading tools from MCP servers.

Requires additional dependencies:
    pip install mcp langchain-mcp-adapters

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, Union

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


# =============================================================================
# Progress Notification Support
# =============================================================================


class ProgressNotificationCallback(Protocol):
    """Protocol for progress notification callbacks."""

    async def __call__(self, params: Any) -> None:
        """Handle a progress notification from MCP server."""
        ...


async def _default_progress_callback(params: Any) -> None:
    """Default no-op progress callback."""
    pass


# =============================================================================
# Configuration Classes
# =============================================================================


@dataclass
class MCPHttpConfig:
    """Configuration for HTTP-based MCP server (uses StreamableHTTP)."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    sse_read_timeout: float = 300.0
    terminate_on_close: bool = True


@dataclass
class MCPStdioConfig:
    """Configuration for stdio-based MCP server (spawns binary)."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    read_timeout: float = 300.0


# Union type for either config
MCPServerConfig = Union[MCPHttpConfig, MCPStdioConfig]


# =============================================================================
# MCP Loader
# =============================================================================


class MCPLoader:
    """
    Load tools from MCP servers.

    Supports both HTTP (StreamableHTTP) and stdio transports.
    Includes progress notification support for streaming updates.

    Requires: pip install mcp langchain-mcp-adapters

    Example (HTTP):
        config = MCPHttpConfig(url="http://localhost:8080")
        async with MCPLoader(config) as loader:
            tools = await loader.load_tools()

    Example (stdio):
        config = MCPStdioConfig(
            command="/path/to/mcp-server",
            args=["stdio"],
            env={"API_KEY": "..."},
        )

        async def on_progress(params):
            print(f"Progress: {params}")

        loader = MCPLoader(config, progress_callback=on_progress)
        async with loader:
            tools = await loader.load_tools()

    Example (from MCPConfig):
        from cortex.orchestration.mcp import HTTPMCPConfig, MCPAuth

        config = HTTPMCPConfig(
            name="custom_mcp",
            url="https://mcp.example.com/v1",
            auth_type=MCPAuth.BEARER_TOKEN,
            token="my_token",
        )

        loader = MCPLoader.from_config(config)
        async with loader:
            tools = await loader.load_tools()
    """

    def __init__(
        self,
        config: MCPServerConfig,
        progress_callback: ProgressNotificationCallback | None = None,
    ):
        self.config = config
        self._progress_callback = progress_callback or _default_progress_callback
        self._tools_cache: list[BaseTool] = []
        self._session: Any = None
        self._started = False
        self._transport_context = None

    @classmethod
    def from_config(
        cls,
        config: Any,  # MCPConfig type
        progress_callback: ProgressNotificationCallback | None = None,
        headers: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
    ) -> "MCPLoader":
        """
        Create an MCPLoader from an MCPConfig.

        Args:
            config: MCPConfig instance (HTTPMCPConfig, STDIOMCPConfig, etc.)
            progress_callback: Optional callback for progress notifications
            headers: Additional headers (HTTP only, merged with config headers)
            env: Additional env vars (stdio only, merged with config env)

        Returns:
            Configured MCPLoader instance
        """
        from cortex.orchestration.mcp.config import MCPTransport

        # Validate config first
        config.validate()

        # Convert to internal config format based on transport type
        if config.transport == MCPTransport.STDIO:
            # Merge environment variables
            merged_env = dict(config.env or {})
            if env:
                merged_env.update(env)

            internal_config = MCPStdioConfig(
                command=config.command,
                args=config.args or [],
                env=merged_env,
                read_timeout=config.sse_read_timeout,
            )
        else:
            # HTTP or SSE transport
            merged_headers = config._get_auth_headers()
            if headers:
                merged_headers.update(headers)

            internal_config = MCPHttpConfig(
                url=config.url,
                headers=merged_headers,
                timeout=config.timeout,
                sse_read_timeout=config.sse_read_timeout,
            )

        return cls(internal_config, progress_callback=progress_callback)

    @property
    def is_http(self) -> bool:
        """Check if this is an HTTP transport."""
        return isinstance(self.config, MCPHttpConfig)

    @property
    def is_stdio(self) -> bool:
        """Check if this is a stdio transport."""
        return isinstance(self.config, MCPStdioConfig)

    async def __aenter__(self) -> "MCPLoader":
        """Start MCP session."""
        await self._start()
        return self

    async def __aexit__(self, *args) -> None:
        """Close MCP session."""
        await self._stop()

    async def _start(self) -> None:
        """Initialize connection to MCP server."""
        if self._started:
            return

        try:
            if self.is_stdio:
                await self._start_stdio()
            else:
                await self._start_http()

            self._started = True
            transport_type = "stdio" if self.is_stdio else "http"
            logger.info(f"MCP session started ({transport_type})")

        except ImportError as e:
            logger.error(f"MCP library not available: {e}")
            raise RuntimeError(
                "mcp and langchain-mcp-adapters required. "
                "Install with: pip install mcp langchain-mcp-adapters"
            ) from e
        except Exception as e:
            logger.error(f"Failed to start MCP session: {e}")
            raise

    async def _start_stdio(self) -> None:
        """Start stdio transport."""
        from datetime import timedelta

        import mcp.client.stdio as stdio

        assert isinstance(self.config, MCPStdioConfig)

        # Create stdio transport
        read_stream, write_stream = stdio.stdio_client(
            self.config.command,
            args=self.config.args,
            env=self.config.env,
        )

        # Store transport context for cleanup
        self._transport_context = (read_stream, write_stream)

        # Create custom session with progress support
        from cortex.orchestration.mcp._session import CustomClientSession

        self._session = CustomClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=self.config.read_timeout),
            progress_notification_callback=self._progress_callback,
        )

        # Initialize session
        async with self._session as session:
            await session.initialize()

    async def _start_http(self) -> None:
        """Start HTTP transport."""
        from datetime import timedelta

        from langchain_mcp_adapters.client import StreamableHTTPClient

        assert isinstance(self.config, MCPHttpConfig)

        # Create HTTP transport
        read_stream, write_stream = StreamableHTTPClient(
            url=self.config.url,
            headers=self.config.headers,
            timeout=self.config.timeout,
            sse_read_timeout=timedelta(seconds=self.config.sse_read_timeout),
        )

        # Store transport context
        self._transport_context = (read_stream, write_stream)

        # Create custom session with progress support
        from cortex.orchestration.mcp._session import CustomClientSession

        self._session = CustomClientSession(
            read_stream,
            write_stream,
            progress_notification_callback=self._progress_callback,
        )

        # Initialize session
        async with self._session as session:
            await session.initialize()

    async def _stop(self) -> None:
        """Close MCP session."""
        if not self._started:
            return

        try:
            if self._session:
                # Session cleanup handled by context manager
                pass

            # Cleanup transport-specific resources
            if self._transport_context:
                read_stream, write_stream = self._transport_context
                # Cleanup depends on transport type
                # For stdio, streams are auto-closed
                # For HTTP, context managers handle cleanup
                self._transport_context = None

            self._started = False
            logger.info("MCP session closed")

        except Exception as e:
            logger.warning(f"Error closing MCP session: {e}")

    async def load_tools(self) -> list[BaseTool]:
        """
        Load tools from the MCP server.

        Returns:
            List of LangChain tools

        Raises:
            RuntimeError: If session not started
        """
        if not self._started or not self._session:
            raise RuntimeError("MCP session not started. Use 'async with loader:'")

        # Check cache
        if self._tools_cache:
            return self._tools_cache

        try:
            # List available tools from MCP server
            tools_list = await self._session.list_tools()

            # Convert MCP tools to LangChain tools
            tools = []
            for mcp_tool in tools_list.tools:
                langchain_tool = self._convert_to_langchain_tool(mcp_tool)
                tools.append(langchain_tool)

            # Cache the tools
            self._tools_cache = tools

            logger.info(f"Loaded {len(tools)} tools from MCP server")
            return tools

        except Exception as e:
            logger.error(f"Failed to load tools from MCP server: {e}")
            raise

    def _convert_to_langchain_tool(self, mcp_tool: Any) -> BaseTool:
        """Convert MCP tool to LangChain tool."""
        from langchain_core.tools import StructuredTool
        from pydantic import create_model, Field

        # Extract tool info
        tool_name = mcp_tool.name
        tool_description = mcp_tool.description or ""

        # Build Pydantic schema from MCP input schema
        if hasattr(mcp_tool, "inputSchema"):
            schema_dict = mcp_tool.inputSchema
            properties = schema_dict.get("properties", {})
            required = schema_dict.get("required", [])

            # Build field definitions for Pydantic model
            field_definitions = {}
            for field_name, field_spec in properties.items():
                field_type = field_spec.get("type", "string")
                field_desc = field_spec.get("description", "")
                is_required = field_name in required

                # Map JSON schema types to Python types
                python_type = str  # Default
                if field_type == "number":
                    python_type = float
                elif field_type == "integer":
                    python_type = int
                elif field_type == "boolean":
                    python_type = bool

                if is_required:
                    field_definitions[field_name] = (
                        python_type,
                        Field(..., description=field_desc),
                    )
                else:
                    field_definitions[field_name] = (
                        python_type | None,
                        Field(None, description=field_desc),
                    )

            # Create Pydantic model
            args_schema = create_model(
                f"{tool_name}_args",
                **field_definitions,
            )
        else:
            args_schema = None

        # Create async wrapper for tool execution
        async def execute_tool(**kwargs) -> str:
            """Execute the MCP tool."""
            if not self._session:
                raise RuntimeError("MCP session not active")

            result = await self._session.call_tool(tool_name, arguments=kwargs)

            # Extract content from result
            if hasattr(result, "content") and result.content:
                # Handle multiple content blocks
                text_parts = []
                for content_item in result.content:
                    if hasattr(content_item, "text"):
                        text_parts.append(content_item.text)
                return "\n".join(text_parts)

            return str(result)

        # Create LangChain tool
        return StructuredTool(
            name=tool_name,
            description=tool_description,
            coroutine=execute_tool,
            args_schema=args_schema,
        )
