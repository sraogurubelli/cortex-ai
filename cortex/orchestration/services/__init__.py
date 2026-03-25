"""
Service Client Registry — pluggable external service integration.

Ported from ml-infra's ``capabilities/tools/grpc/`` pattern. Provides
a registry for external service clients (gRPC or HTTP) with automatic
context propagation via cortex's existing contextvars.

Usage::

    from cortex.orchestration.services import (
        ServiceClient,
        ServiceClientRegistry,
        service_registry,
    )

    # Register a client at startup
    class SchemaServiceClient(ServiceClient):
        async def initialize(self):
            self._channel = grpc.aio.insecure_channel(self.endpoint)
            self._stub = SchemaServiceStub(self._channel)

        async def health_check(self) -> bool:
            try:
                await self._stub.Ping(Empty())
                return True
            except Exception:
                return False

        async def close(self):
            await self._channel.close()

    service_registry.register("schema", SchemaServiceClient(
        endpoint="schema-service:50051",
    ))

    # Use in tools
    client = service_registry.get("schema")
"""

from cortex.orchestration.services.registry import (
    ServiceClient,
    ServiceClientRegistry,
    service_registry,
)

__all__ = [
    "ServiceClient",
    "ServiceClientRegistry",
    "service_registry",
]
