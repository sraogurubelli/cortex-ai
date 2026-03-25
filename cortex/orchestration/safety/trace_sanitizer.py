"""
Trace Sanitizer — mask sensitive data before it reaches observability backends.

Strips API keys, Bearer tokens, JWTs, passwords, and other secrets from data
structures before they are sent to Langfuse, OpenTelemetry, or any logging sink.

Ported from ml-infra langfuse_tracing.py ``_mask_sensitive_data``.

Usage::

    from cortex.orchestration.safety.trace_sanitizer import sanitize_trace_data

    # Single value
    clean = sanitize_trace_data({"api_key": "sk-abc123", "query": "hello"})
    # → {"api_key": "[REDACTED]", "query": "hello"}

    # Install as Langfuse callback
    from cortex.orchestration.safety.trace_sanitizer import install_langfuse_sanitizer
    install_langfuse_sanitizer()

Environment Variables:
    CORTEX_TRACE_SANITIZER_ENABLED: Enable trace sanitization (default: true)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# Sensitive key names (case-insensitive match)
# ============================================================================

_SENSITIVE_KEYS = frozenset({
    "token",
    "api_key",
    "apikey",
    "api-key",
    "password",
    "passwd",
    "secret",
    "credential",
    "credentials",
    "auth",
    "bearer",
    "authorization",
    "private_key",
    "private-key",
    "access_token",
    "access-token",
    "refresh_token",
    "refresh-token",
    "client_secret",
    "client-secret",
    "connection_string",
    "database_url",
})

# ============================================================================
# Regex patterns for inline secrets in string values
# ============================================================================

_TOKEN_PATTERNS = [
    (re.compile(r"\bBearer\s+[\w\-\.]+", re.IGNORECASE), "[REDACTED_TOKEN]"),
    (re.compile(r"\bsk-[\w\-]+", re.IGNORECASE), "[REDACTED_KEY]"),
    (re.compile(r"\bpk-[\w\-]+", re.IGNORECASE), "[REDACTED_KEY]"),
    (re.compile(r"\bghp_[\w]+"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bglpat-[\w\-]+"), "[REDACTED_GITLAB_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[=:]\s*\S+"), "[REDACTED_PASSWORD]"),
]

# Header keys to redact (case-insensitive)
_SENSITIVE_HEADER_KEYS = frozenset({
    "authorization",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "cookie",
    "set-cookie",
    "proxy-authorization",
})


# ============================================================================
# Core sanitizer
# ============================================================================


def sanitize_trace_data(data: Any) -> Any:
    """Recursively sanitize sensitive data from a structure.

    Works on dicts, lists, and strings. Returns a new structure with
    sensitive values replaced — the original is not modified.

    Args:
        data: Any data structure (dict, list, str, or primitive).

    Returns:
        Sanitized copy of the data.
    """
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = key.lower().replace("-", "_")
            if key_lower in _SENSITIVE_KEYS or "secret" in key_lower or "token" in key_lower:
                sanitized[key] = _redact_value(value)
            elif key_lower in _SENSITIVE_HEADER_KEYS:
                sanitized[key] = _redact_value(value)
            else:
                sanitized[key] = sanitize_trace_data(value)
        return sanitized

    elif isinstance(data, list):
        return [sanitize_trace_data(item) for item in data]

    elif isinstance(data, str):
        return _sanitize_string(data)

    return data


def _redact_value(value: Any) -> str:
    """Redact a value, showing a preview for strings."""
    if isinstance(value, str) and len(value) > 10:
        return f"{value[:4]}...[REDACTED]"
    return "[REDACTED]"


def _sanitize_string(text: str) -> str:
    """Apply regex patterns to mask inline secrets in a string."""
    for pattern, replacement in _TOKEN_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Sanitize HTTP headers for safe logging.

    Args:
        headers: HTTP headers dict.

    Returns:
        New dict with sensitive headers redacted.
    """
    result: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADER_KEYS or "secret" in key.lower():
            result[key] = _redact_value(value)
        else:
            result[key] = value
    return result


# ============================================================================
# Langfuse integration
# ============================================================================


def install_langfuse_sanitizer() -> bool:
    """Install the sanitizer as a Langfuse input/output transformer.

    Call this once at application startup (after Langfuse is initialized).

    Returns:
        True if successfully installed, False if Langfuse is not available.
    """
    try:
        from langfuse import get_client

        client = get_client()
        if client is None:
            logger.debug("Langfuse client not available — skipping sanitizer")
            return False

        if hasattr(client, "on"):
            client.on("before-trace-create", _langfuse_before_trace)
            logger.info("Langfuse trace sanitizer installed")
            return True
        else:
            logger.debug("Langfuse client does not support event hooks")
            return False

    except ImportError:
        logger.debug("Langfuse not installed — skipping sanitizer")
        return False
    except Exception:
        logger.debug("Failed to install Langfuse sanitizer", exc_info=True)
        return False


def _langfuse_before_trace(body: dict) -> dict:
    """Langfuse event hook that sanitizes trace data before submission."""
    if "input" in body:
        body["input"] = sanitize_trace_data(body["input"])
    if "output" in body:
        body["output"] = sanitize_trace_data(body["output"])
    if "metadata" in body:
        body["metadata"] = sanitize_trace_data(body["metadata"])
    return body
