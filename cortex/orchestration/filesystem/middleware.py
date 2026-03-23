"""
Filesystem middleware and prompts for swarm agents.

Provides:

1. A ``FilesystemMiddleware`` that intercepts tool results and evicts
   large outputs to the shared ``files`` dict in ``SwarmState``.
2. System prompt guidance for agents on how to use the shared filesystem.

This is a self-contained implementation that does **not** depend on the
``deepagents`` package.  Large tool results are stored in state (and thus
checkpointed by whatever backend the graph uses — MemorySaver, Postgres,
etc.)  instead of writing to the local OS filesystem.

Ported from ml-infra orchestration_sdk/filesystem/prompts.py.
"""

import logging
import uuid
from typing import Any, Optional

from cortex.orchestration.middleware.base import BaseMiddleware, MiddlewareContext

logger = logging.getLogger(__name__)

FILESYSTEM_AGENT_PROMPT = """\
## Agent Filesystem

You have access to a shared filesystem that persists across conversation turns.
Files are stored in the conversation state and checkpointed automatically.

### Path Conventions
- Your workspace is under `/{agent_name}/` — use this prefix for files you create.
- Other agents' files are under their own prefixes (e.g. `/researcher/`, `/writer/`).
  You can read them when collaborating on a problem.
- `/large_tool_results/` contains automatically saved large tool outputs.

### Large Tool Results
When a tool returns a very large result, it is automatically saved to
`/large_tool_results/<id>` and replaced with a truncated preview plus the
file path.  To access the full result, read the file at the path shown in
the preview.

### File Naming
When you write your own files (analysis, summaries, intermediate findings),
use descriptive names that make the content obvious at a glance:
- `/{agent_name}/pipeline_analysis.md` — not `/{agent_name}/output1.txt`
- `/{agent_name}/error_logs_ci_stage.txt` — not `/{agent_name}/data.txt`

### Best Practices
- Write summaries or structured findings to your workspace so other agents
  can build on your work.
- Do NOT copy large tool results into your workspace just to rename them.
  Read them directly from `/large_tool_results/`.
"""


def get_filesystem_prompt(agent_name: str) -> str:
    """Return filesystem guidance tailored to *agent_name*.

    Intended to be appended to the agent's system prompt.
    """
    return FILESYSTEM_AGENT_PROMPT.replace("{agent_name}", agent_name)


class FilesystemMiddleware(BaseMiddleware):
    """Middleware that evicts large tool results to the shared state filesystem.

    When a tool returns a result whose string length exceeds
    ``char_limit_before_evict``, the full result is stored as a file in
    the ``files`` dict (part of ``SwarmState``) and the tool result is
    replaced with a truncated preview containing the file path.

    Handoff tools (``transfer_to_*``) are always passed through without
    interception to preserve ``Command`` routing in langgraph-swarm.

    Args:
        char_limit_before_evict: Approximate character count above which a
            tool result is evicted.  Default ``80_000`` (roughly 20k tokens).
        preview_length: Number of characters to keep in the preview.
    """

    def __init__(
        self,
        char_limit_before_evict: int = 80_000,
        preview_length: int = 2_000,
        enabled: bool = True,
    ):
        super().__init__(enabled=enabled)
        self._char_limit = char_limit_before_evict
        self._preview_length = preview_length
        self._pending_files: dict[str, str] = {}

    async def after_tool_call(
        self,
        tool_name: str,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Evict large tool results to the shared filesystem."""
        if not self.enabled:
            return result

        # Never intercept handoff tools
        if tool_name.startswith("transfer_to_"):
            return result

        text = str(result) if not isinstance(result, str) else result

        if len(text) <= self._char_limit:
            return result

        file_id = str(uuid.uuid4())[:8]
        file_path = f"/large_tool_results/{tool_name}_{file_id}"

        self._pending_files[file_path] = text

        preview = text[: self._preview_length]
        agent_name = context.agent_name if context else "unknown"
        logger.info(
            "Evicted large tool result to %s (%d chars, agent=%s)",
            file_path,
            len(text),
            agent_name,
        )

        return (
            f"{preview}\n\n"
            f"[Full result ({len(text):,} chars) saved to `{file_path}`. "
            f"Use `read_file` to access the complete output.]"
        )

    def pop_pending_files(self) -> dict[str, str]:
        """Return and clear files waiting to be merged into state.

        Call this from the graph node that runs tools to merge evicted
        files into ``SwarmState.files``::

            files_update = fs_middleware.pop_pending_files()
            if files_update:
                state["files"].update(files_update)
        """
        files = self._pending_files
        self._pending_files = {}
        return files


def build_filesystem_middleware(
    agent_name: str = "agent",
    char_limit_before_evict: int = 80_000,
) -> FilesystemMiddleware:
    """Build a ``FilesystemMiddleware`` with sensible defaults.

    Args:
        agent_name: Used only for logging.
        char_limit_before_evict: Approximate character count above which
            a tool result is evicted.

    Returns:
        Configured ``FilesystemMiddleware`` instance.
    """
    logger.info(
        "Building filesystem middleware for agent=%s (char_limit=%d)",
        agent_name,
        char_limit_before_evict,
    )
    return FilesystemMiddleware(
        char_limit_before_evict=char_limit_before_evict,
    )
