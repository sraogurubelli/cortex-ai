"""
MCP Configuration Classes

Provides base configuration classes for MCP servers with support for
different transport types and authentication methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MCPTransport(Enum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


class MCPAuth(Enum):
    """Supported MCP authentication types."""

    NONE = "none"
    BEARER_TOKEN = "bearer_token"
    API_KEY = "api_key"


@dataclass
class MCPConfig(ABC):
    """
    Base configuration class for MCP servers.

    This class provides the foundation for configuring MCP servers
    that will be used to provide tools to LangChain agents.

    Example:
        class CustomMCPConfig(HTTPMCPConfig):
            def __init__(self, token: str, **kwargs):
                super().__init__(
                    name="custom_mcp",
                    description="Custom MCP server",
                    url="https://mcp.example.com",
                    auth_type=MCPAuth.BEARER_TOKEN,
                    token=token,
                    **kwargs,
                )
    """

    name: str
    description: str = ""
    transport: MCPTransport = MCPTransport.HTTP
    auth_type: MCPAuth = MCPAuth.NONE

    # Connection settings
    url: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None

    # Authentication settings
    token: str | None = None
    api_key: str | None = None
    headers: dict[str, str] | None = None

    # Tool filtering
    enabled_tools: list[str] | None = None  # If None, all tools are enabled
    disabled_tools: list[str] | None = None

    # Connection options
    timeout: float = 30.0
    sse_read_timeout: float = 300.0

    @abstractmethod
    def get_client_config(self) -> dict[str, Any]:
        """
        Return the configuration dictionary for MCP client.

        Returns:
            Dict containing the connection configuration for langchain-mcp-adapters
        """
        pass

    def validate(self) -> bool:
        """
        Validate the configuration.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        if self.transport in [MCPTransport.HTTP, MCPTransport.SSE]:
            if not self.url:
                raise ValueError(
                    f"URL is required for {self.transport.value} transport"
                )

        elif self.transport == MCPTransport.STDIO:
            if not self.command:
                raise ValueError("Command is required for stdio transport")

        if self.auth_type == MCPAuth.BEARER_TOKEN and not self.token:
            raise ValueError("Token is required for bearer token authentication")

        if self.auth_type == MCPAuth.API_KEY and not self.api_key:
            raise ValueError("API key is required for API key authentication")

        return True

    def should_include_tool(self, tool_name: str) -> bool:
        """
        Determine if a tool should be included based on filtering configuration.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool should be included, False otherwise
        """
        if self.disabled_tools and tool_name in self.disabled_tools:
            return False

        if self.enabled_tools is not None and tool_name not in self.enabled_tools:
            return False

        return True

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers based on auth_type."""
        headers = dict(self.headers) if self.headers else {}

        if self.auth_type == MCPAuth.BEARER_TOKEN and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.auth_type == MCPAuth.API_KEY and self.api_key:
            headers["X-API-Key"] = self.api_key

        return headers


@dataclass
class HTTPMCPConfig(MCPConfig):
    """
    Configuration for HTTP-based MCP servers.

    Uses StreamableHTTP transport with langchain-mcp-adapters.

    Example:
        config = HTTPMCPConfig(
            name="custom_mcp",
            description="Custom MCP server",
            url="https://mcp.example.com/v1",
            auth_type=MCPAuth.BEARER_TOKEN,
            token="my_token",
        )
    """

    transport: MCPTransport = field(default=MCPTransport.HTTP, init=False)

    def get_client_config(self) -> dict[str, Any]:
        """Get configuration for MCP client."""
        self.validate()

        config: dict[str, Any] = {
            "transport": "streamable_http",
            "url": self.url,
            "timeout": self.timeout,
            "sse_read_timeout": self.sse_read_timeout,
        }

        headers = self._get_auth_headers()
        if headers:
            config["headers"] = headers

        return config


@dataclass
class SSEMCPConfig(MCPConfig):
    """
    Configuration for SSE-based MCP servers.

    Example:
        config = SSEMCPConfig(
            name="sse_server",
            url="https://sse.example.com/mcp",
        )
    """

    transport: MCPTransport = field(default=MCPTransport.SSE, init=False)

    def get_client_config(self) -> dict[str, Any]:
        """Get configuration for MCP client."""
        self.validate()

        config: dict[str, Any] = {
            "transport": "sse",
            "url": self.url,
        }

        headers = self._get_auth_headers()
        if headers:
            config["headers"] = headers

        return config


@dataclass
class STDIOMCPConfig(MCPConfig):
    """
    Configuration for stdio-based MCP servers (spawns binary).

    Example:
        config = STDIOMCPConfig(
            name="local_mcp",
            description="Local MCP via stdio",
            command="/path/to/mcp-server",
            args=["stdio"],
            env={"API_KEY": "..."},
        )
    """

    transport: MCPTransport = field(default=MCPTransport.STDIO, init=False)

    def get_client_config(self) -> dict[str, Any]:
        """Get configuration for MCP client."""
        self.validate()

        config: dict[str, Any] = {
            "transport": "stdio",
            "command": self.command,
            "args": self.args or [],
        }

        if self.env:
            config["env"] = self.env

        return config
