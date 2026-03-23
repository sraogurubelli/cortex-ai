"""
Detect UI continuations from system events and from agent response text.

Supports the post-navigation flow (frontend sends a system event after a UI
action completes) and heuristic follow-up suggestions when the assistant text
mentions documents, search, uploads, projects, or executable code.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from cortex.orchestration.ui_actions.schemas import ActionStatus, UIAction

logger = logging.getLogger(__name__)

# --- System-event continuation (generic wire shape, no product-specific IDs) ---


def is_ui_action_continuation(system_event: dict[str, Any] | None) -> bool:
    """
    Return True if the frontend indicates a prior UI action completed successfully.

    Expected ``system_event`` shape::

        {
            "event_type": "action_completed" | "action_cancelled",
            "capability_id": "<action or capability name>",
            "result": {"success": true | false},
        }

    ``capability_id`` is optional metadata for logging; success is what matters
    for treating the turn as a continuation.
    """
    if not system_event:
        return False

    event_type = system_event.get("event_type")
    capability_id = system_event.get("capability_id")
    result = system_event.get("result") or {}

    if event_type == "action_completed":
        success = bool(result.get("success", False))
        if success:
            logger.info(
                "Detected UI action continuation: capability_id=%s target_page=%s",
                capability_id,
                system_event.get("target_page_id"),
            )
            return True
        logger.info(
            "UI action completed without success: capability_id=%s result=%s",
            capability_id,
            result,
        )
        return False

    if event_type == "action_cancelled":
        logger.info("Detected UI action cancellation: capability_id=%s", capability_id)
        return False

    return False


def is_navigation_continuation(system_event: dict[str, Any] | None) -> bool:
    """Backward-compatible alias for :func:`is_ui_action_continuation`."""
    return is_ui_action_continuation(system_event)


def extract_original_intent(
    message_history: list[dict[str, Any]] | None,
) -> str | None:
    """Return content of the most recent user message, if any."""
    if not message_history:
        return None
    user_messages = [m for m in message_history if m.get("role") == "user"]
    if not user_messages:
        return None
    content = user_messages[-1].get("content", "")
    if isinstance(content, str):
        logger.debug("Extracted original intent from last user message")
        return content
    return None


def build_system_event_query(
    system_event: dict[str, Any],
    message_history: list[dict[str, Any]] | None = None,
) -> str:
    """
    Build an LLM-facing instruction string for a frontend system event.

    Callers can pass this as the user turn (or system supplement) so the model
    acknowledges completion, cancellation, or failure and continues helpfully.
    """
    capability_id = system_event.get("capability_id", "ui_action")
    event_type = system_event.get("event_type", "")
    result = system_event.get("result") or {}

    original_intent = extract_original_intent(message_history)
    intent_context = (
        f" The original user request was: '{original_intent}'."
        if original_intent
        else ""
    )

    if event_type == "action_cancelled":
        logger.info(
            "Building query for cancelled action: capability_id=%s",
            capability_id,
        )
        return (
            f"The user cancelled the '{capability_id}' action.{intent_context}"
            " Let the user know the action was cancelled and ask if they want a "
            "different approach."
        )

    success = bool(result.get("success", False))
    if success:
        logger.info(
            "Building query for successful action: capability_id=%s",
            capability_id,
        )
        return (
            f"The '{capability_id}' action completed successfully.{intent_context}"
            " Confirm completion and offer concise, relevant next steps."
        )

    logger.info(
        "Building query for failed action: capability_id=%s",
        capability_id,
    )
    return (
        f"The '{capability_id}' action did not complete successfully.{intent_context}"
        " Explain briefly, suggest retrying or an alternative."
    )


# --- Response-text heuristics → suggested UIAction instances ---

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_DOC_ID_RE = re.compile(r"\b(?:doc|document)[_-]?id[\"'\s:=]+([a-zA-Z0-9_.-]+)", re.I)
_QUOTED_RE = re.compile(r"['\"]([^'\"]{3,120})['\"]")


def _first_uuid(text: str) -> str | None:
    m = _UUID_RE.search(text)
    return m.group(0) if m else None


def _first_doc_id(text: str) -> str | None:
    m = _DOC_ID_RE.search(text)
    return m.group(1) if m else None


def _search_query_from_text(text: str) -> str | None:
    lowered = text.lower()
    for phrase in (
        "search for",
        "look up",
        "lookup",
        "find ",
        "query ",
    ):
        idx = lowered.find(phrase)
        if idx != -1:
            tail = text[idx + len(phrase) :].strip()
            qm = _QUOTED_RE.search(tail)
            if qm:
                return qm.group(1).strip()
            # first clause up to sentence end
            cut = re.split(r"[.!?\n]", tail, maxsplit=1)
            candidate = cut[0].strip().strip(" '\"")
            if 3 <= len(candidate) <= 200:
                return candidate
    return None


def detect_suggested_actions_from_text(
    response_text: str,
    *,
    project_id: str | None = None,
) -> list[UIAction]:
    """
    Infer follow-up ``UIAction`` suggestions from assistant-visible text.

    Uses lightweight keyword and entity heuristics (not an LLM). Suggested
    actions use cortex-oriented ``action_type`` values; unknown types are safe
    for frontends that ignore them.

    Args:
        response_text: The assistant message to scan.
        project_id: Optional scope passed through to action ``args``.

    Returns:
        Zero or more :class:`UIAction` instances (no SSE emission).
    """
    if not (response_text and response_text.strip()):
        return []

    text = response_text
    lowered = text.lower()
    suggestions: list[UIAction] = []

    def _with_project(args: dict[str, Any]) -> dict[str, Any]:
        if project_id:
            out = {**args, "project_id": project_id}
            return out
        return dict(args)

    # Documents / files
    doc_keywords = (
        "document",
        "pdf",
        "attachment",
        "uploaded file",
        "the file",
        "this file",
    )
    if any(k in lowered for k in doc_keywords):
        doc_id = _first_doc_id(text) or _first_uuid(text)
        if doc_id:
            suggestions.append(
                UIAction(
                    action_type="show_document",
                    args=_with_project({"document_id": doc_id}),
                    status=ActionStatus.EXECUTING,
                    display_text="View this document in the workspace",
                )
            )
        else:
            suggestions.append(
                UIAction(
                    action_type="navigate",
                    args={"page_id": "documents"},
                    status=ActionStatus.EXECUTING,
                    display_text="Open the documents area",
                )
            )

    # Search
    if any(w in lowered for w in ("search", "look up", "lookup", "find ")):
        q = _search_query_from_text(text)
        if q:
            suggestions.append(
                UIAction(
                    action_type="open_search",
                    args=_with_project({"query": q}),
                    status=ActionStatus.EXECUTING,
                    display_text=f'Search for "{q}"',
                )
            )

    # Upload
    if any(
        w in lowered
        for w in (
            "upload",
            "attach a file",
            "add a file",
            "import a file",
        )
    ):
        suggestions.append(
            UIAction(
                action_type="trigger_upload",
                args=_with_project({}),
                status=ActionStatus.EXECUTING,
                display_text="Upload a file",
            )
        )

    # Projects
    if any(
        w in lowered
        for w in (
            "new project",
            "create a project",
            "create project",
            "start a project",
        )
    ):
        suggestions.append(
            UIAction(
                action_type="create_project",
                args={},
                status=ActionStatus.EXECUTING,
                display_text="Create a project",
            )
        )

    # Code execution hint (extensible action type)
    code_fence = "```" in text
    code_words = any(
        w in lowered
        for w in (
            "run the code",
            "execute the",
            "run this script",
            "execute this",
            "try running",
        )
    )
    if code_fence and code_words:
        suggestions.append(
            UIAction(
                action_type="run_code",
                args=_with_project({}),
                status=ActionStatus.EXECUTING,
                display_text="Run the suggested code",
            )
        )

    # De-duplicate by (action_type, sorted args items)
    seen: set[tuple[str, tuple[tuple[str, Any], ...]]] = set()
    unique: list[UIAction] = []
    for a in suggestions:
        key = (a.action_type, tuple(sorted((a.args or {}).items())))
        if key in seen:
            continue
        seen.add(key)
        unique.append(a)

    return unique
