"""
MCP Server Registry — named configuration store for MCP servers.

Provides a singleton registry so agents can reference MCP servers by name
rather than raw URLs.  Servers are registered from environment variables,
config files, or programmatically.

Usage::

    from cortex.orchestration.mcp.registry import mcp_server_registry

    # Register a server
    from cortex.orchestration.mcp import HTTPMCPConfig, MCPAuth

    mcp_server_registry.register(HTTPMCPConfig(
        name="code_interpreter",
        url="http://localhost:8080/mcp",
        auth_type=MCPAuth.BEARER_TOKEN,
        token="my-token",
    ))

    # Use from Agent
    agent = Agent(
        name="coder",
        use_mcp=True,
        mcp_config="code_interpreter",
    )

    # Or create a loader directly
    loader = mcp_server_registry.create_loader(
        "code_interpreter",
        headers={"X-Custom": "value"},
    )
    async with loader:
        tools = await loader.load_tools()

Environment-driven auto-registration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On first access the registry reads ``CORTEX_MCP_SERVERS`` (JSON array)
from the environment.  Each entry is an object with at least ``name``,
``transport`` (``http``, ``sse``, or ``stdio``), and the transport-specific
fields (``url`` for HTTP/SSE, ``command`` for stdio).

Example ``CORTEX_MCP_SERVERS`` value::

    [
      {"name": "tools", "transport": "http", "url": "http://mcp-tools:8080"},
      {"name": "local", "transport": "stdio", "command": "./mcp-server", "args": ["stdio"]}
    ]

Ported from the pattern in ml-infra orchestration_sdk/registries/mcp_servers.py
(Harness-specific server definitions removed).
"""

import json
import logging
import os
from typing import Any

from cortex.orchestration.mcp.config import (
    HTTPMCPConfig,
    MCPAuth,
    MCPConfig,
    SSEMCPConfig,
    STDIOMCPConfig,
)
from cortex.orchestration.mcp.loader import MCPLoader, ProgressNotificationCallback

logger = logging.getLogger(__name__)

_ENV_VAR = "CORTEX_MCP_SERVERS"


class MCPServerRegistry:
    """Singleton registry of named MCP server configurations.

    Starts empty and is populated from environment (``CORTEX_MCP_SERVERS``)
    or programmatically via :meth:`register`.
    """

    _instance: "MCPServerRegistry | None" = None

    def __init__(self) -> None:
        self._configs: dict[str, MCPConfig] = {}

    @classmethod
    def instance(cls) -> "MCPServerRegistry":
        """Get (or create) the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_from_env()
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, config: MCPConfig) -> "MCPServerRegistry":
        """Register an MCP server configuration.

        Args:
            config: An ``MCPConfig`` subclass instance.

        Returns:
            Self for chaining.
        """
        config.validate()
        self._configs[config.name] = config
        logger.info("Registered MCP server: %s", config.name)
        return self

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def list_servers(self) -> list[str]:
        """List registered server names."""
        return list(self._configs.keys())

    def get_config(self, name: str) -> MCPConfig:
        """Get config by server name.

        Raises:
            KeyError: If the server is not registered.
        """
        if name not in self._configs:
            raise KeyError(
                f"MCP server '{name}' not found. "
                f"Available: {self.list_servers()}"
            )
        return self._configs[name]

    def create_loader(
        self,
        name: str,
        headers: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
        progress_callback: ProgressNotificationCallback | None = None,
    ) -> MCPLoader:
        """Create a loader for a registered server.

        Runtime *headers* and *env* are merged with the stored config,
        allowing per-session auth overlay (e.g. bearer tokens).

        Args:
            name: Registered server name.
            headers: Extra headers (HTTP/SSE only).
            env: Extra env vars (stdio only).
            progress_callback: Optional progress notification handler.

        Returns:
            Configured ``MCPLoader``.
        """
        config = self.get_config(name)
        return MCPLoader.from_config(
            config,
            progress_callback=progress_callback,
            headers=headers,
            env=env,
        )

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def remove(self, name: str) -> bool:
        """Remove a server by name. Returns True if removed."""
        if name in self._configs:
            del self._configs[name]
            logger.info("Removed MCP server: %s", name)
            return True
        return False

    def clear(self) -> None:
        """Remove all registered servers."""
        self._configs.clear()

    # ------------------------------------------------------------------
    # Environment loading
    # ------------------------------------------------------------------

    def _load_from_env(self) -> None:
        """Load server configs from the ``CORTEX_MCP_SERVERS`` env var."""
        raw = os.environ.get(_ENV_VAR)
        if not raw:
            return

        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "%s is not valid JSON — skipping auto-registration", _ENV_VAR
            )
            return

        if not isinstance(entries, list):
            logger.warning("%s must be a JSON array", _ENV_VAR)
            return

        for entry in entries:
            try:
                config = self._parse_entry(entry)
                self.register(config)
            except Exception:
                logger.warning(
                    "Skipping invalid MCP server entry: %s",
                    entry.get("name", "<unnamed>"),
                    exc_info=True,
                )

    @staticmethod
    def _parse_entry(entry: dict[str, Any]) -> MCPConfig:
        """Parse a single JSON entry into an MCPConfig."""
        name = entry["name"]
        transport = entry.get("transport", "http")
        description = entry.get("description", "")

        auth_type = MCPAuth.NONE
        token = entry.get("token")
        api_key = entry.get("api_key")
        if token:
            auth_type = MCPAuth.BEARER_TOKEN
        elif api_key:
            auth_type = MCPAuth.API_KEY

        common = dict(
            name=name,
            description=description,
            auth_type=auth_type,
            token=token,
            api_key=api_key,
            headers=entry.get("headers"),
            enabled_tools=entry.get("enabled_tools"),
            disabled_tools=entry.get("disabled_tools"),
            timeout=entry.get("timeout", 30.0),
        )

        if transport == "stdio":
            return STDIOMCPConfig(
                command=entry["command"],
                args=entry.get("args", []),
                env=entry.get("env", {}),
                **common,
            )
        elif transport == "sse":
            return SSEMCPConfig(url=entry["url"], **common)
        else:
            return HTTPMCPConfig(url=entry["url"], **common)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._configs)

    def __contains__(self, name: str) -> bool:
        return name in self._configs


# Module-level singleton
mcp_server_registry = MCPServerRegistry.instance()
