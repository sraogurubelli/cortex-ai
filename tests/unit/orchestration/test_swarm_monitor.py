"""Tests for SwarmMonitor JSONL event recorder."""

import json
import os
import tempfile

import pytest

from cortex.orchestration.observability.monitor import SwarmMonitor


@pytest.mark.unit
class TestSwarmMonitor:
    """Tests for SwarmMonitor."""

    def test_initial_turn_start_event(self):
        monitor = SwarmMonitor(conversation_id="conv-1", interaction_id="int-1")

        assert len(monitor._events) == 1
        assert monitor._events[0]["event"] == "turn_start"
        assert monitor._events[0]["data"]["conversation_id"] == "conv-1"

    def test_record_tool_start(self):
        monitor = SwarmMonitor(conversation_id="test")
        event = {
            "event": "on_tool_start",
            "name": "search",
            "data": {"input": {"query": "test"}},
        }
        monitor.record_event(event, source_agent="researcher")

        assert len(monitor._events) == 2
        assert monitor._events[1]["event"] == "on_tool_start"
        assert monitor._events[1]["agent"] == "researcher"

    def test_record_tool_end(self):
        monitor = SwarmMonitor(conversation_id="test")
        event = {
            "event": "on_tool_end",
            "name": "search",
            "data": {"output": "some results"},
        }
        monitor.record_event(event, source_agent="agent")

        recorded = [e for e in monitor._events if e["event"] == "on_tool_end"]
        assert len(recorded) == 1

    def test_skips_chat_model_stream(self):
        monitor = SwarmMonitor(conversation_id="test")
        event = {"event": "on_chat_model_stream", "data": {}}
        monitor.record_event(event)

        # Only turn_start should be present — stream events are skipped
        assert len(monitor._events) == 1

    def test_detects_handoff(self):
        monitor = SwarmMonitor(conversation_id="test")
        event = {
            "event": "on_tool_end",
            "name": "transfer_to_writer",
            "data": {"output": ""},
        }
        monitor.record_event(event, source_agent="researcher")

        handoffs = [e for e in monitor._events if e["event"] == "handoff"]
        assert len(handoffs) == 1
        assert handoffs[0]["data"]["from"] == "researcher"
        assert handoffs[0]["data"]["to"] == "writer"

    def test_flush_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SwarmMonitor(conversation_id="flush-test", output_dir=tmpdir)
            monitor.record_event(
                {"event": "on_tool_start", "name": "t1", "data": {"input": {}}},
                source_agent="a",
            )

            path = monitor.flush()
            assert path is not None
            assert os.path.exists(path)

            with open(path, "r") as f:
                lines = f.readlines()

            assert len(lines) == 2  # turn_start + on_tool_start
            for line in lines:
                entry = json.loads(line)
                assert "ts" in entry
                assert "seq" in entry

    def test_flush_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SwarmMonitor(conversation_id="test", output_dir=tmpdir)

            path1 = monitor.flush()
            path2 = monitor.flush()

            # Second flush should return None (nothing new)
            assert path1 is not None
            assert path2 is None

    def test_record_custom_event(self):
        monitor = SwarmMonitor(conversation_id="test")
        monitor.record_custom("phase_complete", {"phase": "research"}, agent="a")

        custom = [e for e in monitor._events if e["event"] == "phase_complete"]
        assert len(custom) == 1
        assert custom[0]["data"]["phase"] == "research"

    def test_flush_appends_across_calls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = SwarmMonitor(conversation_id="test", output_dir=tmpdir)
            monitor.flush()

            # Add more events and flush again
            monitor.record_event(
                {"event": "on_chat_model_start", "name": "gpt-4o", "data": {"input": {"messages": []}}},
                source_agent="a",
            )
            path = monitor.flush()
            assert path is not None

            with open(path, "r") as f:
                lines = f.readlines()
            assert len(lines) == 2  # turn_start from first + chat_model_start from second
