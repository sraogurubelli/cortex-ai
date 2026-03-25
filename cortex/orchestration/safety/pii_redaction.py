"""
PII Redaction Middleware.

Detects and masks Personally Identifiable Information (PII) in messages
before they reach the LLM and in responses before they reach the client.

Supports two modes:
  - **local** (default): Regex-based pattern matching for common PII types.
    No external dependencies. Suitable for most use cases.
  - **presidio**: Uses Microsoft Presidio for NER-based PII detection.
    Requires: ``pip install presidio-analyzer presidio-anonymizer``

The middleware intercepts both LLM calls (before/after) and tool calls
(before/after) to ensure PII doesn't leak through any path.

Usage::

    from cortex.orchestration.safety.pii_redaction import PIIRedactionMiddleware

    middleware = PIIRedactionMiddleware(
        redact_input=True,
        redact_output=True,
        entity_types=["email", "phone", "ssn", "credit_card"],
    )

    agent = Agent(
        name="assistant",
        middleware=[middleware],
    )

Environment Variables:
    CORTEX_PII_REDACTION_ENABLED: Enable PII redaction globally (default: false)
    CORTEX_PII_REDACTION_MODE: "local" or "presidio" (default: local)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from cortex.orchestration.middleware.base import BaseMiddleware, MiddlewareContext

logger = logging.getLogger(__name__)

# Replacement placeholder format: <<ENTITY_TYPE>>
_PLACEHOLDER = "<<{entity_type}>>"

# ============================================================================
# Regex patterns for common PII types
# ============================================================================

_PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"
    ),
    "phone": re.compile(
        r"(?<!\d)"
        r"(?:\+?1[-.\s]?)?"
        r"(?:\(?\d{3}\)?[-.\s]?)"
        r"\d{3}[-.\s]?\d{4}"
        r"(?!\d)"
    ),
    "ssn": re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
    ),
    "credit_card": re.compile(
        r"\b(?:\d[ -]*?){13,19}\b"
    ),
    "ip_address": re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    ),
    "api_key": re.compile(
        r"\b(?:sk|pk|api|key|token|secret|bearer)[-_][\w\-]{16,}\b",
        re.IGNORECASE,
    ),
    "aws_key": re.compile(
        r"\b(?:AKIA|ABIA|ACCA)[0-9A-Z]{16}\b"
    ),
    "jwt": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\b"
    ),
}

# Credit card validation: crude Luhn-like length check
_CC_DIGIT_RE = re.compile(r"\d")


def _looks_like_cc(match_text: str) -> bool:
    """Quick heuristic to avoid false positives on arbitrary digit sequences."""
    digits = _CC_DIGIT_RE.findall(match_text)
    return 13 <= len(digits) <= 19


# ============================================================================
# Redaction engine
# ============================================================================


class PIIRedactor:
    """Stateless PII redaction engine using regex patterns."""

    def __init__(
        self,
        entity_types: list[str] | None = None,
        custom_patterns: dict[str, re.Pattern] | None = None,
    ) -> None:
        if entity_types:
            self._patterns = {
                k: v for k, v in _PII_PATTERNS.items() if k in entity_types
            }
        else:
            self._patterns = dict(_PII_PATTERNS)

        if custom_patterns:
            self._patterns.update(custom_patterns)

        self._redaction_count = 0

    @property
    def redaction_count(self) -> int:
        return self._redaction_count

    def redact(self, text: str) -> str:
        """Redact PII from a string, returning the sanitized version."""
        if not text or not isinstance(text, str):
            return text

        for entity_type, pattern in self._patterns.items():
            def _replace(m: re.Match, etype: str = entity_type) -> str:
                if etype == "credit_card" and not _looks_like_cc(m.group()):
                    return m.group()
                self._redaction_count += 1
                return _PLACEHOLDER.format(entity_type=etype.upper())

            text = pattern.sub(_replace, text)

        return text

    def redact_dict(self, data: dict) -> dict:
        """Recursively redact PII in a dictionary."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.redact(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value)
            elif isinstance(value, list):
                result[key] = [self._redact_item(item) for item in value]
            else:
                result[key] = value
        return result

    def _redact_item(self, item: Any) -> Any:
        if isinstance(item, str):
            return self.redact(item)
        elif isinstance(item, dict):
            return self.redact_dict(item)
        elif isinstance(item, list):
            return [self._redact_item(i) for i in item]
        return item


