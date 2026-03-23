"""
Pydantic schemas for UI action events.

These schemas define the wire format for SSE events that instruct the
frontend to perform UI actions.
"""

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActionStatus(str, Enum):
    """Execution status for UI actions."""

    EXECUTING = "executing"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    FAILED = "failed"


def _generate_action_id() -> str:
    return f"act_{uuid.uuid4().hex[:8]}"


class UIAction(BaseModel):
    """Event emitted when the agent instructs the frontend to perform an action.

    Sent as an SSE event with type ``ui_action``.
    """

    action_id: str = Field(default_factory=_generate_action_id)
    action_type: str = Field(
        ...,
        description=(
            "The type of action to perform.  Cortex-defined types: "
            "navigate, show_document, open_search, create_project, "
            "trigger_upload.  Extensible — the frontend ignores unknown types."
        ),
    )
    args: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = Field(default=ActionStatus.EXECUTING)
    display_text: str | None = Field(
        default=None,
        description="Optional human-readable description shown in the chat.",
    )

    model_config = {"use_enum_values": True}


class UIActionUpdate(BaseModel):
    """Status update for a previously emitted action.

    Sent as an SSE event with type ``ui_action_update``.
    """

    action_id: str = Field(
        ..., description="The action_id of the original UIAction."
    )
    status: ActionStatus
    result: dict[str, Any] | None = Field(
        default=None,
        description="Optional result payload from the frontend.",
    )

    model_config = {"use_enum_values": True}
