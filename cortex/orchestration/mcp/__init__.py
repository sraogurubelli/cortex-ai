"""
MCP (Model Context Protocol) Support

Provides configuration, loading, and a named server registry for MCP servers
to extend agent capabilities with external tools.
"""

from .config import (
    HTTPMCPConfig,
    MCPAuth,
    MCPConfig,
    MCPTransport,
    SSEMCPConfig,
    STDIOMCPConfig,
)
from .loader import MCPLoader
from .registry import MCPServerRegistry, mcp_server_registry
from .rest_gateway import RestToolGateway
from .hybrid_loader import HybridToolLoader

__all__ = [
    # Config
    "MCPConfig",
    "HTTPMCPConfig",
    "SSEMCPConfig",
    "STDIOMCPConfig",
    "MCPTransport",
    "MCPAuth",
    # Loader
    "MCPLoader",
    # Registry
    "MCPServerRegistry",
    "mcp_server_registry",
    # REST Gateway
    "RestToolGateway",
    # Hybrid Loader
    "HybridToolLoader",
]
