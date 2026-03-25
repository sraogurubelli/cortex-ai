"""
Intent detection interfaces and implementations.

Provides an abstract ``IntentDetector`` protocol and two concrete
implementations:

- ``KeywordIntentDetector`` — fast, rule-based matching via keyword lists
- ``LLMIntentDetector`` — accurate, uses an LLM call to classify intent
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """Result of intent detection.

    Attributes:
        module: Primary detected module/category (e.g. "ci", "billing").
        confidence: Confidence score between 0.0 and 1.0.
        all_modules: Ranked list of all detected modules with scores.
        usage: Token usage if an LLM call was made.
    """

    module: str
    confidence: float = 1.0
    all_modules: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


class IntentDetector(ABC):
    """Abstract interface for intent/module detection.

    Implement this protocol to classify user intent before agent execution.
    The detected intent drives:
      - Agent routing in a swarm
      - Module-specific skill loading
      - System prompt customization

    Subclass and implement ``detect`` for your domain.
    """

    @abstractmethod
    async def detect(
        self,
        message: str,
        conversation_history: list[dict] | None = None,
        context: dict | None = None,
    ) -> IntentResult:
        """Detect the user's intent/module from their message.

        Args:
            message: The latest user message.
            conversation_history: Optional prior conversation for context.
            context: Optional additional context (e.g. current page, module hint).

        Returns:
            IntentResult with the detected module and confidence.
        """
        ...


class KeywordIntentDetector(IntentDetector):
    """Fast keyword-based intent detector.

    Maps keywords to module names. The module with the most keyword
    matches wins. Falls back to ``default_module`` when no keywords match.

    Example::

        detector = KeywordIntentDetector(
            keyword_map={
                "ci": ["build", "pipeline", "compile", "test run"],
                "cd": ["deploy", "rollback", "release", "environment"],
                "ccm": ["cost", "cloud spend", "budget", "savings"],
            },
            default_module="general",
        )
    """

    def __init__(
        self,
        keyword_map: dict[str, list[str]],
        default_module: str = "general",
    ):
        self._keyword_map = {
            module: [kw.lower() for kw in keywords]
            for module, keywords in keyword_map.items()
        }
        self._default = default_module

    async def detect(
        self,
        message: str,
        conversation_history: list[dict] | None = None,
        context: dict | None = None,
    ) -> IntentResult:
        text = message.lower()
        scores: dict[str, int] = {}

        for module, keywords in self._keyword_map.items():
            count = sum(1 for kw in keywords if kw in text)
            if count > 0:
                scores[module] = count

        if not scores:
            return IntentResult(module=self._default, confidence=0.0)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_module, best_count = ranked[0]
        total = sum(s for _, s in ranked)

        return IntentResult(
            module=best_module,
            confidence=round(best_count / total, 2) if total > 0 else 1.0,
            all_modules=[
                {"module": m, "score": s} for m, s in ranked
            ],
        )


class LLMIntentDetector(IntentDetector):
    """LLM-based intent detector using a lightweight model call.

    Sends a classification prompt to the configured model and parses
    the module name from the response.

    Example::

        detector = LLMIntentDetector(
            modules=["ci", "cd", "ccm", "sto", "general"],
            model="gpt-4o-mini",
        )
    """

    def __init__(
        self,
        modules: list[str],
        model: str = "gpt-4o-mini",
        default_module: str = "general",
    ):
        self._modules = modules
        self._model = model
        self._default = default_module

    def _build_prompt(self, message: str, context: dict | None = None) -> str:
        module_list = ", ".join(self._modules)
        prompt = (
            f"Classify the following user message into exactly one of these modules: {module_list}.\n"
            f"Respond with ONLY the module name, nothing else.\n\n"
            f"User message: {message}"
        )
        if context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
            prompt += f"\nContext: {ctx_str}"
        return prompt

    async def detect(
        self,
        message: str,
        conversation_history: list[dict] | None = None,
        context: dict | None = None,
    ) -> IntentResult:
        try:
            from cortex.orchestration.llm import LLMClient
            from cortex.orchestration.config import ModelConfig

            client = LLMClient(ModelConfig(model=self._model, temperature=0.0))
            model = client.get_model()

            prompt = self._build_prompt(message, context)
            response = await model.ainvoke(prompt)

            detected = response.content.strip().lower() if hasattr(response, "content") else ""

            # Validate the detected module
            if detected not in self._modules:
                for mod in self._modules:
                    if mod in detected:
                        detected = mod
                        break
                else:
                    detected = self._default

            usage = {}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = {
                    "input_tokens": getattr(response.usage_metadata, "input_tokens", 0),
                    "output_tokens": getattr(response.usage_metadata, "output_tokens", 0),
                }

            return IntentResult(
                module=detected,
                confidence=0.9,
                usage=usage,
            )
        except Exception:
            logger.warning("LLM intent detection failed, using default", exc_info=True)
            return IntentResult(module=self._default, confidence=0.0)
