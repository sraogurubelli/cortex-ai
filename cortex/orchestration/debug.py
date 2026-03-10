"""Conversation serialization and history dumping utilities.

These are **debugging / diagnostics helpers**, not part of the production
request path. They let developers inspect the full LangChain message
history (including tool calls, usage metadata, etc.) by writing it to a
local JSON file. Typically gated behind the ``DUMP_CONVERSATION_HISTORY``
environment variable so they are no-ops in production.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

logger = logging.getLogger(__name__)


def serialize_message(msg: BaseMessage) -> Dict[str, Any]:
    """
    Serialize a LangChain message to a JSON-compatible dict.

    Handles content (str or list of blocks), tool calls on AIMessage,
    usage metadata, and ToolMessage fields.
    """
    data: Dict[str, Any] = {"type": msg.type}

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
                {"id": tc.get("id"), "name": tc.get("name"), "args": tc.get("args")}
                for tc in msg.tool_calls
            ]
        usage = getattr(msg, "usage_metadata", None)
        if usage:
            data["usage_metadata"] = dict(usage)

    if isinstance(msg, ToolMessage):
        data["tool_call_id"] = msg.tool_call_id
        data["name"] = getattr(msg, "name", "")

    return data


def serialize_messages(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Serialize a list of LangChain messages to JSON-compatible dicts."""
    return [serialize_message(msg) for msg in messages]


def dump_conversation_history(
    messages: List[BaseMessage],
    metadata: Dict[str, Any] | None = None,
    output_dir: str | None = None,
    dir_name: str = "agent_execution_history",
) -> str | None:
    """
    Dump conversation history to a JSON file.

    Controlled by the DUMP_CONVERSATION_HISTORY environment variable.
    Set to "1" or "true" to enable dumping.

    Args:
        messages: LangChain messages to serialize.
        metadata: Arbitrary execution metadata (model, token_usage, IDs, etc.)
            included under the "execution_context" key.
        output_dir: Absolute path to write the file into. If provided,
            ``dir_name`` is ignored.
        dir_name: Directory name created under cwd. Defaults to
            ``"agent_execution_history"``. Ignored if ``output_dir`` is set.

    Returns:
        The file path written, or None if writing failed or dumping is disabled.

    Example:
        # Enable dumping
        os.environ["DUMP_CONVERSATION_HISTORY"] = "1"

        # Dump conversation
        result = await agent.run("...")
        dump_conversation_history(
            result.messages,
            metadata={
                "model": "gpt-4o",
                "token_usage": result.token_usage,
                "user_id": "user123",
            }
        )
    """
    # Check if dumping is enabled
    dump_enabled = os.environ.get("DUMP_CONVERSATION_HISTORY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if not dump_enabled:
        return None

    try:
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), dir_name)
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(output_dir, f"conversation_history_{timestamp}.json")

        dump_data: Dict[str, Any] = {
            "messages": serialize_messages(messages),
            "message_count": len(messages),
            "timestamp": timestamp,
        }
        if metadata:
            dump_data["execution_context"] = metadata

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, indent=2, ensure_ascii=False)

        logger.info("Conversation history dumped", extra={"path": file_path})
        return file_path

    except Exception as e:
        logger.warning("Failed to dump conversation history", extra={"error": str(e)})
        return None


def load_conversation_history(file_path: str) -> Dict[str, Any] | None:
    """
    Load conversation history from a JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        The loaded conversation data, or None if loading failed

    Example:
        data = load_conversation_history("agent_execution_history/conversation_history_20250308_143022.json")
        print(f"Message count: {data['message_count']}")
        print(f"Messages: {data['messages']}")
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(
            "Failed to load conversation history",
            extra={"path": file_path, "error": str(e)},
        )
        return None
