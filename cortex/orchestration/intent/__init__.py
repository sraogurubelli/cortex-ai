"""
Intent Detection — classify user intent before agent execution.

Ported from ml-infra's ``module_detection`` pattern. Enables:
  - Routing to specialized agents in a swarm
  - Loading module-specific skills
  - Customizing system prompts per intent

Usage::

    from cortex.orchestration.intent import (
        IntentDetector,
        IntentResult,
        KeywordIntentDetector,
        LLMIntentDetector,
    )

    # Keyword-based (fast, no LLM call)
    detector = KeywordIntentDetector({
        "billing": ["invoice", "cost", "pricing", "payment"],
        "technical": ["error", "bug", "deploy", "pipeline"],
    })
    result = await detector.detect("How do I fix this deployment error?")
    # result.module == "technical"

    # LLM-based (more accurate, uses a model call)
    detector = LLMIntentDetector(
        modules=["ci", "cd", "ccm", "sto", "general"],
        model="gpt-4o-mini",
    )
    result = await detector.detect("Show me my cloud cost trends")
    # result.module == "ccm"
"""

from cortex.orchestration.intent.detector import (
    IntentDetector,
    IntentResult,
    KeywordIntentDetector,
    LLMIntentDetector,
)

__all__ = [
    "IntentDetector",
    "IntentResult",
    "KeywordIntentDetector",
    "LLMIntentDetector",
]
