"""Model Usage Tracking for token consumption.

Provides ``ModelUsage`` (per-model accumulator) and ``ModelUsageTracker``
(session-level aggregator).  The tracker can record usage from:

- Explicit ``record(model, prompt_tokens, completion_tokens)`` calls.
- LangGraph ``astream_events`` dicts via ``record_from_event(event)``.
- Post-hoc message lists via ``record_from_messages(messages)``.

Cache token tracking (Anthropic prompt caching) is built in -- cache
metrics are nested inside each model's usage dict (under a ``"cache"``
key).  Use ``get_cache_usage()`` for aggregated totals across all models.

The module-level ``resolve_model_name`` helper extracts a model identifier
from any object carrying LangChain-style ``response_metadata`` or
``usage_metadata`` attributes (duck-typed -- no framework import required).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# =========================================================================
# Module-level helper
# =========================================================================


def resolve_model_name(output: Any) -> str:
    """Extract model name from a LangChain message's metadata.

    Tries multiple metadata keys in priority order and falls back to
    ``"unknown"`` when none are present.  Uses duck typing -- works with any
    object that has ``response_metadata`` or ``usage_metadata`` attributes.
    """
    response_metadata = getattr(output, "response_metadata", {}) or {}
    usage_metadata = getattr(output, "usage_metadata", {}) or {}
    return (
        response_metadata.get("model")
        or response_metadata.get("model_name")
        or response_metadata.get("model_id")
        or usage_metadata.get("model_name")
        or "unknown"
    )


# =========================================================================
# Per-model usage accumulator
# =========================================================================


@dataclass
class ModelUsage:
    """Token usage for a single model."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.prompt_tokens + self.completion_tokens

    def add(self, prompt: int = 0, completion: int = 0) -> None:
        """
        Add token usage.

        Args:
            prompt: Prompt/input tokens
            completion: Completion/output tokens
        """
        self.prompt_tokens += prompt
        self.completion_tokens += completion

    def add_cache(self, cache_read: int = 0, cache_creation: int = 0) -> None:
        """Add cache token usage (Anthropic prompt caching)."""
        self.cache_read_tokens += cache_read
        self.cache_creation_tokens += cache_creation

    def to_dict(self) -> dict:
        """Convert to dict for event data."""
        d: dict = {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }
        if self.cache_read_tokens or self.cache_creation_tokens:
            cache: dict[str, int] = {}
            if self.cache_read_tokens:
                cache["cache_read"] = self.cache_read_tokens
            if self.cache_creation_tokens:
                cache["cache_creation"] = self.cache_creation_tokens
            d["cache"] = cache
        return d


# =========================================================================
# Session-level usage tracker
# =========================================================================


