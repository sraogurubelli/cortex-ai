"""Tests for conversation serialization and history dumping."""

import json
import os
import tempfile

import pytest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from cortex.orchestration.observability.conversation import (
    dump_conversation_history,
    serialize_message,
    serialize_messages,
)


@pytest.mark.unit
class TestSerializeMessage:
    """Tests for serialize_message()."""

    def test_human_message(self):
        msg = HumanMessage(content="Hello")
        data = serialize_message(msg)

        assert data["type"] == "human"
        assert data["content"] == "Hello"

    def test_ai_message_with_content(self):
        msg = AIMessage(content="World")
        data = serialize_message(msg)

        assert data["type"] == "ai"
        assert data["content"] == "World"

    def test_ai_message_with_tool_calls(self):
        msg = AIMessage(
            content="",
            tool_calls=[
                {"id": "call_1", "name": "search", "args": {"q": "test"}},
            ],
        )
        data = serialize_message(msg)

        assert "tool_calls" in data
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["name"] == "search"

    def test_tool_message(self):
        msg = ToolMessage(content="result data", tool_call_id="call_1", name="search")
        data = serialize_message(msg)

        assert data["type"] == "tool"
        assert data["tool_call_id"] == "call_1"
        assert data["name"] == "search"
        assert data["content"] == "result data"

    def test_ai_message_with_list_content(self):
        msg = AIMessage(content=[{"type": "text", "text": "hello"}, "plain"])
        data = serialize_message(msg)

        assert isinstance(data["content"], list)
        assert len(data["content"]) == 2


@pytest.mark.unit
class TestSerializeMessages:
    """Tests for serialize_messages()."""

    def test_batch_serialization(self):
        messages = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello!"),
        ]
        result = serialize_messages(messages)

        assert len(result) == 2
        assert result[0]["type"] == "human"
        assert result[1]["type"] == "ai"


@pytest.mark.unit
class TestDumpConversationHistory:
    """Tests for dump_conversation_history()."""

    def test_dump_writes_valid_json(self):
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = dump_conversation_history(
                messages,
                metadata={"model": "gpt-4o"},
                output_dir=tmpdir,
            )

            assert path is not None
            assert os.path.exists(path)

            with open(path, "r") as f:
                data = json.load(f)

            assert data["message_count"] == 2
            assert data["execution_context"]["model"] == "gpt-4o"
            assert len(data["messages"]) == 2

    def test_dump_without_metadata(self):
        messages = [HumanMessage(content="Test")]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = dump_conversation_history(messages, output_dir=tmpdir)

            assert path is not None
            with open(path, "r") as f:
                data = json.load(f)

            assert "execution_context" not in data
