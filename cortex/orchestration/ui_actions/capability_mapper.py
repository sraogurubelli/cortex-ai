"""
Map agent tools/skills to UI action types the agent may suggest or emit.

Use with :func:`continuation_detector.detect_suggested_actions_from_text` to
filter heuristic suggestions to only those the current toolset supports.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from cortex.orchestration.ui_actions.schemas import UIAction

logger = logging.getLogger(__name__)

# Substrings matched against normalized tool/skill names (lowercase).
_TOOL_PATTERN_TO_UI_ACTIONS: tuple[tuple[str, frozenset[str]], ...] = (
    ("read_file", frozenset({"show_document"})),
    ("document", frozenset({"show_document", "navigate"})),
    ("search", frozenset({"open_search", "navigate"})),
    ("retriev", frozenset({"open_search"})),
    ("upload", frozenset({"trigger_upload"})),
    ("import", frozenset({"trigger_upload", "navigate"})),
    ("project", frozenset({"create_project", "navigate"})),
    ("navigate", frozenset({"navigate"})),
    ("code", frozenset({"run_code"})),
    ("execute", frozenset({"run_code"})),
    ("python", frozenset({"run_code"})),
    ("shell", frozenset({"run_code"})),
    ("terminal", frozenset({"run_code"})),
    ("skill", frozenset({"navigate", "open_search"})),
)


def normalize_tool_name(name: str) -> str:
    """Lowercase and collapse separators for stable matching."""
    s = name.strip().lower()
    return re.sub(r"[\s\-_.]+", "_", s)


def ui_action_types_for_tools(tool_or_skill_names: Iterable[str]) -> frozenset[str]:
    """
    Return UI action type strings the agent is allowed to suggest, given its tools.

    Any agent with at least one tool gets a minimal default set so the UI can
    still offer navigation and search when appropriate.
    """
    names = [normalize_tool_name(n) for n in tool_or_skill_names if n and str(n).strip()]
    if not names:
        logger.debug("No tool names provided; returning empty UI action set")
        return frozenset()

    allowed: set[str] = set()
    for name in names:
        for pattern, actions in _TOOL_PATTERN_TO_UI_ACTIONS:
            if pattern in name:
                allowed.update(actions)

    # Baseline affordances when the agent has any tools
    allowed.update({"navigate", "open_search"})

    return frozenset(allowed)


def filter_suggestions_by_capabilities(
    suggestions: list[UIAction],
    allowed_action_types: Iterable[str],
) -> list[UIAction]:
    """Keep only suggestions whose ``action_type`` is in ``allowed_action_types``."""
    allowed = frozenset(allowed_action_types)
    return [a for a in suggestions if a.action_type in allowed]


def merge_tool_capabilities_with_suggestions(
    tool_or_skill_names: Iterable[str],
    suggestions: list[UIAction],
) -> list[UIAction]:
    """
    Filter heuristic suggestions to those permitted for the given tools.

    Convenience wrapper around :func:`ui_action_types_for_tools` and
    :func:`filter_suggestions_by_capabilities`.
    """
    allowed = ui_action_types_for_tools(tool_or_skill_names)
    return filter_suggestions_by_capabilities(suggestions, allowed)
