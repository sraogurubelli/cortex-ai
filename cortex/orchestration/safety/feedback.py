"""
Feedback Collection Hook.

Sends a structured ``collect_feedback`` SSE event to the client before
the ``done`` event, prompting the UI to display a feedback widget with
configurable reason options.

Ported from ml-infra's runner which sends feedback reasons at the end
of each session.

Usage::

    from cortex.orchestration.safety.feedback import FeedbackCollectionHook

    hook = FeedbackCollectionHook(
        reasons=["not_helpful", "inaccurate", "too_slow"],
    )

    config = SessionConfig(
        ...,
        event_hooks=[hook],
    )
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_FEEDBACK_REASONS = [
    "response_was_not_helpful",
    "did_not_fully_follow_instructions",
    "incorrect_output",
    "response_not_accurate",
    "performance_issues",
]


class FeedbackCollectionHook:
    """Session event hook that sends a feedback collection SSE event.

    Fires on ``on_session_complete`` — the orchestrator calls this
    before the ``done`` event, so the client sees the feedback prompt
    as part of the stream.

    Args:
        reasons: List of feedback reason identifiers shown to the user.
        event_name: SSE event name (default: "collect_feedback").
    """

    def __init__(
        self,
        reasons: list[str] | None = None,
        event_name: str = "collect_feedback",
    ) -> None:
        self._reasons = reasons or list(DEFAULT_FEEDBACK_REASONS)
        self._event_name = event_name

    async def on_session_start(self, config: Any, metadata: dict) -> None:
        pass

    async def on_session_complete(
        self, config: Any, result: Any, metadata: dict
    ) -> None:
        stream_writer = getattr(config, "stream_writer", None)
        if stream_writer is None:
            return

        try:
            await stream_writer.write_event(
                self._event_name,
                {
                    "reasons": self._reasons,
                    "conversation_id": getattr(config, "conversation_id", ""),
                },
            )
        except Exception:
            logger.debug("Failed to send feedback collection event")

    async def on_session_error(
        self, config: Any, error: Exception, metadata: dict
    ) -> None:
        pass
