"""
Service client registry for external service integrations.

Provides a pluggable framework for registering and managing external
service clients (gRPC, HTTP, etc.) with lifecycle management and
health checking. Uses cortex's existing contextvars for automatic
tenant/request context propagation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ServiceClient(ABC):
    """Abstract base class for external service clients.

    Subclass this to integrate with gRPC services, HTTP APIs,
    or any other external service your tools need to call.

    Context propagation is automatic: use ``cortex.orchestration.context``
    to read tenant_id, project_id, etc. in your client methods.
    """

    def __init__(self, endpoint: str = "", metadata: dict | None = None):
        self.endpoint = endpoint
        self.metadata = metadata or {}

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the client (create channels, stubs, etc.).

        Called once during application startup.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the service is reachable and healthy."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (close channels, connections, etc.).

        Called during application shutdown.
        """
        ...

    def get_context_headers(self) -> dict[str, str]:
        """Build context headers from current request context.

        Subclasses can override this to add service-specific headers.
        """
        from cortex.orchestration.context import (
            get_conversation_id,
            get_principal_id,
            get_request_id,
            get_tenant_id,
        )

        headers: dict[str, str] = {}
        tenant = get_tenant_id()
        if tenant:
            headers["x-tenant-id"] = tenant
        principal = get_principal_id()
        if principal:
            headers["x-principal-id"] = principal
        request_id = get_request_id()
        if request_id:
            headers["x-request-id"] = request_id
        conv_id = get_conversation_id()
        if conv_id:
            headers["x-conversation-id"] = conv_id
        return headers


class ServiceClientRegistry:
    """Registry for external service clients with lifecycle management.

    Manages initialization, health checking, and shutdown of all
    registered service clients.

    Example::

        registry = ServiceClientRegistry()
        registry.register("schema", SchemaServiceClient(endpoint="host:50051"))
        await registry.initialize_all()

        client = registry.get("schema")
        # use client...

        await registry.close_all()
    """

    def __init__(self) -> None:
        self._clients: dict[str, ServiceClient] = {}
        self._initialized = False

    def register(self, name: str, client: ServiceClient) -> "ServiceClientRegistry":
        """Register a service client.

        Args:
            name: Unique name for the service.
            client: ServiceClient instance.

        Returns:
            Self for chaining.
        """
        self._clients[name] = client
        logger.info("Registered service client: %s (endpoint=%s)", name, client.endpoint)
        return self

    def get(self, name: str) -> ServiceClient:
        """Get a registered service client.

        Raises:
            KeyError: If the service is not registered.
        """
        if name not in self._clients:
            raise KeyError(
                f"Service '{name}' not registered. "
                f"Available: {list(self._clients.keys())}"
            )
        return self._clients[name]

    def get_optional(self, name: str) -> Optional[ServiceClient]:
        """Get a registered service client, or None if not found."""
        return self._clients.get(name)

    def list_services(self) -> list[str]:
        """List all registered service names."""
        return list(self._clients.keys())

    async def initialize_all(self) -> dict[str, bool]:
        """Initialize all registered clients.

        Returns:
            Dict mapping service name to initialization success.
        """
        results: dict[str, bool] = {}
        for name, client in self._clients.items():
            try:
                await client.initialize()
                results[name] = True
                logger.info("Initialized service client: %s", name)
            except Exception:
                results[name] = False
                logger.exception("Failed to initialize service client: %s", name)
        self._initialized = True
        return results

    async def health_check_all(self) -> dict[str, bool]:
        """Health check all registered clients."""
        results: dict[str, bool] = {}
        for name, client in self._clients.items():
            try:
                results[name] = await client.health_check()
            except Exception:
                results[name] = False
        return results

    async def close_all(self) -> None:
        """Close all registered clients."""
        for name, client in self._clients.items():
            try:
                await client.close()
                logger.info("Closed service client: %s", name)
            except Exception:
                logger.exception("Failed to close service client: %s", name)

    def __contains__(self, name: str) -> bool:
        return name in self._clients

    def __len__(self) -> int:
        return len(self._clients)


# Singleton instance
service_registry = ServiceClientRegistry()
