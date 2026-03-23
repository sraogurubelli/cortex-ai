"""Tests for MessageTrimmingMiddleware and create_summarization_middleware."""

import pytest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from cortex.orchestration.middleware.summarization import (
    MessageTrimmingMiddleware,
    create_summarization_middleware,
)


@pytest.mark.unit
class TestMessageTrimmingMiddleware:
    """Unit tests for deterministic message trimming."""

    def _make_messages(self, n: int, *, with_system: bool = True) -> list:
        msgs = []
        if with_system:
            msgs.append(SystemMessage(content="System prompt"))
        msgs.append(HumanMessage(content="First user question"))
        for i in range(n):
            msgs.append(AIMessage(content=f"Response {i}"))
            msgs.append(HumanMessage(content=f"Follow-up {i}"))
        return msgs

    def test_no_trim_when_under_threshold(self):
        mw = MessageTrimmingMiddleware(max_messages=50, keep_recent=10)
        messages = self._make_messages(5)
        result = mw._trim(messages)
        assert result is messages

    def test_trim_preserves_system_and_first_user(self):
        mw = MessageTrimmingMiddleware(max_messages=10, keep_recent=4)
        messages = self._make_messages(20)
        trimmed = mw._trim(messages)

        assert isinstance(trimmed[0], SystemMessage)
        assert trimmed[0].content == "System prompt"
        assert isinstance(trimmed[1], HumanMessage)
        assert trimmed[1].content == "First user question"

    def test_trim_inserts_marker(self):
        mw = MessageTrimmingMiddleware(max_messages=10, keep_recent=4)
        messages = self._make_messages(20)
        trimmed = mw._trim(messages)

        marker = trimmed[2]
        assert isinstance(marker, AIMessage)
        assert "trimmed" in marker.content.lower()

    def test_trim_keeps_recent_messages(self):
        mw = MessageTrimmingMiddleware(max_messages=10, keep_recent=4)
        messages = self._make_messages(20)
        trimmed = mw._trim(messages)

        # System + first_user + marker + 4 recent = 7
        assert len(trimmed) == 7
        assert trimmed[-1] == messages[-1]
        assert trimmed[-4:] == messages[-4:]

    def test_trim_without_system_message(self):
        mw = MessageTrimmingMiddleware(max_messages=5, keep_recent=2)
        messages = self._make_messages(10, with_system=False)
        trimmed = mw._trim(messages)

        assert isinstance(trimmed[0], HumanMessage)
        assert trimmed[0].content == "First user question"
        assert any("trimmed" in m.content.lower() for m in trimmed if isinstance(m, AIMessage))

    def test_before_model_returns_none_when_under_limit(self):
        mw = MessageTrimmingMiddleware(max_messages=100, keep_recent=10)
        state = {"messages": self._make_messages(5)}
        assert mw.before_model(state) is None

    def test_before_model_returns_trimmed_when_over_limit(self):
        mw = MessageTrimmingMiddleware(max_messages=10, keep_recent=4)
        messages = self._make_messages(20)
        state = {"messages": messages}
        result = mw.before_model(state)

        assert result is not None
        assert len(result["messages"]) < len(messages)

    @pytest.mark.asyncio
    async def test_abefore_model_delegates_to_sync(self):
        mw = MessageTrimmingMiddleware(max_messages=10, keep_recent=4)
        messages = self._make_messages(20)
        state = {"messages": messages}
        result = await mw.abefore_model(state)

        assert result is not None
        assert len(result["messages"]) < len(messages)


@pytest.mark.unit
class TestCreateSummarizationMiddleware:
    """Tests for the factory function."""

    def test_trim_strategy_returns_trimming_middleware(self):
        mw = create_summarization_middleware(strategy="trim", keep_messages=10)
        assert isinstance(mw, MessageTrimmingMiddleware)

    def test_summarize_strategy_without_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            create_summarization_middleware(strategy="summarize")

    def test_summarize_strategy_with_mock_model(self):
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mw = create_summarization_middleware(
            strategy="summarize", model=mock_model
        )
        assert mw is not None
