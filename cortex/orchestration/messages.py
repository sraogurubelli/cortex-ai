"""
Message conversion utilities.

Bi-directional conversion between simple ``{role, content}`` dicts
(used in API payloads and database storage) and LangChain
``BaseMessage`` objects (used in the orchestration layer).
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

_ROLE_TO_CLS: dict[str, type[BaseMessage]] = {
    "user": HumanMessage,
    "human": HumanMessage,
    "assistant": AIMessage,
    "ai": AIMessage,
    "system": SystemMessage,
}

_TYPE_TO_ROLE: dict[str, str] = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
}


def dicts_to_messages(history: list[dict[str, str]]) -> list[BaseMessage]:
    """Convert ``[{role, content}, ...]`` to LangChain messages."""
    messages: list[BaseMessage] = []
    for item in history:
        role = item.get("role", "user")
        content = item.get("content", "")
        cls = _ROLE_TO_CLS.get(role, HumanMessage)
        messages.append(cls(content=content))
    return messages


def messages_to_dicts(messages: list[BaseMessage]) -> list[dict[str, str]]:
    """Convert LangChain messages to ``[{role, content}, ...]``."""
    result: list[dict[str, str]] = []
    for msg in messages:
        role = _TYPE_TO_ROLE.get(msg.type, msg.type)
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        result.append({"role": role, "content": content})
    return result
