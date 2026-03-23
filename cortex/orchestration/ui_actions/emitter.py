"""
Emitter functions for sending UI action events through a StreamWriter.

Each function constructs a ``UIAction``, serializes it, and writes it
as an SSE event.  Returns the ``action_id`` so the caller can track
status updates from the frontend.
"""

import logging
from typing import Any, Protocol

from cortex.orchestration.ui_actions.schemas import (
    ActionStatus,
    UIAction,
    UIActionUpdate,
)

logger = logging.getLogger(__name__)


class _StreamWriterProtocol(Protocol):
    """Minimal protocol for SSE stream writers."""

    async def write_event(self, event_type: str, data: Any) -> None: ...


# ---------------------------------------------------------------------------
# Generic emitter
# ---------------------------------------------------------------------------


async def emit_action(
    stream_writer: _StreamWriterProtocol,
    action_type: str,
    args: dict[str, Any] | None = None,
    status: ActionStatus = ActionStatus.EXECUTING,
    display_text: str | None = None,
) -> str:
    """Emit a generic UI action event.

    Args:
        stream_writer: SSE stream writer.
        action_type: Action type string (e.g. ``"navigate"``).
        args: Action-specific arguments.
        status: Initial status.
        display_text: Human-readable description.

    Returns:
        The ``action_id`` for tracking updates.
    """
    action = UIAction(
        action_type=action_type,
        args=args or {},
        status=status,
        display_text=display_text,
    )
    await stream_writer.write_event(
        "ui_action", action.model_dump(exclude_none=True)
    )
    logger.info(
        "Emitted ui_action: type=%s, id=%s, status=%s",
        action_type,
        action.action_id,
        status.value,
    )
    return action.action_id


async def emit_action_update(
    stream_writer: _StreamWriterProtocol,
    action_id: str,
    status: ActionStatus,
    result: dict[str, Any] | None = None,
) -> None:
    """Emit a status update for a previously emitted action.

    Args:
        stream_writer: SSE stream writer.
        action_id: The ``action_id`` of the original ``UIAction``.
        status: New status.
        result: Optional result payload.
    """
    update = UIActionUpdate(
        action_id=action_id, status=status, result=result
    )
    await stream_writer.write_event(
        "ui_action_update", update.model_dump(exclude_none=True)
    )
    logger.info(
        "Emitted ui_action_update: id=%s, status=%s",
        action_id,
        status.value,
    )


# ---------------------------------------------------------------------------
# Convenience emitters for common actions
# ---------------------------------------------------------------------------


async def emit_navigate(
    stream_writer: _StreamWriterProtocol,
    page_id: str,
    status: ActionStatus = ActionStatus.EXECUTING,
    display_text: str | None = None,
) -> str:
    """Instruct the frontend to navigate to a page.

    Args:
        stream_writer: SSE stream writer.
        page_id: Target page identifier (e.g. ``"documents"``, ``"projects"``).
        status: Initial status.
        display_text: Optional message shown in the chat.

    Returns:
        The ``action_id``.
    """
    return await emit_action(
        stream_writer,
        action_type="navigate",
        args={"page_id": page_id},
        status=status,
        display_text=display_text or f"Navigating to {page_id}…",
    )


async def emit_show_document(
    stream_writer: _StreamWriterProtocol,
    document_id: str,
    project_id: str | None = None,
    display_text: str | None = None,
) -> str:
    """Instruct the frontend to open/highlight a document.

    Args:
        stream_writer: SSE stream writer.
        document_id: Document identifier.
        project_id: Optional project scope.
        display_text: Optional message.

    Returns:
        The ``action_id``.
    """
    args: dict[str, Any] = {"document_id": document_id}
    if project_id:
        args["project_id"] = project_id
    return await emit_action(
        stream_writer,
        action_type="show_document",
        args=args,
        display_text=display_text or f"Opening document {document_id}…",
    )


async def emit_open_search(
    stream_writer: _StreamWriterProtocol,
    query: str,
    project_id: str | None = None,
    display_text: str | None = None,
) -> str:
    """Instruct the frontend to open the search panel with a query.

    Args:
        stream_writer: SSE stream writer.
        query: Pre-filled search query.
        project_id: Optional project scope.
        display_text: Optional message.

    Returns:
        The ``action_id``.
    """
    args: dict[str, Any] = {"query": query}
    if project_id:
        args["project_id"] = project_id
    return await emit_action(
        stream_writer,
        action_type="open_search",
        args=args,
        display_text=display_text or f'Searching for "{query}"…',
    )
