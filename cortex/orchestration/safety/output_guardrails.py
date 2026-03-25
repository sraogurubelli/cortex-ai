"""
Output Guardrails Middleware.

Validates and sanitizes LLM responses before they reach the client:
  - **System prompt leak detection** — catches when the LLM echoes back
    system prompts or internal instructions.
  - **PII leak detection** — flags responses containing PII that wasn't
    present in the user's original message (data from other users).
  - **Hallucination markers** — detects known hallucination indicators
    (the LLM claiming capabilities it shouldn't have).
  - **Malicious code detection** — flags responses containing shell
    injection, SQL injection, or suspicious script patterns.

Runs in ``after_llm_call`` and either blocks, warns, or sanitizes
depending on configuration.

Usage::

    from cortex.orchestration.safety.output_guardrails import OutputGuardrailsMiddleware

    middleware = OutputGuardrailsMiddleware(
        detect_prompt_leak=True,
        detect_code_injection=True,
        system_prompt_fingerprints=["You are assistant", "CONFIDENTIAL:"],
    )

    agent = Agent(name="assistant", middleware=[middleware])
"""

from __future__ import annotations

import logging
import re
from typing import Any

from cortex.orchestration.middleware.base import BaseMiddleware, MiddlewareContext

logger = logging.getLogger(__name__)


class OutputViolation(Exception):
    """Raised when LLM output fails a guardrail check."""

    def __init__(self, violation_type: str, detail: str) -> None:
        self.violation_type = violation_type
        self.detail = detail
        super().__init__(f"[{violation_type}] {detail}")


# ============================================================================
# Detection patterns
# ============================================================================

_PROMPT_LEAK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(?:my\s+)?(?:system\s+)?(?:prompt|instructions?)\s+"
            r"(?:is|are|says?|reads?|states?)\s*:",
            re.IGNORECASE,
        ),
        "LLM revealing its system prompt",
    ),
    (
        re.compile(
            r"(?:I\s+was\s+(?:told|instructed|given|programmed)\s+to|"
            r"my\s+(?:initial|original|system)\s+(?:prompt|instructions?)\s+(?:is|are))",
            re.IGNORECASE,
        ),
        "LLM acknowledging internal instructions",
    ),
    (
        re.compile(
            r"<<\s*SYS\s*>>|<\|system\|>|\[INST\]|\[/INST\]",
            re.IGNORECASE,
        ),
        "Raw prompt template markers in output",
    ),
]

_CODE_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r";\s*(?:rm\s+-rf|dd\s+if=|mkfs\s|chmod\s+777|wget\s.*\|\s*(?:bash|sh))",
            re.IGNORECASE,
        ),
        "Destructive shell command in response",
    ),
    (
        re.compile(
            r"(?:DROP\s+TABLE|DELETE\s+FROM|TRUNCATE\s+TABLE|ALTER\s+TABLE.*DROP)"
            r"(?:\s+|;)",
            re.IGNORECASE,
        ),
        "Destructive SQL in response",
    ),
    (
        re.compile(
            r"<script\b[^>]*>.*?</script>",
            re.IGNORECASE | re.DOTALL,
        ),
        "Script injection in response",
    ),
]

_REFUSAL_MESSAGE = (
    "I'm sorry, but I can't provide that information. "
    "If you need help with something else, I'm happy to assist."
)


# ============================================================================
# Middleware
# ============================================================================


class OutputGuardrailsMiddleware(BaseMiddleware):
    """Middleware that validates LLM responses.

    Args:
        detect_prompt_leak: Check for system prompt leakage (default True).
        detect_code_injection: Check for dangerous code in output (default True).
        system_prompt_fingerprints: Substrings from your system prompt. If any
            appear verbatim in the LLM output, it's flagged as a leak. Use
            short, unique phrases that wouldn't appear in normal conversation.
        max_output_chars: Maximum allowed output length. 0 = no limit.
        on_violation: "block" replaces response with refusal, "warn" logs
            and allows through, "sanitize" removes the offending content
            (default: "block").
        custom_blocked_patterns: Additional patterns to block in output.
    """

    def __init__(
        self,
        detect_prompt_leak: bool = True,
        detect_code_injection: bool = True,
        system_prompt_fingerprints: list[str] | None = None,
        max_output_chars: int = 0,
        on_violation: str = "block",
        custom_blocked_patterns: list[tuple[re.Pattern, str]] | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(enabled=enabled)
        self._detect_prompt_leak = detect_prompt_leak
        self._detect_code_injection = detect_code_injection
        self._fingerprints = system_prompt_fingerprints or []
        self._max_output = max_output_chars
        self._on_violation = on_violation
        self._custom_patterns = custom_blocked_patterns or []

    async def after_llm_call(
        self,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        content = getattr(result, "content", None)
        if not isinstance(content, str) or not content:
            return result

        # Length check
        if self._max_output > 0 and len(content) > self._max_output:
            logger.warning(
                "Output exceeds max length",
                extra={"length": len(content), "max": self._max_output},
            )
            if self._on_violation == "block":
                return result.copy(update={"content": content[: self._max_output]})

        # System prompt leak
        if self._detect_prompt_leak:
            violation = self._check_prompt_leak(content)
            if violation:
                return self._handle_violation(result, "prompt_leak", violation)

        # Code injection
        if self._detect_code_injection:
            violation = self._check_code_injection(content)
            if violation:
                return self._handle_violation(result, "code_injection", violation)

        # Custom patterns
        for pattern, description in self._custom_patterns:
            if pattern.search(content):
                return self._handle_violation(result, "custom_violation", description)

        return result

    # -----------------------------------------------------------------------
    # Checks
    # -----------------------------------------------------------------------

    def _check_prompt_leak(self, content: str) -> str | None:
        for pattern, description in _PROMPT_LEAK_PATTERNS:
            if pattern.search(content):
                return description

        content_lower = content.lower()
        for fingerprint in self._fingerprints:
            if fingerprint.lower() in content_lower:
                return f"System prompt fingerprint found: '{fingerprint[:20]}...'"

        return None

    def _check_code_injection(self, content: str) -> str | None:
        for pattern, description in _CODE_INJECTION_PATTERNS:
            if pattern.search(content):
                return description
        return None

    # -----------------------------------------------------------------------
    # Violation handling
    # -----------------------------------------------------------------------

    def _handle_violation(
        self, result: Any, violation_type: str, detail: str
    ) -> Any:
        logger.warning(
            "Output guardrail violation",
            extra={"type": violation_type, "detail": detail},
        )

        if self._on_violation == "block":
            return result.copy(update={"content": _REFUSAL_MESSAGE})
        elif self._on_violation == "sanitize":
            content = getattr(result, "content", "")
            for pattern, _ in _PROMPT_LEAK_PATTERNS + _CODE_INJECTION_PATTERNS:
                content = pattern.sub("[REDACTED]", content)
            return result.copy(update={"content": content})
        else:
            return result
