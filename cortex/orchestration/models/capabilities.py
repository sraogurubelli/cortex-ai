"""
Model capability detection.

Provides a dataclass describing what a given model supports and a function
to infer capabilities from model names / known provider catalogs.
"""

from dataclasses import dataclass, field


@dataclass
class ModelCapabilities:
    """Describes what a model supports."""

    supports_tools: bool = False
    supports_vision: bool = False
    supports_streaming: bool = True
    supports_json_mode: bool = False
    supports_reasoning: bool = False
    context_window: int = 4096
    max_output_tokens: int = 4096
    provider: str = "unknown"
    model_name: str = ""
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    tags: list[str] = field(default_factory=list)


_KNOWN_MODELS: dict[str, ModelCapabilities] = {
    "gpt-4o": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        supports_json_mode=True, context_window=128_000, max_output_tokens=16_384,
        provider="openai", model_name="gpt-4o",
        cost_per_1k_input=0.0025, cost_per_1k_output=0.01,
        tags=["flagship"],
    ),
    "gpt-4o-mini": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        supports_json_mode=True, context_window=128_000, max_output_tokens=16_384,
        provider="openai", model_name="gpt-4o-mini",
        cost_per_1k_input=0.00015, cost_per_1k_output=0.0006,
        tags=["fast", "cheap"],
    ),
    "gpt-4-turbo": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        supports_json_mode=True, context_window=128_000, max_output_tokens=4096,
        provider="openai", model_name="gpt-4-turbo",
        cost_per_1k_input=0.01, cost_per_1k_output=0.03,
    ),
    "claude-sonnet-4-20250514": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        supports_json_mode=True, supports_reasoning=True,
        context_window=200_000, max_output_tokens=64_000,
        provider="anthropic", model_name="claude-sonnet-4-20250514",
        cost_per_1k_input=0.003, cost_per_1k_output=0.015,
        tags=["flagship", "reasoning"],
    ),
    "claude-3-5-sonnet-20241022": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        supports_json_mode=True, context_window=200_000, max_output_tokens=8192,
        provider="anthropic", model_name="claude-3-5-sonnet-20241022",
        cost_per_1k_input=0.003, cost_per_1k_output=0.015,
        tags=["flagship"],
    ),
    "claude-3-haiku-20240307": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        context_window=200_000, max_output_tokens=4096,
        provider="anthropic", model_name="claude-3-haiku-20240307",
        cost_per_1k_input=0.00025, cost_per_1k_output=0.00125,
        tags=["fast", "cheap"],
    ),
    "gemini-2.0-flash": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        supports_json_mode=True, context_window=1_000_000, max_output_tokens=8192,
        provider="google", model_name="gemini-2.0-flash",
        cost_per_1k_input=0.0001, cost_per_1k_output=0.0004,
        tags=["fast", "cheap"],
    ),
    "gemini-2.5-pro": ModelCapabilities(
        supports_tools=True, supports_vision=True, supports_streaming=True,
        supports_json_mode=True, supports_reasoning=True,
        context_window=1_000_000, max_output_tokens=65_536,
        provider="google", model_name="gemini-2.5-pro",
        cost_per_1k_input=0.00125, cost_per_1k_output=0.01,
        tags=["flagship", "reasoning"],
    ),
}


def detect_capabilities(model_name: str) -> ModelCapabilities:
    """Detect capabilities for a model name.

    Checks the known catalog first, then falls back to heuristics
    based on provider prefix patterns.
    """
    if model_name in _KNOWN_MODELS:
        return _KNOWN_MODELS[model_name]

    lower = model_name.lower()

    if "gpt" in lower or "o1" in lower or "o3" in lower:
        return ModelCapabilities(
            supports_tools=True, supports_vision="vision" in lower or "gpt-4" in lower,
            supports_streaming=True, context_window=128_000,
            provider="openai", model_name=model_name,
        )
    if "claude" in lower:
        return ModelCapabilities(
            supports_tools=True, supports_vision=True,
            supports_streaming=True, context_window=200_000,
            provider="anthropic", model_name=model_name,
        )
    if "gemini" in lower:
        return ModelCapabilities(
            supports_tools=True, supports_vision=True,
            supports_streaming=True, context_window=1_000_000,
            provider="google", model_name=model_name,
        )

    return ModelCapabilities(
        supports_tools=True, supports_streaming=True,
        provider="custom", model_name=model_name,
    )


def list_known_models() -> list[ModelCapabilities]:
    """Return all known model capability entries."""
    return list(_KNOWN_MODELS.values())
