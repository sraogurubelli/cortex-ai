"""
Prompt Registry — Jinja2-based prompt template management.

Auto-discovers ``*_prompts.py`` modules under ``cortex/prompts/``, registers
their ``PROMPTS`` dict entries with dotted keys, and renders templates using
Jinja2 (with support for ``{% include "key" %}`` cross-references).

Architecture
~~~~~~~~~~~~

    cortex/prompts/
    ├── __init__.py          # Public API
    ├── registry.py          # This file — core registry + Jinja2 rendering
    ├── chat_prompts.py      # → keys: chat.system, chat.rag_context, …
    └── research_prompts.py  # → keys: research.plan, research.synthesize, …

Template syntax
~~~~~~~~~~~~~~~

All templates use Jinja2:

- ``{{ variable }}`` for variable substitution.
- ``{% include "other.key" %}`` for composing templates from other registry
  entries.  Includes are resolved via a custom ``RegistryLoader``.

Ported from ml-infra capabilities/tools/prompts/registry.py
(Harness-specific remote ConfigService path removed).
"""

import importlib
import logging
import pkgutil
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateNotFound

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Jinja2 RegistryLoader — resolves {% include "key" %} from the registry
# ---------------------------------------------------------------------------


class _RegistryLoader(BaseLoader):
    """Jinja2 loader that resolves ``{% include "key" %}`` via the registry."""

    def __init__(self, registry: "PromptRegistry"):
        self._registry = registry

    def get_source(self, environment: Environment, template_name: str):
        source = self._registry._get_raw(template_name)
        if source is None:
            raise TemplateNotFound(template_name)
        return source, template_name, lambda: True


# ---------------------------------------------------------------------------
# PromptRegistry
# ---------------------------------------------------------------------------


class PromptRegistry:
    """Central, singleton registry for prompt templates.

    Resolution is purely local (no remote calls).  Templates are populated
    by :meth:`initialize` (auto-discovery) or :meth:`register` (runtime).

    Example::

        registry = PromptRegistry.instance()
        rendered = registry.get("chat.system", agent_name="assistant")
    """

    _singleton: "PromptRegistry | None" = None

    def __init__(self) -> None:
        self._prompts: dict[str, str] = {}
        self._initialized = False

    @classmethod
    def instance(cls) -> "PromptRegistry":
        """Get (or create) the singleton instance."""
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    # ------------------------------------------------------------------
    # Initialization (auto-discovery)
    # ------------------------------------------------------------------

    def initialize(self, package_name: str = "cortex.prompts") -> None:
        """Auto-discover and register prompts from ``*_prompts.py`` modules.

        Scans *package_name* for submodules whose name ends with
        ``_prompts``.  Each must export a ``PROMPTS`` dict mapping short
        keys to Jinja2 template strings.  The module prefix is used as
        namespace: ``chat_prompts.py`` with key ``"system"`` registers
        as ``"chat.system"``.
        """
        if self._initialized:
            return

        try:
            package = importlib.import_module(package_name)
        except ImportError:
            logger.warning("Prompt package %s not found", package_name)
            self._initialized = True
            return

        for _importer, module_name, _is_pkg in pkgutil.iter_modules(
            package.__path__
        ):
            if not module_name.endswith("_prompts"):
                continue
            prefix = module_name.removesuffix("_prompts")
            try:
                mod = importlib.import_module(f"{package_name}.{module_name}")
            except Exception:
                logger.warning(
                    "Failed to import prompt module %s.%s",
                    package_name,
                    module_name,
                    exc_info=True,
                )
                continue
            prompts_dict = getattr(mod, "PROMPTS", None)
            if not isinstance(prompts_dict, dict):
                continue
            for key, template in prompts_dict.items():
                full_key = f"{prefix}.{key}"
                self._prompts[full_key] = template

        self._initialized = True
        logger.info(
            "PromptRegistry initialized with %d prompts", len(self._prompts)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, **kwargs: Any) -> str:
        """Fetch and render a prompt by key.

        Args:
            key: Dotted prompt key (e.g. ``"chat.system"``).
            **kwargs: Jinja2 template variables.

        Returns:
            Fully rendered prompt string.

        Raises:
            KeyError: If the key is not registered.
        """
        self._ensure_initialized()
        raw = self._get_raw(key)
        if raw is None:
            available = ", ".join(sorted(self._prompts.keys()))
            raise KeyError(f"Prompt '{key}' not found. Available: {available}")
        return self._render(raw, kwargs)

    async def get_async(self, key: str, **kwargs: Any) -> str:
        """Async variant of :meth:`get`.

        Currently identical to ``get()`` (no remote fetching).  Provided
        for forward-compatibility so callers can switch to a remote-first
        strategy later without changing call sites.
        """
        return self.get(key, **kwargs)

    def register(self, key: str, template: str) -> None:
        """Register (or overwrite) a prompt template at runtime."""
        self._ensure_initialized()
        self._prompts[key] = template

    def list_keys(self) -> list[str]:
        """List all registered prompt keys (sorted)."""
        self._ensure_initialized()
        return sorted(self._prompts.keys())

    def has(self, key: str) -> bool:
        """Check if a prompt key is registered."""
        self._ensure_initialized()
        return key in self._prompts

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, template: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template, resolving includes via RegistryLoader."""
        env = Environment(loader=_RegistryLoader(self))
        try:
            jinja_template = env.from_string(template)
            return jinja_template.render(**variables)
        except Exception:
            logger.exception(
                "Jinja2 render failed (template preview: %.120s, vars: %s)",
                template,
                list(variables.keys()),
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_raw(self, key: str) -> str | None:
        """Return the raw (un-rendered) template for *key*, or ``None``."""
        self._ensure_initialized()
        return self._prompts.get(key)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    # ------------------------------------------------------------------
    # Testing / reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all prompts and mark as uninitialized. For testing only."""
        self._prompts.clear()
        self._initialized = False

    def get_status(self) -> dict[str, Any]:
        """Diagnostic info."""
        return {
            "initialized": self._initialized,
            "prompt_count": len(self._prompts),
        }


# ---------------------------------------------------------------------------
# Module-level singleton + convenience functions
# ---------------------------------------------------------------------------

_registry = PromptRegistry.instance()


def get_prompt(key: str, **kwargs: Any) -> str:
    """Fetch and render a prompt by key (sync)."""
    return _registry.get(key, **kwargs)


async def get_prompt_async(key: str, **kwargs: Any) -> str:
    """Fetch and render a prompt by key (async)."""
    return await _registry.get_async(key, **kwargs)


def register_prompt(key: str, template: str) -> None:
    """Register a prompt template at runtime."""
    _registry.register(key, template)


def list_prompts() -> list[str]:
    """List all registered prompt keys."""
    return _registry.list_keys()
