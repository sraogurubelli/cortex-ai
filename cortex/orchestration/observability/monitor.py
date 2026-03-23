"""
Swarm Monitor — JSONL event recorder for post-mortem debugging.

Records LangGraph ``astream_events`` to a JSONL file so you can inspect
the full event timeline after a request completes (or fails).

The monitor is **agent-agnostic**: it records events from every agent in
the swarm with agent attribution and scales to N agents without changes.

Usage::

    from cortex.orchestration.observability.monitor import SwarmMonitor

    monitor = SwarmMonitor(conversation_id="abc-123")

    async for event in compiled.astream_events(...):
        monitor.record_event(event, source_agent=current_agent)

    monitor.flush()
    # → agent_execution_history/swarm_monitor/abc-123/events.jsonl

Events are **appended** across turns so a single file captures the full
conversation lifecycle.  Each turn begins with a ``turn_start`` event
carrying ``conversation_id`` and ``interaction_id``.

Each JSONL line is a JSON object with keys::

    ts      — ISO-8601 timestamp
    seq     — monotonic sequence number (resets per turn)
    event   — LangGraph event type (on_tool_start, on_chat_model_end, …)
    agent   — source agent name
    data    — event-specific payload (tool name, args preview, etc.)

Ported from ml-infra orchestration_sdk/observability/monitor.py.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_MAX_PREVIEW_CHARS = 500


def _default_output_root() -> str:
    return os.path.join(os.getcwd(), "agent_execution_history", "swarm_monitor")


def _truncate(value: Any, max_chars: int = _MAX_PREVIEW_CHARS) -> str:
    """Convert *value* to a string and truncate if necessary."""
    text = str(value) if not isinstance(value, str) else value
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"… [{len(text) - max_chars} chars truncated]"


class SwarmMonitor:
    """Records swarm events to a JSONL file for post-mortem debugging.

    Each line is a JSON object with ``ts``, ``seq``, ``event``,
    ``agent``, and ``data`` keys.  Data previews are truncated to
    *max_preview_chars* to keep the file manageable.

    The monitor buffers events in memory and writes them to disk on
    :meth:`flush`.  Call ``flush()`` in the runner's ``finally`` block
    to guarantee the file is written even when the request errors out.
    """

    def __init__(
        self,
        conversation_id: str,
        interaction_id: str = "",
        output_dir: str | None = None,
        max_preview_chars: int = _MAX_PREVIEW_CHARS,
    ) -> None:
        self._conversation_id = conversation_id
        self._interaction_id = interaction_id
        self._max_chars = max_preview_chars
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self._flush_offset = 0

        if output_dir is None:
            self._output_dir = os.path.join(
                _default_output_root(), conversation_id
            )
        else:
            self._output_dir = output_dir

        self._append(
            "turn_start",
            "",
            {
                "conversation_id": conversation_id,
                "interaction_id": interaction_id,
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_event(self, event: dict, source_agent: str = "") -> None:
        """Extract key info from a LangGraph ``astream_events`` event.

        Only events that carry useful debugging information are recorded;
        high-frequency token-stream events (``on_chat_model_stream``)
        are skipped to avoid bloating the file.
        """
        event_type = event.get("event", "")

        if event_type == "on_chat_model_stream":
            return

        handler = self._HANDLERS.get(event_type)
        if handler is None:
            return

        data = handler(self, event)
        if data is None:
            return

        # Detect agent handoffs from transfer_to_* tool names
        if event_type == "on_tool_end":
            tool_name = event.get("name", "")
            if tool_name.startswith("transfer_to_"):
                target = tool_name[len("transfer_to_"):]
                self._append(
                    "handoff",
                    source_agent,
                    {"from": source_agent, "to": target},
                )

        self._append(event_type, source_agent, data)

    def record_custom(
        self,
        event_type: str,
        data: dict[str, Any],
        agent: str = "",
    ) -> None:
        """Record a custom event (errors, phase messages, etc.)."""
        safe_data = {k: _truncate(v, self._max_chars) for k, v in data.items()}
        self._append(event_type, agent, safe_data)

    def flush(self) -> str | None:
        """Append buffered events to ``{output_dir}/events.jsonl``.

        Events are **appended** so that multiple turns within the same
        conversation accumulate in a single file.  Each turn is
        delimited by a ``turn_start`` event emitted in ``__init__``.

        Returns the file path on success, ``None`` on failure.
        Safe to call multiple times — only unflushed events are written.
        """
        pending = self._events[self._flush_offset:]
        if not pending:
            return None

        try:
            os.makedirs(self._output_dir, exist_ok=True)
            file_path = os.path.join(self._output_dir, "events.jsonl")

            with open(file_path, "a", encoding="utf-8") as fh:
                for entry in pending:
                    fh.write(json.dumps(entry, ensure_ascii=False, default=str))
                    fh.write("\n")

            self._flush_offset = len(self._events)
            logger.info(
                "Swarm monitor flushed %d events to %s (conversation=%s)",
                len(pending),
                file_path,
                self._conversation_id,
            )
            return file_path

        except Exception:
            logger.exception(
                "Failed to flush swarm monitor (conversation=%s)",
                self._conversation_id,
            )
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(
        self,
        event_type: str,
        agent: str,
        data: dict[str, Any],
    ) -> None:
        self._seq += 1
        self._events.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "seq": self._seq,
                "event": event_type,
                "agent": agent,
                "data": data,
            }
        )

    # ------------------------------------------------------------------
    # Per-event-type extractors
    # ------------------------------------------------------------------

    def _extract_chat_model_start(self, event: dict) -> dict | None:
        data = event.get("data", {})
        input_data = data.get("input", {})
        messages = (
            input_data.get("messages", []) if isinstance(input_data, dict) else []
        )
        return {
            "model": event.get("name", ""),
            "message_count": len(messages),
        }

    def _extract_chat_model_end(self, event: dict) -> dict | None:
        data = event.get("data", {})
        output = data.get("output")
        if output is None:
            return {"content_preview": ""}

        content = getattr(output, "content", "")
        tool_calls = getattr(output, "tool_calls", None)
        usage = getattr(output, "usage_metadata", None)

        result: dict[str, Any] = {
            "content_preview": _truncate(content, self._max_chars),
        }

        if tool_calls:
            result["tool_calls"] = [
                {"name": tc.get("name", ""), "id": tc.get("id", "")}
                for tc in tool_calls
            ]

        if usage:
            result["usage"] = dict(usage)

        return result

    def _extract_tool_start(self, event: dict) -> dict | None:
        data = event.get("data", {})
        args = data.get("input", {})
        return {
            "tool": event.get("name", ""),
            "args_preview": _truncate(args, self._max_chars),
        }

    def _extract_tool_end(self, event: dict) -> dict | None:
        data = event.get("data", {})
        output = data.get("output", "")

        if hasattr(output, "content"):
            output = output.content

        return {
            "tool": event.get("name", ""),
            "result_preview": _truncate(output, self._max_chars),
        }

    _HANDLERS: dict[str, Any] = {
        "on_chat_model_start": _extract_chat_model_start,
        "on_chat_model_end": _extract_chat_model_end,
        "on_tool_start": _extract_tool_start,
        "on_tool_end": _extract_tool_end,
    }
