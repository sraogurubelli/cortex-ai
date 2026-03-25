"""
Safety and Guardrails for Cortex Orchestration.

Provides production-grade safety features:
  - PII redaction (input/output/tool I/O)
  - Trace sanitization (Langfuse, OpenTelemetry)
  - Input guardrails (prompt injection, content safety)
  - Output guardrails (prompt leak, code injection)
  - Token budget enforcement
  - Feedback collection
  - Conversation history dump (debug)

Usage::

    from cortex.orchestration.safety import (
        PIIRedactionMiddleware,
        InputGuardrailsMiddleware,
        OutputGuardrailsMiddleware,
        TokenBudgetMiddleware,
        FeedbackCollectionHook,
        HistoryDumpHook,
        install_langfuse_sanitizer,
    )

    # Build a safety-hardened middleware stack
    middleware = [
        InputGuardrailsMiddleware(),
        PIIRedactionMiddleware(),
        OutputGuardrailsMiddleware(),
        TokenBudgetMiddleware(max_total_tokens=100_000),
    ]
"""

from cortex.orchestration.safety.feedback import (
    DEFAULT_FEEDBACK_REASONS,
    FeedbackCollectionHook,
)
from cortex.orchestration.safety.history_dump import HistoryDumpHook
from cortex.orchestration.safety.input_guardrails import (
    GuardrailViolation,
    InputGuardrailsMiddleware,
)
from cortex.orchestration.safety.output_guardrails import (
    OutputGuardrailsMiddleware,
    OutputViolation,
)
from cortex.orchestration.safety.pii_redaction import (
    PIIRedactionMiddleware,
    PIIRedactor,
)
from cortex.orchestration.safety.token_budget import (
    TokenBudgetExceeded,
    TokenBudgetMiddleware,
)
from cortex.orchestration.safety.trace_sanitizer import (
    install_langfuse_sanitizer,
    sanitize_headers,
    sanitize_trace_data,
)

__all__ = [
    # PII Redaction
    "PIIRedactionMiddleware",
    "PIIRedactor",
    # Trace Sanitization
    "sanitize_trace_data",
    "sanitize_headers",
    "install_langfuse_sanitizer",
    # Input Guardrails
    "InputGuardrailsMiddleware",
    "GuardrailViolation",
    # Output Guardrails
    "OutputGuardrailsMiddleware",
    "OutputViolation",
    # Token Budget
    "TokenBudgetMiddleware",
    "TokenBudgetExceeded",
    # Feedback
    "FeedbackCollectionHook",
    "DEFAULT_FEEDBACK_REASONS",
    # History Dump
    "HistoryDumpHook",
]
