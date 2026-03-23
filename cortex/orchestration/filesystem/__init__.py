"""
Shared filesystem middleware for swarm agents.

Provides a shared file store that lives in LangGraph state, enabling agents
in a swarm to read/write named files that persist across handoffs and
checkpoints.  Large tool results are automatically evicted to the filesystem
and replaced with truncated previews.

Usage::

    from cortex.orchestration.filesystem import (
        build_filesystem_middleware,
        get_filesystem_prompt,
        SwarmState,
    )

    fs_middleware = build_filesystem_middleware("researcher")
    fs_prompt = get_filesystem_prompt("researcher")

    config = AgentConfig(
        name="researcher",
        middleware=[fs_middleware],
        system_prompt=base_prompt + fs_prompt,
    )

Ported from ml-infra orchestration_sdk/filesystem/.
"""

from cortex.orchestration.filesystem.state import SwarmState
from cortex.orchestration.filesystem.middleware import (
    FILESYSTEM_AGENT_PROMPT,
    FilesystemMiddleware,
    build_filesystem_middleware,
    get_filesystem_prompt,
)

__all__ = [
    "SwarmState",
    "FILESYSTEM_AGENT_PROMPT",
    "FilesystemMiddleware",
    "build_filesystem_middleware",
    "get_filesystem_prompt",
]
