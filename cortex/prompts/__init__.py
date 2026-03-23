"""
Cortex Prompt Registry — central storage and rendering for prompt templates.

Provides auto-discovery of local ``*_prompts.py`` modules and Jinja2 template
rendering with ``{% include "key" %}`` support for template composition.

Usage::

    from cortex.prompts import get_prompt, register_prompt, list_prompts

    # Fetch and render a prompt (sync)
    prompt = get_prompt("chat.system", agent_name="assistant")

    # Register a prompt at runtime
    register_prompt("custom.greeting", "Hello, {{ name }}!")

    # List all registered keys
    keys = list_prompts()

Auto-discovery scans ``cortex/prompts/`` for modules named ``*_prompts.py``.
Each module should export a ``PROMPTS`` dict mapping dotted keys to Jinja2
template strings::

    # cortex/prompts/chat_prompts.py
    PROMPTS = {
        "system": "You are {{ agent_name }}, a helpful assistant.",
        "rag_context": "Use the following context:\\n{{ context }}",
    }

Keys are namespaced by the module prefix: ``chat_prompts.py`` → prefix
``chat``, so the full key for ``"system"`` becomes ``"chat.system"``.

Ported from the pattern in ml-infra capabilities/tools/prompts/registry.py
(Harness-specific remote ConfigService path removed).
"""

from cortex.prompts.registry import (
    PromptRegistry,
    get_prompt,
    get_prompt_async,
    list_prompts,
    register_prompt,
)

__all__ = [
    "PromptRegistry",
    "get_prompt",
    "get_prompt_async",
    "list_prompts",
    "register_prompt",
]
