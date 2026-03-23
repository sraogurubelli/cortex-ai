"""
UI Actions Protocol — agent-drives-UI via structured SSE events.

Defines a protocol for the AI agent to instruct the frontend to perform
UI actions (navigate to pages, open documents, trigger uploads, show
search results, etc.) through structured SSE events.

The protocol uses two SSE event types:

- ``ui_action`` — a single action the frontend should execute.
- ``ui_action_update`` — status update for a previously emitted action.

Backend usage (cortex-ai)::

    from cortex.orchestration.ui_actions import (
        emit_navigate,
        emit_action,
        ActionStatus,
    )

    # Tell the UI to navigate to the documents page
    action_id = await emit_navigate(stream_writer, page_id="documents")

    # Tell the UI to open a specific document
    action_id = await emit_action(
        stream_writer,
        action_type="open_document",
        args={"document_id": "doc-123", "project_id": "proj-456"},
    )

Frontend handling (cortex-ui)::

    // In useChat hook, handle the "ui_action" SSE event:
    case "ui_action":
      const { action_type, args, action_id } = JSON.parse(event.data);
      switch (action_type) {
        case "navigate":
          router.push(args.page_id);
          break;
        case "open_document":
          openDocumentPanel(args.document_id);
          break;
      }

Adapted from the pattern in ml-infra capabilities/tools/ui_actions/.
"""

from cortex.orchestration.ui_actions.schemas import (
    ActionStatus,
    UIAction,
    UIActionUpdate,
)
from cortex.orchestration.ui_actions.emitter import (
    emit_action,
    emit_action_update,
    emit_navigate,
    emit_show_document,
    emit_open_search,
)
from cortex.orchestration.ui_actions.continuation_detector import (
    build_system_event_query,
    detect_suggested_actions_from_text,
    extract_original_intent,
    is_navigation_continuation,
    is_ui_action_continuation,
)
from cortex.orchestration.ui_actions.capability_mapper import (
    filter_suggestions_by_capabilities,
    merge_tool_capabilities_with_suggestions,
    normalize_tool_name,
    ui_action_types_for_tools,
)

__all__ = [
    # Schemas
    "ActionStatus",
    "UIAction",
    "UIActionUpdate",
    # Emitters
    "emit_action",
    "emit_action_update",
    "emit_navigate",
    "emit_show_document",
    "emit_open_search",
    # Continuation detection
    "is_ui_action_continuation",
    "is_navigation_continuation",
    "extract_original_intent",
    "build_system_event_query",
    "detect_suggested_actions_from_text",
    # Capability mapping
    "normalize_tool_name",
    "ui_action_types_for_tools",
    "filter_suggestions_by_capabilities",
    "merge_tool_capabilities_with_suggestions",
]