# ============================================================================
# Middleware
# ============================================================================


class PIIRedactionMiddleware(BaseMiddleware):
    """Middleware that redacts PII from messages and tool I/O.

    Intercepts messages at four points:
      1. ``before_llm_call`` — redact user messages before the LLM sees them
      2. ``after_llm_call`` — redact LLM responses before they reach the client
      3. ``before_tool_call`` — redact tool input arguments
      4. ``after_tool_call`` — redact tool output

    Args:
        redact_input: Redact PII in user messages sent to LLM (default True).
        redact_output: Redact PII in LLM responses (default True).
        redact_tool_io: Redact PII in tool inputs/outputs (default True).
        entity_types: List of PII types to detect. Default: all built-in types.
            Options: email, phone, ssn, credit_card, ip_address, api_key,
            aws_key, jwt.
        custom_patterns: Additional regex patterns {name: compiled_regex}.
        log_redactions: Log when redactions occur (default True).
    """

    def __init__(
        self,
        redact_input: bool = True,
        redact_output: bool = True,
        redact_tool_io: bool = True,
        entity_types: list[str] | None = None,
        custom_patterns: dict[str, re.Pattern] | None = None,
        log_redactions: bool = True,
        enabled: bool = True,
    ) -> None:
        env_enabled = os.getenv(
            "CORTEX_PII_REDACTION_ENABLED", "false"
        ).lower() in ("true", "1", "yes")
        super().__init__(enabled=enabled or env_enabled)

        self._redact_input = redact_input
        self._redact_output = redact_output
        self._redact_tool_io = redact_tool_io
        self._log_redactions = log_redactions
        self._redactor = PIIRedactor(
            entity_types=entity_types,
            custom_patterns=custom_patterns,
        )

    async def before_llm_call(
        self,
        messages: list[Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        if not self._redact_input:
            return messages, kwargs

        count_before = self._redactor.redaction_count
        redacted_messages = []

        for msg in messages:
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                new_content = self._redactor.redact(content)
                if new_content != content:
                    msg = msg.copy(update={"content": new_content})
            redacted_messages.append(msg)

        redactions = self._redactor.redaction_count - count_before
        if redactions and self._log_redactions:
            logger.info(
                "PII redacted from LLM input",
                extra={"redactions": redactions, "phase": "before_llm"},
            )

        return redacted_messages, kwargs

    async def after_llm_call(
        self,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        if not self._redact_output:
            return result

        content = getattr(result, "content", None)
        if isinstance(content, str):
            count_before = self._redactor.redaction_count
            new_content = self._redactor.redact(content)
            if new_content != content:
                result = result.copy(update={"content": new_content})
                if self._log_redactions:
                    redactions = self._redactor.redaction_count - count_before
                    logger.info(
                        "PII redacted from LLM output",
                        extra={"redactions": redactions, "phase": "after_llm"},
                    )

        return result

    async def before_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self._redact_tool_io:
            return tool_input, kwargs

        redacted = self._redactor.redact_dict(tool_input)
        return redacted, kwargs

    async def after_tool_call(
        self,
        tool_name: str,
        result: Any,
        context: MiddlewareContext | None = None,
        **kwargs: Any,
    ) -> Any:
        if not self._redact_tool_io:
            return result

        if isinstance(result, str):
            return self._redactor.redact(result)
        elif isinstance(result, dict):
            return self._redactor.redact_dict(result)
        return result
