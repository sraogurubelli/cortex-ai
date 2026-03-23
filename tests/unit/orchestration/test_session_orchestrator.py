"""Unit tests for SessionOrchestrator."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool

from cortex.orchestration.session.orchestrator import SessionConfig, SessionOrchestrator
from cortex.orchestration.tools import ToolRegistry


def _dummy_tool(name: str = "dummy") -> StructuredTool:
    def _fn(x: str = "") -> str:
        return "ok"

    return StructuredTool.from_function(_fn, name=name, description="test")


@pytest.mark.unit
class TestSessionOrchestratorInit:
    def test_initialization_creates_tool_registry(self):
        orch = SessionOrchestrator()
        assert isinstance(orch._tool_registry, ToolRegistry)


@pytest.mark.unit
class TestSessionOrchestratorLoadTools:
    @pytest.mark.asyncio
    async def test_load_tools_skips_registry_when_use_tools_false(self):
        orch = SessionOrchestrator()
        mock_reg = MagicMock(spec=ToolRegistry)
        orch._tool_registry = mock_reg
        extra = _dummy_tool("extra")
        cfg = SessionConfig(use_tools=False, extra_tools=[extra])
        tools = await orch._load_tools(cfg)
        mock_reg.set_context.assert_not_called()
        mock_reg.all.assert_not_called()
        assert tools == [extra]

    @pytest.mark.asyncio
    async def test_load_tools_uses_registry_and_extra_tools(self):
        orch = SessionOrchestrator()
        reg = ToolRegistry()
        t1 = _dummy_tool("one")
        reg.register(t1)
        orch._tool_registry = reg
        t2 = _dummy_tool("two")
        cfg = SessionConfig(
            use_tools=True,
            tenant_id="t1",
            project_id="p1",
            extra_tools=[t2],
        )
        tools = await orch._load_tools(cfg)
        assert [x.name for x in tools] == ["one", "two"]

@pytest.mark.unit
class TestSessionOrchestratorBuildAgent:
    def test_build_agent_passes_config_to_agent(self):
        orch = SessionOrchestrator()
        tools = [_dummy_tool()]
        cfg = SessionConfig(
            agent_name="sales",
            model="gpt-4o",
            temperature=0.3,
            system_prompt="Be brief.",
            max_iterations=10,
        )
        mock_agent = MagicMock()
        with patch("cortex.orchestration.Agent", return_value=mock_agent) as AgentCls:
            agent = orch._build_agent(cfg, tools)
        assert agent is mock_agent
        mock_agent.add_middleware.assert_not_called()
        AgentCls.assert_called_once()
        call_kw = AgentCls.call_args[1]
        assert call_kw["name"] == "sales"
        assert call_kw["system_prompt"] == "Be brief."
        assert call_kw["tools"] is tools
        assert call_kw["max_iterations"] == 10
        mc = call_kw["model"]
        assert mc.model == "gpt-4o"
        assert mc.temperature == 0.3

    def test_build_agent_skills_merges_skill_context_into_prompt(self):
        orch = SessionOrchestrator()
        cfg = SessionConfig(
            use_skills=True,
            system_prompt="Base.",
            skills_category=None,
        )
        mock_agent = MagicMock()
        mock_agent.system_prompt = "Base."
        with patch("cortex.orchestration.Agent", return_value=mock_agent):
            with patch(
                "cortex.orchestration.skills.middleware.SkillsMiddleware",
            ) as SM:
                SM.return_value.get_skill_context.return_value = "<skills>ctx</skills>"
                orch._build_agent(cfg, [])
        assert "Base." in mock_agent.system_prompt
        assert "<skills>ctx</skills>" in mock_agent.system_prompt
        SM.assert_called_once_with(category=None)
