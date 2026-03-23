"""
Provider Registry — singleton store for LLM provider configurations.

Manages provider API keys, base URLs, priorities, and models.
Auto-loads from environment variables on first access.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_ENV_VAR = "CORTEX_LLM_PROVIDERS"


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""

    name: str
    provider_type: str  # openai, anthropic, google, azure, custom
    api_key: str = ""
    base_url: str = ""
    gateway_url: str = ""  # If set, route through this gateway instead of direct API
    models: list[str] = field(default_factory=list)
    priority: int = 0  # lower = preferred
    enabled: bool = True
    max_retries: int = 3
    rate_limit_rpm: int = 0  # 0 = unlimited
    metadata: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.name


class ProviderRegistry:
    """Singleton registry of LLM provider configurations."""

    _instance: Optional["ProviderRegistry"] = None

    def __init__(self) -> None:
        self._providers: dict[str, ProviderConfig] = {}

    @classmethod
    def instance(cls) -> "ProviderRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_from_env()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (useful for tests)."""
        cls._instance = None

    def register(self, config: ProviderConfig) -> "ProviderRegistry":
        self._providers[config.name] = config
        logger.info("Registered provider: %s (%s)", config.name, config.provider_type)
        return self

    def get(self, name: str) -> ProviderConfig:
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not found. Available: {self.list_names()}")
        return self._providers[name]

    def list_names(self) -> list[str]:
        return list(self._providers.keys())

    def list_providers(self) -> list[ProviderConfig]:
        return list(self._providers.values())

    def list_enabled(self) -> list[ProviderConfig]:
        return sorted(
            [p for p in self._providers.values() if p.enabled],
            key=lambda p: p.priority,
        )

    def remove(self, name: str) -> bool:
        if name in self._providers:
            del self._providers[name]
            return True
        return False

    def find_provider_for_model(self, model: str) -> Optional[ProviderConfig]:
        """Find the highest-priority enabled provider that lists a given model."""
        for p in self.list_enabled():
            if model in p.models or not p.models:
                return p
        return None

    def _load_from_env(self) -> None:
        raw = os.environ.get(_ENV_VAR)
        if not raw:
            self._auto_detect()
            return
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("%s is not valid JSON", _ENV_VAR)
            return
        if not isinstance(entries, list):
            return
        for entry in entries:
            try:
                self.register(ProviderConfig(**entry))
            except Exception:
                logger.warning("Skipping invalid provider entry: %s", entry.get("name", "?"), exc_info=True)

    def _auto_detect(self) -> None:
        """Auto-detect providers from well-known env vars."""
        if os.environ.get("OPENAI_API_KEY"):
            self.register(ProviderConfig(
                name="openai", provider_type="openai",
                api_key=os.environ["OPENAI_API_KEY"],
                priority=1,
            ))
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.register(ProviderConfig(
                name="anthropic", provider_type="anthropic",
                api_key=os.environ["ANTHROPIC_API_KEY"],
                priority=0,
            ))
        if os.environ.get("GOOGLE_API_KEY"):
            self.register(ProviderConfig(
                name="google", provider_type="google",
                api_key=os.environ["GOOGLE_API_KEY"],
                priority=2,
            ))

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, name: str) -> bool:
        return name in self._providers


provider_registry = ProviderRegistry.instance()
