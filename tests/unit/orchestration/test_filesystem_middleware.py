"""Tests for FilesystemMiddleware."""

import pytest

from cortex.orchestration.filesystem.middleware import (
    FilesystemMiddleware,
    get_filesystem_prompt,
)
from cortex.orchestration.middleware.base import MiddlewareContext


@pytest.mark.unit
class TestFilesystemMiddleware:
    """Tests for large-result eviction logic."""

    @pytest.mark.asyncio
    async def test_small_result_passes_through(self):
        mw = FilesystemMiddleware(char_limit_before_evict=100)
        result = await mw.after_tool_call("search", "short result")
        assert result == "short result"

    @pytest.mark.asyncio
    async def test_large_result_is_evicted(self):
        mw = FilesystemMiddleware(char_limit_before_evict=50, preview_length=20)
        large_text = "x" * 200
        ctx = MiddlewareContext(agent_name="researcher")

        result = await mw.after_tool_call("big_tool", large_text, context=ctx)

        assert "saved to" in result.lower()
        assert "/large_tool_results/" in result
        assert len(result) < len(large_text)

    @pytest.mark.asyncio
    async def test_evicted_file_in_pending(self):
        mw = FilesystemMiddleware(char_limit_before_evict=50, preview_length=10)
        large_text = "y" * 200

        await mw.after_tool_call("tool_a", large_text)

        pending = mw.pop_pending_files()
        assert len(pending) == 1

        path = list(pending.keys())[0]
        assert path.startswith("/large_tool_results/tool_a_")
        assert pending[path] == large_text

    @pytest.mark.asyncio
    async def test_pop_pending_clears(self):
        mw = FilesystemMiddleware(char_limit_before_evict=10)
        await mw.after_tool_call("t", "z" * 100)

        first = mw.pop_pending_files()
        assert len(first) == 1

        second = mw.pop_pending_files()
        assert len(second) == 0

    @pytest.mark.asyncio
    async def test_handoff_tools_bypass(self):
        mw = FilesystemMiddleware(char_limit_before_evict=10)
        large_text = "a" * 100

        result = await mw.after_tool_call("transfer_to_writer", large_text)
        assert result == large_text
        assert len(mw.pop_pending_files()) == 0

    @pytest.mark.asyncio
    async def test_disabled_middleware(self):
        mw = FilesystemMiddleware(char_limit_before_evict=10, enabled=False)
        large_text = "b" * 100

        result = await mw.after_tool_call("tool", large_text)
        assert result == large_text


@pytest.mark.unit
class TestGetFilesystemPrompt:
    """Tests for the filesystem agent prompt builder."""

    def test_prompt_contains_agent_name(self):
        prompt = get_filesystem_prompt("researcher")
        assert "/researcher/" in prompt

    def test_prompt_contains_guidance(self):
        prompt = get_filesystem_prompt("agent")
        assert "large_tool_results" in prompt.lower()
        assert "shared filesystem" in prompt.lower()
