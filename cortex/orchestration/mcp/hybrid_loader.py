"""
HybridToolLoader — merges local ToolRegistry tools with MCP remote tools.

Provides a unified tool set that combines locally registered Python
tools with tools discovered from remote MCP-compatible REST endpoints.

Usage::

    loader = HybridToolLoader(
        local_registry=my_registry,
        mcp_endpoints=["http://localhost:8080", "http://tools.internal:9090"],
    )
    tools = await loader.load_all()
"""

import logging
from typing import Any, Optional

from langchain_core.tools import BaseTool

from cortex.orchestration.tools import ToolRegistry

logger = logging.getLogger(__name__)


class HybridToolLoader:
    """Merges local ToolRegistry tools with remote MCP tools.

    Local tools take precedence: if a local tool and a remote tool share
    the same name, the local tool is kept and the remote one is skipped.
    """

    def __init__(
        self,
        local_registry: Optional[ToolRegistry] = None,
        mcp_endpoints: Optional[list[str]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        self._local_registry = local_registry or ToolRegistry()
        self._mcp_endpoints = mcp_endpoints or []
        self._context = context or {}

    async def load_all(self) -> list[BaseTool]:
        """Load tools from both local registry and MCP endpoints.

        Returns a deduplicated list: local tools first, then remote tools
        whose names don't conflict with local ones.
        """
        if self._context:
            self._local_registry.set_context(**self._context)

        local_tools = self._local_registry.all()
        local_names = {t.name for t in local_tools}

        remote_tools: list[BaseTool] = []
        for endpoint in self._mcp_endpoints:
            try:
                from cortex.orchestration.mcp.rest_gateway import RestToolGateway

                async with RestToolGateway(endpoint) as gw:
                    tools = await gw.list_langchain_tools()
                    for tool in tools:
                        if tool.name in local_names:
                            logger.debug(
                                "Skipping remote tool '%s' from %s (local override exists)",
                                tool.name, endpoint,
                            )
                        else:
                            remote_tools.append(tool)
                            local_names.add(tool.name)
            except Exception:
                logger.warning(
                    "Failed to load MCP tools from %s", endpoint, exc_info=True,
                )

        all_tools = local_tools + remote_tools
        logger.info(
            "HybridToolLoader: %d local + %d remote = %d total tools",
            len(local_tools), len(remote_tools), len(all_tools),
        )
        return all_tools

    async def load_remote_only(self) -> list[BaseTool]:
        """Load only remote MCP tools (skipping local registry)."""
        remote_tools: list[BaseTool] = []
        seen_names: set[str] = set()

        for endpoint in self._mcp_endpoints:
            try:
                from cortex.orchestration.mcp.rest_gateway import RestToolGateway

                async with RestToolGateway(endpoint) as gw:
                    tools = await gw.list_langchain_tools()
                    for tool in tools:
                        if tool.name not in seen_names:
                            remote_tools.append(tool)
                            seen_names.add(tool.name)
            except Exception:
                logger.warning(
                    "Failed to load MCP tools from %s", endpoint, exc_info=True,
                )

        return remote_tools
