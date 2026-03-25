"""
Input Guardrails Middleware.

Detects and blocks malicious or unsafe user inputs before they reach the LLM:
  - **Prompt injection** — detects attempts to override system prompts.
  - **Content safety** — blocks toxic, harmful, or prohibited content.
  - **Input length limits** — prevents excessively long inputs.
  - **Repetition detection** — catches pathological repeated strings.

The middleware runs in ``before_llm_call`` and raises ``GuardrailViolation``
when a violation is detected, which the orchestrator converts to an error
event on the stream.

Usage::

    from cortex.orchestration.safety.input_guardrails import InputGuardrailsMiddleware

    middleware = InputGuardrailsMiddleware(
        block_prompt_injection=True,
        block_unsafe_content=True,
        max_input_chars=50_000,
    )

    agent = Agent(name="assistant", middleware=[middleware])

Environment Variables:
    CORTEX_GUARDRAILS_ENABLED: Enable input guardrails (default: true)
    CORTEX_GUARDRAILS_MAX_INPUT_CHARS: Max input character length (default: 50000)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from cortex.orchestration.middleware.base import BaseMiddleware, MiddlewareContext

logger = logging.getLogger(__name__)


class GuardrailViolation(Exception):
    """Raised when input fails a guardrail check.

    Attributes:
        violation_type: Category of the violation.
        detail: Human-readable description.
    """

    def __init__(self, violation_type: str, detail: str) -> None:
        self.violation_type = violation_type
        self.detail = detail
        super().__init__(f"[{violation_type}] {detail}")


# ============================================================================
# Prompt injection patterns
# ============================================================================

_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"ignore\s+(?:all\s+)?(?:previous|above|prior|earlier)\s+"
            r"(?:instructions?|prompts?|context|rules?|guidelines?)",
            re.IGNORECASE,
        ),
        "Attempt to override system instructions",
    ),
    (
        re.compile(
            r"(?:forget|disregard|override|bypass)\s+"
            r"(?:all\s+)?(?:your|the|system|initial)\s+"
            r"(?:instructions?|prompts?|rules?|constraints?|guidelines?)",
            re.IGNORECASE,
        ),
        "Attempt to override system instructions",
    ),
    (
        re.compile(
            r"you\s+are\s+(?:now|actually)\s+(?:a|an)\s+",
            re.IGNORECASE,
        ),
        "Role reassignment attempt",
    ),
    (
        re.compile(
            r"(?:system|developer|admin)\s*(?:prompt|message|instruction)\s*:",
            re.IGNORECASE,
        ),
        "Fake system message injection",
    ),
    (
        re.compile(
            r"<\s*(?:system|instruction|prompt)\s*>",
            re.IGNORECASE,
        ),
        "XML tag injection (system/instruction)",
    ),
    (
        re.compile(
            r"(?:print|reveal|show|output|display|repeat|tell\s+me)\s+"
            r"(?:your|the|initial|original|system)\s+"
            r"(?:prompt|instructions?|rules?|system\s+message)",
            re.IGNORECASE,
        ),
        "System prompt exfiltration attempt",
    ),
    (
        re.compile(
            r"(?:DAN|jailbreak|evil\s+mode|developer\s+mode|god\s+mode)\s*"
            r"(?:mode|prompt|enabled?)",
            re.IGNORECASE,
        ),
        "Known jailbreak pattern",
    ),
]

# ============================================================================
# Content safety patterns
# ============================================================================

_UNSAFE_CONTENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(?:how\s+to|instructions?\s+(?:for|to)|steps?\s+to|guide\s+(?:to|for))\s+"
            r"(?:make|build|create|synthesize|manufacture)\s+"
            r"(?:a\s+)?(?:bomb|explosive|weapon|poison|drug|meth)",
            re.IGNORECASE,
        ),
        "Harmful content: weapon/drug synthesis",
    ),
    (
        re.compile(
            r"(?:hack|break\s+into|exploit|compromise)\s+"
            r"(?:a\s+|the\s+)?(?:bank|government|military|hospital|school)",
            re.IGNORECASE,
        ),
        "Harmful content: illegal hacking guidance",
    ),
]


# ============================================================================
# Middleware
# ============================================================================


class InputGuardrailsMiddleware(BaseMiddleware):
    """Middleware that validates user inputs against safety rules.

    Checks are applied to user messages (``HumanMessage``) only — system
    messages and assistant messages pass through.

    Args:
        block_prompt_injection: Detect and block prompt injection (default True).
        block_unsafe_content: Detect and block harmful content (default True).
        max_input_chars: Maximum allowed input length in characters.
            Set to 0 to disable length check.
        max_repetition_ratio: Maximum ratio of repeated characters (0.0–1.0).
            Catches inputs like "aaaaaa..." that can waste tokens.
        custom_blocked_patterns: Additional regex patterns to block.
            Each entry is (compiled_regex, description).
        on_violation: Action on violation. "block" raises an error,
            "warn" logs and allows through (default: "block").
    """

    def __init__(
        self,
        block_prompt_injection: bool = True,
        block_unsafe_content: bool = True,
        max_input_chars: int = 50_000,
        max_repetition_ratio: float = 0.7,
        custom_blocked_patterns: list[tuple[re.Pattern, str]] | None = None,
        on_violation: str = "block",
        enabled: bool = True,
    ) -> None:
        env_enabled = os.getenv(
            "CORTEX_GUARDRAILS_ENABLED", "true"
        ).lower() in ("true", "1", "yes")
        super().__init__(enabled=enabled and env_enabled)

        self._block_injection = block_prompt_injection
        self._block_unsafe = block_unsafe_content
        self._max_chars = int(
            os.getenv("CORTEX_GUARDRAILS_MAX_INPUT_CHARS", str(max_input_chars))
        )
        self._max_repetition = max_repetition_ratio
        self._custom_patterns = custom_blocked_patterns or []
        self._on_violation = on_violation

    async def before_llm_call(
        self,
        messages: list[Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        for msg in messages:
            msg_type = type(msg).__name__
            if msg_type not in ("HumanMessage", "HumanMessageChunk"):
                continue

            content = getattr(msg, "content", "")
            if not isinstance(content, str):
                continue

            self._check_length(content)
            self._check_repetition(content)

            if self._block_injection:
                self._check_prompt_injection(content)

            if self._block_unsafe:
                self._check_content_safety(content)

            if self._custom_patterns:
                self._check_custom_patterns(content)

        return messages, kwargs

    # -----------------------------------------------------------------------
    # Individual checks
    # -----------------------------------------------------------------------

    def _check_length(self, content: str) -> None:
        if self._max_chars > 0 and len(content) > self._max_chars:
            self._raise_or_warn(
                "input_too_long",
                f"Input exceeds maximum length ({len(content)} > {self._max_chars} chars)",
            )

    def _check_repetition(self, content: str) -> None:
        if not content or len(content) < 100:
            return
        from collections import Counter
        char_counts = Counter(content)
        most_common_count = char_counts.most_common(1)[0][1]
        ratio = most_common_count / len(content)
        if ratio > self._max_repetition:
            self._raise_or_warn(
                "excessive_repetition",
                f"Input has excessive character repetition (ratio={ratio:.2f})",
            )

    def _check_prompt_injection(self, content: str) -> None:
        for pattern, description in _INJECTION_PATTERNS:
            if pattern.search(content):
                self._raise_or_warn("prompt_injection", description)
                return

    def _check_content_safety(self, content: str) -> None:
        for pattern, description in _UNSAFE_CONTENT_PATTERNS:
            if pattern.search(content):
                self._raise_or_warn("unsafe_content", description)
                return

    def _check_custom_patterns(self, content: str) -> None:
        for pattern, description in self._custom_patterns:
            if pattern.search(content):
                self._raise_or_warn("custom_violation", description)
                return

    def _raise_or_warn(self, violation_type: str, detail: str) -> None:
        if self._on_violation == "block":
            logger.warning(
                "Input guardrail violation",
                extra={"type": violation_type, "detail": detail},
            )
            raise GuardrailViolation(violation_type, detail)
        else:
            logger.warning(
                "Input guardrail warning (allowed through)",
                extra={"type": violation_type, "detail": detail},
            )
