"""
Conversation serialization and history dumping utilities.

Debugging / diagnostics helpers for inspecting the full LangChain message
history (including tool calls, usage metadata, etc.) by serializing to
JSON-safe dicts or writing to local JSON files.

Typically gated behind the ``DUMP_CONVERSATION_HISTORY`` environment
variable so they are no-ops in production.

Usage::

    from cortex.orchestration.observability.conversation import (
        serialize_message,
        serialize_messages,
        dump_conversation_history,
    )

    # Serialize for API responses or logging
    data = serialize_messages(messages)

    # Dump full execution history to disk
    path = dump_conversation_history(
        messages,
        metadata={"model": "gpt-4o", "conversation_id": "abc-123"},
    )

Ported from ml-infra orchestration_sdk/observability/conversation.py.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

logger = logging.getLogger(__name__)


def serialize_message(msg: BaseMessage) -> dict[str, Any]:
    """Serialize a LangChain message to a JSON-compatible dict.

    Handles content (str or list of blocks), tool calls on AIMessage,
    usage metadata, and ToolMessage fields.
    """
    data: dict[str, Any] = {"type": msg.type}

    if isinstance(msg.content, str):
        data["content"] = msg.content
    elif isinstance(msg.content, list):
        data["content"] = [
            block if isinstance(block, (str, dict)) else str(block)
            for block in msg.content
        ]

    if isinstance(msg, AIMessage):
        if msg.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.get("id"),
                    "name": tc.get("name"),
                    "args": tc.get("args"),
                }
                for tc in msg.tool_calls
            ]
        usage = getattr(msg, "usage_metadata", None)
        if usage:
            data["usage_metadata"] = dict(usage)

    if isinstance(msg, ToolMessage):
        data["tool_call_id"] = msg.tool_call_id
        data["name"] = getattr(msg, "name", "")

    return data


def serialize_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Serialize a list of LangChain messages to JSON-compatible dicts."""
    return [serialize_message(msg) for msg in messages]


def dump_conversation_history(
    messages: list[BaseMessage],
    metadata: dict[str, Any] | None = None,
    output_dir: str | None = None,
    dir_name: str = "agent_execution_history",
) -> str | None:
    """Dump conversation history to a JSON file.

    Args:
        messages: LangChain messages to serialize.
        metadata: Arbitrary execution metadata (model, token_usage, IDs, etc.)
            included under the ``"execution_context"`` key.
        output_dir: Absolute path to write the file into.  If provided,
            *dir_name* is ignored.
        dir_name: Directory name created under cwd.  Defaults to
            ``"agent_execution_history"``.  Ignored if *output_dir* is set.

    Returns:
        The file path written, or ``None`` if writing failed.
    """
    try:
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), dir_name)
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(
            output_dir, f"conversation_history_{timestamp}.json"
        )

        dump_data: dict[str, Any] = {
            "messages": serialize_messages(messages),
            "message_count": len(messages),
        }
        if metadata:
            dump_data["execution_context"] = metadata

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, indent=2, ensure_ascii=False)

        logger.info("Conversation history dumped to %s", file_path)
        return file_path

    except Exception:
        logger.warning("Failed to dump conversation history", exc_info=True)
        return None
