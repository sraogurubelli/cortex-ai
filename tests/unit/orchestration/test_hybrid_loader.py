"""Unit tests for HybridToolLoader."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool

from cortex.orchestration.mcp.hybrid_loader import HybridToolLoader
from cortex.orchestration.tools import ToolRegistry


def _tool(name: str) -> StructuredTool:
    def _fn() -> str:
        return name

    return StructuredTool.from_function(_fn, name=name, description=name)


@pytest.mark.unit
class TestHybridToolLoader:
    @pytest.mark.asyncio
    async def test_load_local_only_no_endpoints(self):
        reg = ToolRegistry()
        reg.register(_tool("alpha"))
        loader = HybridToolLoader(local_registry=reg, mcp_endpoints=[])
        tools = await loader.load_all()
        assert len(tools) == 1
        assert tools[0].name == "alpha"

    @pytest.mark.asyncio
    async def test_merges_local_and_remote(self):
        reg = ToolRegistry()
        reg.register(_tool("local_only"))
        remote = _tool("remote_only")
        mock_gw = MagicMock()
        mock_gw.list_langchain_tools = AsyncMock(return_value=[remote])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_gw)
        cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "cortex.orchestration.mcp.rest_gateway.RestToolGateway",
            return_value=cm,
        ):
            loader = HybridToolLoader(
                local_registry=reg,
                mcp_endpoints=["http://mcp.example/tools"],
            )
            tools = await loader.load_all()

        names = {t.name for t in tools}
        assert names == {"local_only", "remote_only"}

    @pytest.mark.asyncio
    async def test_deduplication_local_takes_precedence(self):
        reg = ToolRegistry()
        reg.register(_tool("shared"))
        remote_same = _tool("shared")
        mock_gw = MagicMock()
        mock_gw.list_langchain_tools = AsyncMock(return_value=[remote_same])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_gw)
        cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "cortex.orchestration.mcp.rest_gateway.RestToolGateway",
            return_value=cm,
        ):
            loader = HybridToolLoader(
                local_registry=reg,
                mcp_endpoints=["http://mcp.example"],
            )
            tools = await loader.load_all()

        assert [t.name for t in tools] == ["shared"]
        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_set_context_passed_to_registry(self):
        reg = ToolRegistry()
        reg.register(_tool("ctx"))
        with patch.object(reg, "set_context", wraps=reg.set_context) as spy:
            loader = HybridToolLoader(
                local_registry=reg,
                mcp_endpoints=[],
                context={"tenant_id": "t1", "project_id": "p1"},
            )
            await loader.load_all()
        spy.assert_called_once_with(tenant_id="t1", project_id="p1")
