"""Tests for the Jinja2 PromptRegistry."""

import pytest

from cortex.prompts.registry import PromptRegistry


@pytest.fixture
def registry():
    """Fresh registry for each test (not the module-level singleton)."""
    reg = PromptRegistry()
    reg._initialized = False
    return reg


@pytest.mark.unit
class TestPromptRegistry:
    """Tests for PromptRegistry core functionality."""

    def test_auto_discovery_loads_chat_prompts(self, registry: PromptRegistry):
        registry.initialize()

        keys = registry.list_keys()
        assert "chat.system" in keys
        assert "chat.rag_context" in keys
        assert "chat.summarize_conversation" in keys

    def test_get_prompt_renders_variables(self, registry: PromptRegistry):
        registry.initialize()

        result = registry.get("chat.system", agent_name="TestBot")
        assert "TestBot" in result

    def test_get_prompt_raises_on_missing_key(self, registry: PromptRegistry):
        registry.initialize()

        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent.key")

    def test_register_prompt_at_runtime(self, registry: PromptRegistry):
        registry.initialize()
        registry.register("custom.greeting", "Hello, {{ name }}!")

        result = registry.get("custom.greeting", name="World")
        assert result == "Hello, World!"

    def test_has_key(self, registry: PromptRegistry):
        registry.initialize()

        assert registry.has("chat.system") is True
        assert registry.has("nonexistent") is False

    def test_include_resolution(self, registry: PromptRegistry):
        registry.initialize()
        registry.register("base.header", "=== HEADER ===")
        registry.register(
            "composed.report",
            '{% include "base.header" %}\n\nReport body for {{ topic }}.',
        )

        result = registry.get("composed.report", topic="testing")
        assert "=== HEADER ===" in result
        assert "testing" in result

    def test_reset_clears_state(self, registry: PromptRegistry):
        registry.initialize()
        assert len(registry.list_keys()) > 0

        registry.reset()
        assert registry._initialized is False
        assert len(registry._prompts) == 0

    def test_get_status(self, registry: PromptRegistry):
        status = registry.get_status()
        assert "initialized" in status
        assert "prompt_count" in status

    def test_initialize_is_idempotent(self, registry: PromptRegistry):
        registry.initialize()
        count_first = len(registry.list_keys())

        registry.initialize()
        count_second = len(registry.list_keys())

        assert count_first == count_second

    def test_conditional_rendering(self, registry: PromptRegistry):
        registry.initialize()

        # Without project_context — conditional block should be omitted
        result_no_ctx = registry.get("chat.system", agent_name="Bot")
        assert "Project context" not in result_no_ctx

        # With project_context — conditional block should render
        result_with_ctx = registry.get(
            "chat.system", agent_name="Bot", project_context="Sales analysis"
        )
        assert "Sales analysis" in result_with_ctx
