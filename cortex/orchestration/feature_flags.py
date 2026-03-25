"""
Runtime Feature Flag Evaluator.

Ported from ml-infra's Harness Feature Flags pattern. Provides a
pluggable interface for per-account feature gating that can be used
in the session orchestrator and middleware to progressively roll out
features.

Supports multiple backends:
  - In-memory (for development/testing)
  - Database-backed (via cortex platform DB)
  - External providers (Harness FF, LaunchDarkly, etc.)

Usage::

    from cortex.orchestration.feature_flags import (
        FeatureFlagEvaluator,
        InMemoryFeatureFlags,
        feature_flags,
    )

    # Global evaluator (singleton)
    feature_flags.register("semantic_memory", default=False)
    feature_flags.set_override("semantic_memory", True, account_id="acc_123")

    # In session orchestrator or middleware
    if await feature_flags.is_enabled("semantic_memory", account_id=config.tenant_id):
        # Enable semantic memory for this account
        ...

    # Bulk evaluation
    flags = await feature_flags.evaluate_all(account_id="acc_123")
    # {"semantic_memory": True, "new_model": False, ...}
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class FeatureFlagEvaluator(ABC):
    """Abstract interface for runtime feature flag evaluation.

    Implement this to integrate with your feature flag provider.
    """

    @abstractmethod
    async def is_enabled(
        self,
        flag_name: str,
        account_id: str = "",
        default: bool = False,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Evaluate whether a feature flag is enabled.

        Args:
            flag_name: Name of the feature flag.
            account_id: Account/tenant to evaluate for.
            default: Default value if the flag is not found.
            context: Additional evaluation context (user, project, etc.).

        Returns:
            True if the flag is enabled, False otherwise.
        """
        ...

    @abstractmethod
    async def evaluate_all(
        self,
        account_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        """Evaluate all registered flags for an account.

        Returns:
            Dict mapping flag name to enabled status.
        """
        ...


class InMemoryFeatureFlags(FeatureFlagEvaluator):
    """In-memory feature flag evaluator for development and testing.

    Supports per-account overrides on top of global defaults.
    """

    def __init__(self) -> None:
        self._defaults: dict[str, bool] = {}
        self._overrides: dict[str, dict[str, bool]] = {}

    def register(self, flag_name: str, default: bool = False) -> "InMemoryFeatureFlags":
        """Register a feature flag with a default value."""
        self._defaults[flag_name] = default
        return self

    def set_override(
        self,
        flag_name: str,
        enabled: bool,
        account_id: str = "",
    ) -> "InMemoryFeatureFlags":
        """Set a per-account override for a flag."""
        if flag_name not in self._overrides:
            self._overrides[flag_name] = {}
        self._overrides[flag_name][account_id] = enabled
        return self

    def clear_override(self, flag_name: str, account_id: str = "") -> None:
        """Remove a per-account override."""
        if flag_name in self._overrides:
            self._overrides[flag_name].pop(account_id, None)

    async def is_enabled(
        self,
        flag_name: str,
        account_id: str = "",
        default: bool = False,
        context: dict[str, Any] | None = None,
    ) -> bool:
        # Check per-account override first
        account_overrides = self._overrides.get(flag_name, {})
        if account_id and account_id in account_overrides:
            return account_overrides[account_id]

        # Fall back to global default
        return self._defaults.get(flag_name, default)

    async def evaluate_all(
        self,
        account_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for flag_name, default_val in self._defaults.items():
            account_overrides = self._overrides.get(flag_name, {})
            if account_id and account_id in account_overrides:
                result[flag_name] = account_overrides[account_id]
            else:
                result[flag_name] = default_val
        return result

    def list_flags(self) -> list[str]:
        """List all registered flag names."""
        return list(self._defaults.keys())


class DatabaseFeatureFlags(FeatureFlagEvaluator):
    """Feature flag evaluator backed by the cortex platform database.

    Delegates to the platform's feature_flags API route for evaluation.
    Falls back to in-memory defaults when the database is unavailable.
    """

    def __init__(self, fallback: InMemoryFeatureFlags | None = None) -> None:
        self._fallback = fallback or InMemoryFeatureFlags()
        self._cache: dict[str, dict[str, bool]] = {}

    async def is_enabled(
        self,
        flag_name: str,
        account_id: str = "",
        default: bool = False,
        context: dict[str, Any] | None = None,
    ) -> bool:
        cache_key = f"{account_id}:{flag_name}"
        cached = self._cache.get(account_id, {}).get(flag_name)
        if cached is not None:
            return cached

        try:
            from cortex.platform.database.repositories.feature_flag import (
                feature_flag_repository,
            )

            flag = await feature_flag_repository.get_by_name(flag_name)
            if flag is None:
                return await self._fallback.is_enabled(
                    flag_name, account_id, default, context
                )
            return flag.enabled
        except Exception:
            logger.debug("Database FF lookup failed for %s, using fallback", flag_name)
            return await self._fallback.is_enabled(
                flag_name, account_id, default, context
            )

    async def evaluate_all(
        self,
        account_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        return await self._fallback.evaluate_all(account_id, context)


# Singleton instance — default to in-memory for development
feature_flags: FeatureFlagEvaluator = InMemoryFeatureFlags()


def set_feature_flag_evaluator(evaluator: FeatureFlagEvaluator) -> None:
    """Replace the global feature flag evaluator.

    Call this at application startup to switch to a database-backed
    or external provider-backed evaluator.
    """
    global feature_flags
    feature_flags = evaluator
    logger.info("Feature flag evaluator set to %s", type(evaluator).__name__)
