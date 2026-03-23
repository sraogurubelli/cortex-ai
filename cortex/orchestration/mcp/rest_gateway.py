"""
REST MCP Tool Gateway — LangChain-compatible client for MCP REST endpoints.

Discovers and invokes tools from any MCP-compatible REST gateway that exposes:
  - ``GET /api/tools``        → list available tools
  - ``POST /api/tools/invoke`` → invoke a tool by name

Ported from ml-infra agents/mcp/rest_gateway_workbench.py
(Autogen Workbench interface replaced with LangChain StructuredTool).

Usage::

    from cortex.orchestration.mcp.rest_gateway import RestToolGateway

    async with RestToolGateway("http://localhost:8080") as gw:
        tools = await gw.list_langchain_tools()
        # tools are LangChain StructuredTools usable by Agent
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


@dataclass
class RestGatewayConfig:
    """Configuration for a REST MCP Tool Gateway."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    additional_context: dict[str, Any] = field(default_factory=dict)


def _merge_context(
    args: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Merge additional context into tool arguments.

    Lists are concatenated; scalars from args take precedence.
    """
    merged = dict(args)
    for key, value in context.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(value, list) and isinstance(merged[key], list):
            merged[key] = merged[key] + value
    return merged


class RestToolGateway:
    """Client for discovering and calling tools via a REST MCP gateway.

    Implements async context manager for lifecycle management.
    """

    def __init__(self, config: RestGatewayConfig | str) -> None:
        if isinstance(config, str):
            config = RestGatewayConfig(url=config)
        self._config = config
        self._config.url = self._config.url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._tools_cache: Optional[list[dict]] = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._config.headers,
                timeout=self._config.timeout,
            )
            logger.info("REST Tool Gateway started: %s", self._config.url)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("REST Tool Gateway stopped")

    async def __aenter__(self) -> "RestToolGateway":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch tool schemas from the gateway.

        Returns:
            List of raw tool schema dicts (name, description, inputSchema).
        """
        if self._tools_cache is not None:
            return self._tools_cache

        if not self._client:
            await self.start()

        url = f"{self._config.url}/api/tools"
        resp = await self._client.get(url)  # type: ignore[union-attr]
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict):
            tools_data = data.get("tools", data.get("data", []))
        elif isinstance(data, list):
            tools_data = data
        else:
            raise ValueError(f"Unexpected response format: {type(data)}")

        self._tools_cache = tools_data
        logger.info("Discovered %d tools from gateway %s", len(tools_data), self._config.url)
        return tools_data

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke a tool via the gateway.

        Returns:
            The JSON response body as a dict.
        """
        if not self._client:
            await self.start()

        merged = _merge_context(arguments or {}, self._config.additional_context)
        url = f"{self._config.url}/api/tools/invoke"
        payload = {"tool_name": name, "arguments": merged}

        resp = await self._client.post(url, json=payload)  # type: ignore[union-attr]
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # LangChain integration
    # ------------------------------------------------------------------

    async def list_langchain_tools(self) -> list[StructuredTool]:
        """Convert gateway tools into LangChain StructuredTool instances.

        Each tool calls back to the gateway on invocation.
        """
        raw_tools = await self.list_tools()
        lc_tools: list[StructuredTool] = []

        for tool_data in raw_tools:
            tool_name = tool_data.get("name") or tool_data.get("tool_name", "unknown")
            description = tool_data.get("description", "")
            input_schema = (
                tool_data.get("inputSchema")
                or tool_data.get("input_schema")
                or tool_data.get("schema", {})
            )

            gateway = self

            async def _invoke(
                _name: str = tool_name,
                **kwargs: Any,
            ) -> str:
                result = await gateway.call_tool(_name, kwargs)
                content = result.get("content") or result.get("result") or result.get("data")
                if isinstance(content, list):
                    parts = [
                        item.get("text", str(item)) if isinstance(item, dict) else str(item)
                        for item in content
                    ]
                    return "\n".join(parts)
                if isinstance(content, str):
                    return content
                return json.dumps(content, indent=2) if content else json.dumps(result, indent=2)

            lc_tools.append(
                StructuredTool.from_function(
                    coroutine=_invoke,
                    name=tool_name,
                    description=description,
                    args_schema=None,
                )
            )

        return lc_tools

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def update_context(self, ctx: dict[str, Any]) -> None:
        self._config.additional_context.update(ctx)

    def invalidate_cache(self) -> None:
        self._tools_cache = None
