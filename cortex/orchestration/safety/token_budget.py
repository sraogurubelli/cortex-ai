"""
Token Budget Enforcement Middleware.

Prevents runaway costs by enforcing per-session token limits on both
input (prompt) and output (completion) tokens. When a budget is exceeded
the middleware either:
  - Raises ``TokenBudgetExceeded`` (hard limit), or
  - Logs a warning and allows through (soft limit).

Tracks cumulative token usage across multiple LLM calls within a single
session, so the budget applies to the *total* conversation cost — not
per-call.

Usage::

    from cortex.orchestration.safety.token_budget import TokenBudgetMiddleware

    middleware = TokenBudgetMiddleware(
        max_total_tokens=100_000,
        max_completion_tokens=50_000,
        on_exceed="block",
    )

    agent = Agent(name="assistant", middleware=[middleware])

Environment Variables:
    CORTEX_TOKEN_BUDGET_MAX_TOTAL: Max total tokens per session (default: 0 = unlimited)
    CORTEX_TOKEN_BUDGET_MAX_COMPLETION: Max completion tokens (default: 0 = unlimited)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from cortex.orchestration.middleware.base import BaseMiddleware, MiddlewareContext

logger = logging.getLogger(__name__)


class TokenBudgetExceeded(Exception):
    """Raised when a token budget is exceeded."""

    def __init__(self, budget_type: str, used: int, limit: int) -> None:
        self.budget_type = budget_type
        self.used = used
        self.limit = limit
        super().__init__(
            f"Token budget exceeded: {budget_type} "
            f"({used:,} used / {limit:,} limit)"
        )


class TokenBudgetMiddleware(BaseMiddleware):
    """Middleware that enforces per-session token budgets.

    Tracks usage from ``after_llm_call`` by inspecting the response's
    ``usage_metadata`` or ``response_metadata``. The cumulative count
    is checked in ``before_llm_call`` for subsequent calls.

    Args:
        max_total_tokens: Maximum total tokens (prompt + completion).
            0 = unlimited.
        max_prompt_tokens: Maximum prompt/input tokens. 0 = unlimited.
        max_completion_tokens: Maximum completion/output tokens.
            0 = unlimited.
        on_exceed: "block" raises TokenBudgetExceeded, "warn" logs
            and allows through (default: "block").
        warn_threshold: When cumulative usage reaches this fraction
            of the limit (e.g. 0.8 = 80%), emit a warning log.
    """

    def __init__(
        self,
        max_total_tokens: int = 0,
        max_prompt_tokens: int = 0,
        max_completion_tokens: int = 0,
        on_exceed: str = "block",
        warn_threshold: float = 0.8,
        enabled: bool = True,
    ) -> None:
        super().__init__(enabled=enabled)

        self._max_total = int(
            os.getenv("CORTEX_TOKEN_BUDGET_MAX_TOTAL", str(max_total_tokens))
        )
        self._max_prompt = max_prompt_tokens
        self._max_completion = int(
            os.getenv(
                "CORTEX_TOKEN_BUDGET_MAX_COMPLETION", str(max_completion_tokens)
            )
        )
        self._on_exceed = on_exceed
        self._warn_threshold = warn_threshold

        self._used_prompt = 0
        self._used_completion = 0

    @property
    def used_total(self) -> int:
        return self._used_prompt + self._used_completion

    @property
    def used_prompt(self) -> int:
        return self._used_prompt

    @property
    def used_completion(self) -> int:
        return self._used_completion

    def get_usage_summary(self) -> dict[str, int]:
        """Return a summary of token usage for this session."""
        return {
            "prompt_tokens": self._used_prompt,
            "completion_tokens": self._used_completion,
            "total_tokens": self.used_total,
        }

    def reset(self) -> None:
        """Reset cumulative counters (useful between sessions)."""
        self._used_prompt = 0
        self._used_completion = 0

    async def before_llm_call(
        self,
        messages: list[Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Check budget before each LLM call."""
        self._check_budget("total", self.used_total, self._max_total)
        self._check_budget("prompt", self._used_prompt, self._max_prompt)
        self._check_budget("completion", self._used_completion, self._max_completion)

        return messages, kwargs

    async def after_llm_call(
        self,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        """Record token usage from the LLM response."""
        usage = getattr(result, "usage_metadata", None)
        if usage:
            prompt = (
                usage.get("input_tokens", 0)
                if isinstance(usage, dict)
                else getattr(usage, "input_tokens", 0)
            )
            completion = (
                usage.get("output_tokens", 0)
                if isinstance(usage, dict)
                else getattr(usage, "output_tokens", 0)
            )
        else:
            resp_meta = getattr(result, "response_metadata", {}) or {}
            token_usage = resp_meta.get("token_usage", {})
            prompt = token_usage.get("prompt_tokens", 0)
            completion = token_usage.get("completion_tokens", 0)

        self._used_prompt += prompt
        self._used_completion += completion

        self._check_threshold("total", self.used_total, self._max_total)
        self._check_threshold("prompt", self._used_prompt, self._max_prompt)
        self._check_threshold("completion", self._used_completion, self._max_completion)

        return result

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _check_budget(self, budget_type: str, used: int, limit: int) -> None:
        if limit <= 0:
            return
        if used >= limit:
            msg = (
                f"Token budget exceeded: {budget_type} "
                f"({used:,} used / {limit:,} limit)"
            )
            if self._on_exceed == "block":
                raise TokenBudgetExceeded(budget_type, used, limit)
            else:
                logger.warning(msg)

    def _check_threshold(self, budget_type: str, used: int, limit: int) -> None:
        if limit <= 0 or self._warn_threshold <= 0:
            return
        threshold = int(limit * self._warn_threshold)
        if used >= threshold and (used - threshold) < max(1, limit // 20):
            logger.warning(
                "Approaching token budget limit",
                extra={
                    "budget_type": budget_type,
                    "used": used,
                    "limit": limit,
                    "percent": round(used / limit * 100, 1),
                },
            )
