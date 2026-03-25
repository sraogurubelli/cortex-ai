"""
Conversation History Dump — debug-mode serialization of full conversations.

When enabled, writes the entire conversation history (messages + metadata)
to a JSONL file on disk after each session completes. Useful for post-mortem
debugging but must be used carefully in production (PII risk).

Ported from ml-infra's ``dump_conversation_history`` pattern.

Usage::

    from cortex.orchestration.safety.history_dump import HistoryDumpHook

    hook = HistoryDumpHook(output_dir="/tmp/cortex-debug")

    config = SessionConfig(
        ...,
        event_hooks=[hook],
    )

Environment Variables:
    CORTEX_DUMP_CONVERSATION_HISTORY: Enable history dump (default: false)
    CORTEX_HISTORY_DUMP_DIR: Output directory (default: ./agent_execution_history/conversations)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _default_output_dir() -> str:
    return os.path.join(
        os.getcwd(), "agent_execution_history", "conversations"
    )


class HistoryDumpHook:
    """Session event hook that dumps conversation history to disk.

    Fires on ``on_session_complete`` and ``on_session_error`` to capture
    both successful and failed conversations.

    The dump is only performed when:
      - The hook is explicitly enabled, OR
      - The ``CORTEX_DUMP_CONVERSATION_HISTORY`` env var is set to "true"

    Args:
        output_dir: Directory for dump files (auto-created).
        enabled: Explicitly enable/disable (overrides env var if set).
        include_metadata: Include session metadata in the dump.
        sanitize: If True, run the PII redactor on the dump before writing.
    """

    def __init__(
        self,
        output_dir: str | None = None,
        enabled: bool | None = None,
        include_metadata: bool = True,
        sanitize: bool = False,
    ) -> None:
        if enabled is not None:
            self._enabled = enabled
        else:
            self._enabled = os.getenv(
                "CORTEX_DUMP_CONVERSATION_HISTORY", "false"
            ).lower() in ("true", "1", "yes")

        self._output_dir = output_dir or os.getenv(
            "CORTEX_HISTORY_DUMP_DIR", _default_output_dir()
        )
        self._include_metadata = include_metadata
        self._sanitize = sanitize

    async def on_session_start(self, config: Any, metadata: dict) -> None:
        pass

    async def on_session_complete(
        self, config: Any, result: Any, metadata: dict
    ) -> None:
        if not self._enabled:
            return
        self._dump(config, result, metadata, status="completed")

    async def on_session_error(
        self, config: Any, error: Exception, metadata: dict
    ) -> None:
        if not self._enabled:
            return
        self._dump(config, None, metadata, status="error", error=str(error))

    def _dump(
        self,
        config: Any,
        result: Any,
        metadata: dict,
        status: str,
        error: str | None = None,
    ) -> None:
        try:
            os.makedirs(self._output_dir, exist_ok=True)

            conversation_id = getattr(config, "conversation_id", "unknown")
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"{conversation_id}_{ts}.jsonl"
            filepath = os.path.join(self._output_dir, filename)

            messages_data = self._serialize_messages(result)

            dump_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "conversation_id": conversation_id,
                "status": status,
                "messages": messages_data,
            }

            if self._include_metadata:
                dump_record["metadata"] = {
                    "model": getattr(config, "model", "unknown"),
                    "mode": getattr(config, "mode", "standard"),
                    "agent_name": getattr(config, "agent_name", "unknown"),
                    "duration_ms": metadata.get("duration_ms", 0),
                    "usage": metadata.get("usage", {}),
                }

            if error:
                dump_record["error"] = error

            if self._sanitize:
                dump_record = self._sanitize_record(dump_record)

            with open(filepath, "w") as f:
                f.write(json.dumps(dump_record, default=str) + "\n")

            logger.info("Conversation history dumped", extra={"path": filepath})

        except Exception:
            logger.debug("Failed to dump conversation history", exc_info=True)

    @staticmethod
    def _serialize_messages(result: Any) -> list[dict]:
        """Convert LangChain messages to serializable dicts."""
        if result is None:
            return []

        messages = getattr(result, "messages", [])
        serialized = []

        for msg in messages:
            entry: dict[str, Any] = {
                "type": type(msg).__name__,
                "content": getattr(msg, "content", ""),
            }

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "name": tc.get("name", ""),
                        "args_preview": str(tc.get("args", ""))[:200],
                    }
                    for tc in msg.tool_calls
                ]

            if hasattr(msg, "name") and msg.name:
                entry["name"] = msg.name

            serialized.append(entry)

        return serialized

    @staticmethod
    def _sanitize_record(record: dict) -> dict:
        """Apply PII redaction to the dump record."""
        try:
            from cortex.orchestration.safety.pii_redaction import PIIRedactor
            redactor = PIIRedactor()
            return redactor.redact_dict(record)
        except Exception:
            return record
