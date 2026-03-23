"""
Message summarization and trimming middleware for LangChain agents.

Two strategies for managing conversation length within LangGraph agents:

1. "summarize" — LLM-based summarization of older messages via LangChain's
   built-in SummarizationMiddleware (requires a model).
2. "trim" — Lightweight, deterministic message trimming that keeps system +
   first user + N recent messages, inserting a marker for dropped messages.

Usage::

    from cortex.orchestration.middleware.summarization import (
        create_summarization_middleware,
        MessageTrimmingMiddleware,
    )

    # LLM-based summarization
    mw = create_summarization_middleware(
        strategy="summarize",
        model=my_chat_model,
    )

    # Lightweight trimming (no LLM call)
    mw = create_summarization_middleware(strategy="trim", keep_messages=15)

    # Or use the trimming middleware directly
    mw = MessageTrimmingMiddleware(max_messages=40, keep_recent=20)

Ported from ml-infra orchestration_sdk/middleware/summarization.py.
"""

import logging
import os
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage

logger = logging.getLogger(__name__)

DEFAULT_SUMMARIZATION_TOKEN_TRIGGER = int(
    os.getenv("SUMMARIZATION_TOKEN_TRIGGER", "100000")
)
DEFAULT_KEEP_MESSAGES = int(os.getenv("SUMMARIZATION_KEEP_MESSAGES", "20"))


def create_summarization_middleware(
    model: Optional[BaseChatModel] = None,
    model_name: Optional[str] = None,
    strategy: str = "trim",
    token_trigger: int = DEFAULT_SUMMARIZATION_TOKEN_TRIGGER,
    keep_messages: int = DEFAULT_KEEP_MESSAGES,
) -> Any:
    """Create a summarization middleware for LangChain agents.

    Args:
        model: LangChain chat model for LLM-based summarization
            (required when ``strategy="summarize"``).
        model_name: Model name string for the built-in SummarizationMiddleware.
        strategy: ``"summarize"`` for LLM-based, ``"trim"`` for lightweight trimming.
        token_trigger: Token count threshold that triggers summarization/trimming.
        keep_messages: Number of recent messages to keep after compression.

    Returns:
        A middleware instance compatible with ``create_agent()``.
    """
    if strategy == "summarize":
        return _create_ootb_summarization(
            model=model,
            model_name=model_name,
            token_trigger=token_trigger,
            keep_messages=keep_messages,
        )

    return MessageTrimmingMiddleware(
        max_messages=keep_messages * 2,
        keep_recent=keep_messages,
    )


def _create_ootb_summarization(
    model: Optional[BaseChatModel] = None,
    model_name: Optional[str] = None,
    token_trigger: int = DEFAULT_SUMMARIZATION_TOKEN_TRIGGER,
    keep_messages: int = DEFAULT_KEEP_MESSAGES,
) -> Any:
    """Create LangChain's built-in SummarizationMiddleware."""
    try:
        from langchain.agents.middleware import (
            AgentMiddleware,
            SummarizationMiddleware,
        )

        kwargs: dict[str, Any] = {
            "trigger": [("tokens", token_trigger)],
            "keep": ("messages", keep_messages),
        }

        if model is not None:
            kwargs["model"] = model
        elif model_name is not None:
            kwargs["model"] = model_name
        else:
            raise ValueError(
                "Either model or model_name must be provided for 'summarize' strategy"
            )

        middleware = SummarizationMiddleware(**kwargs)
        logger.info(
            "Created SummarizationMiddleware (token_trigger=%d, keep_messages=%d)",
            token_trigger,
            keep_messages,
        )
        return middleware

    except ImportError:
        logger.warning(
            "SummarizationMiddleware not available, "
            "falling back to MessageTrimmingMiddleware"
        )
        return MessageTrimmingMiddleware(
            max_messages=keep_messages * 2,
            keep_recent=keep_messages,
        )


class MessageTrimmingMiddleware:
    """Lightweight message trimming middleware.

    Trims messages when the count exceeds ``max_messages``, keeping:

    * The system message (always)
    * The first user message (original question)
    * The most recent ``keep_recent`` messages

    Middle messages are replaced with a compact summary marker.
    No LLM call required — purely deterministic.

    This class intentionally duck-types the LangChain ``AgentMiddleware``
    protocol (``before_model`` / ``abefore_model``) so it works with
    ``create_agent()`` without requiring the optional ``langchain``
    middleware import.
    """

    def __init__(
        self,
        max_messages: int = 40,
        keep_recent: int = 20,
    ):
        self.max_messages = max_messages
        self.keep_recent = keep_recent

    def before_model(
        self, state: Any, runtime: Any = None
    ) -> Optional[dict[str, Any]]:
        """Trim messages before the model call if over threshold."""
        messages = state.get("messages", [])

        if len(messages) <= self.max_messages:
            return None

        trimmed = self._trim(messages)
        if len(trimmed) < len(messages):
            logger.info(
                "MessageTrimmingMiddleware trimmed messages: %d → %d (max=%d)",
                len(messages),
                len(trimmed),
                self.max_messages,
            )
            return {"messages": trimmed}

        return None

    async def abefore_model(
        self, state: Any, runtime: Any = None
    ) -> Optional[dict[str, Any]]:
        """Async version of ``before_model``."""
        return self.before_model(state, runtime)

    def _trim(self, messages: list) -> list:
        """Trim messages, keeping system + first user + recent messages."""
        prefix: list = []
        remaining = messages

        if remaining and isinstance(remaining[0], SystemMessage):
            prefix.append(remaining[0])
            remaining = remaining[1:]

        for msg in remaining[:2]:
            if hasattr(msg, "type") and msg.type == "human":
                prefix.append(msg)
                break

        suffix = remaining[-self.keep_recent :]

        if len(prefix) + len(suffix) >= len(messages):
            return messages

        dropped_count = len(messages) - len(prefix) - len(suffix)
        marker = AIMessage(
            content=f"[{dropped_count} earlier messages trimmed for context management]"
        )

        return prefix + [marker] + suffix