class ModelUsageTracker:
    """
    Tracks token usage across LLM calls in a session.

    Supports three recording modes:

    1. **Explicit** -- ``record(model, prompt_tokens, completion_tokens)``
    2. **Event-based** -- ``record_from_event(event)`` for LangGraph
       ``astream_events`` dicts (only processes ``on_chat_model_end``).
    3. **Message-based** -- ``record_from_messages(messages)`` for post-hoc
       extraction from a list of LangChain messages.

    Cache token metrics (Anthropic prompt caching) are tracked
    automatically when ``input_token_details`` is present in
    ``usage_metadata``.

    Example::

        tracker = ModelUsageTracker()

        # Record usage from LLM responses
        tracker.record("gpt-4o", prompt_tokens=100, completion_tokens=50)
        tracker.record("gpt-4o", prompt_tokens=200, completion_tokens=100)

        # Get aggregated usage
        usage = tracker.get_usage()
        # {"gpt-4o": {"prompt_tokens": 300, "completion_tokens": 150, "total_tokens": 450}}
    """

    def __init__(self) -> None:
        self._usage: dict[str, ModelUsage] = {}

    # -----------------------------------------------------------------
    # Explicit recording (existing API, unchanged)
    # -----------------------------------------------------------------

    def record(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """
        Record token usage for a model.

        Args:
            model: Model name
            prompt_tokens: Prompt/input tokens
            completion_tokens: Completion/output tokens
        """
        if model not in self._usage:
            self._usage[model] = ModelUsage()
        self._usage[model].add(prompt_tokens, completion_tokens)

    # -----------------------------------------------------------------
    # Event-based recording (new)
    # -----------------------------------------------------------------

    def record_from_event(self, event: dict) -> None:
        """Record usage from a LangGraph ``astream_events`` event.

        Only processes ``on_chat_model_end`` events.  All others --
        including ``on_llm_end`` -- are ignored to prevent
        double-counting when both fire for the same LLM call.

        Args:
            event: A LangGraph event dict from ``astream_events(version="v2")``.
        """
        if event.get("event") != "on_chat_model_end":
            return
        output = event.get("data", {}).get("output")
        if output is not None:
            self._record_from_output(output)

    # -----------------------------------------------------------------
    # Message-based recording (new)
    # -----------------------------------------------------------------

    def record_from_messages(self, messages: list) -> None:
        """Record usage from a list of LangChain messages (post-hoc).

        Iterates *messages* and extracts ``usage_metadata`` from any that
        carry it.  Uses duck typing so no ``AIMessage`` import is needed.

        Args:
            messages: A list of LangChain ``BaseMessage`` objects (or any
                objects with ``usage_metadata`` / ``response_metadata``
                attributes).
        """
        for msg in messages:
            if hasattr(msg, "usage_metadata") or hasattr(msg, "response_metadata"):
                self._record_from_output(msg)

    # -----------------------------------------------------------------
    # Retrieval
    # -----------------------------------------------------------------

    def get_usage(self) -> dict[str, dict]:
        """
        Get all usage formatted for event.

        Returns:
            Dict mapping model name to usage dict.  Each model dict includes
            ``prompt_tokens``, ``completion_tokens``, ``total_tokens``, and
            optionally a ``cache`` sub-dict when cache tokens were recorded.
        """
        return {model: usage.to_dict() for model, usage in self._usage.items()}

    def get_total_tokens(self) -> int:
        """Get total tokens across all models."""
        return sum(usage.total_tokens for usage in self._usage.values())

    def get_cache_usage(self) -> dict[str, int]:
        """Get accumulated cache token counts across all models.

        Returns a dict with ``cache_read`` and/or ``cache_creation`` keys,
        or an empty dict if no cache tokens were recorded.
        """
        total_read = sum(u.cache_read_tokens for u in self._usage.values())
        total_creation = sum(u.cache_creation_tokens for u in self._usage.values())
        result: dict[str, int] = {}
        if total_read:
            result["cache_read"] = total_read
        if total_creation:
            result["cache_creation"] = total_creation
        return result

    def reset(self) -> None:
        """Reset all tracking."""
        self._usage.clear()

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _record_from_output(self, output: Any) -> None:
        """Extract and record usage from any object with ``usage_metadata``.

        Falls back to ``response_metadata.token_usage`` for providers that
        do not populate ``usage_metadata`` (e.g. LLM Gateway).
        """
        resp_meta = getattr(output, "response_metadata", {}) or {}
        usage = getattr(output, "usage_metadata", None)
        if usage:
            model = resolve_model_name(output)
            self.record(
                model,
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )
            self._accumulate_cache_tokens(model, usage, resp_meta)
        else:
            fallback = resp_meta.get("token_usage", {})
            if fallback:
                model = resolve_model_name(output)
                self.record(
                    model,
                    fallback.get("prompt_tokens", 0),
                    fallback.get("completion_tokens", 0),
                )
                self._accumulate_cache_tokens(model, None, resp_meta)

    def _accumulate_cache_tokens(
        self, model: str, usage_metadata: Any, response_metadata: dict | None = None
    ) -> None:
        """Accumulate cache token details onto the per-model ModelUsage.

        Checks ``usage_metadata.input_token_details`` first (direct Anthropic),
        then falls back to ``response_metadata.token_usage`` fields for gateway
        responses where ChatOpenAI doesn't fully map cache fields.
        """
        cache_read = 0
        cache_creation = 0

        if usage_metadata is not None:
            if isinstance(usage_metadata, dict):
                details = usage_metadata.get("input_token_details") or {}
            else:
                details = getattr(usage_metadata, "input_token_details", {}) or {}
                if not isinstance(details, dict):
                    details = dict(details) if details else {}
            cache_read = details.get("cache_read", 0) or 0
            cache_creation = details.get("cache_creation", 0) or 0

        if not cache_creation and response_metadata:
            token_usage = response_metadata.get("token_usage", {})
            if token_usage:
                if not cache_read:
                    cache_read = token_usage.get("cache_read_input_tokens", 0) or 0
                cache_creation = token_usage.get("cache_creation_input_tokens", 0) or 0
                if not cache_creation:
                    ptd = token_usage.get("prompt_tokens_details") or {}
                    cache_creation = ptd.get("cache_creation_tokens", 0) or 0

        if cache_read or cache_creation:
            if model not in self._usage:
                self._usage[model] = ModelUsage()
            self._usage[model].add_cache(cache_read, cache_creation)
