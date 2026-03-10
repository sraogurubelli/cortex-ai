"""
MCP (Model Context Protocol) Support

Provides configuration and loading for MCP servers to extend agent capabilities
with external tools.
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
]
