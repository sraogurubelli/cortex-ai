"""
Extended Swarm State with shared filesystem.

Adds a ``files`` dict to the standard LangGraph ``MessagesState`` so that
agents in a swarm can share persistent named files across handoffs.

The ``files`` dict is checkpointed alongside messages by the LangGraph
checkpointer (MemorySaver in dev, PostgresSaver in production).

Usage::

    from cortex.orchestration.filesystem.state import SwarmState

    # Use as the state type when compiling a swarm graph
    workflow = StateGraph(SwarmState)
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from langgraph.graph import MessagesState


def _merge_files(
    existing: dict[str, str], update: dict[str, str]
) -> dict[str, str]:
    """Merge file dicts: new keys are added, existing keys are overwritten."""
    merged = dict(existing)
    merged.update(update)
    return merged


class SwarmState(MessagesState):
    """LangGraph state extended with a shared filesystem.

    Attributes:
        files: Dict mapping virtual file paths (e.g. ``"/researcher/notes.md"``)
            to their string contents.  Automatically merged across state
            updates so agents can write files without stomping each other's
            work (last-write-wins per key).
    """

    files: Annotated[dict[str, str], _merge_files] = {}
