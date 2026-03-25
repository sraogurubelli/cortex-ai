"""
Audit Logging Middleware

Automatically records mutation operations (POST, PUT, PATCH, DELETE) to
the audit_logs table with actor, action, resource, and request context.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestCallbackType

logger = logging.getLogger(__name__)

_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SKIP_PATHS = {"/health", "/ready", "/", "/api/docs", "/api/redoc", "/metrics"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Records audit log entries for mutation endpoints."""

    async def dispatch(
        self, request: Request, call_next: RequestCallbackType
    ) -> Response:
        if request.method not in _MUTATION_METHODS:
            return await call_next(request)

        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        response = await call_next(request)

        if response.status_code < 400:
            try:
                await self._record(request, response)
            except Exception:
                logger.debug("Audit log write failed", exc_info=True)

        return response

    @staticmethod
    async def _record(request: Request, response: Response) -> None:
        from cortex.platform.database.session import get_db_manager
        from cortex.platform.database.models import AuditLog

        principal = getattr(request.state, "principal", None)
        request_id = getattr(request.state, "request_id", None)

        action = _derive_action(request.method, request.url.path)
        resource_type, resource_id = _parse_resource(request.url.path)

        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not ip and request.client:
            ip = request.client.host

        entry = AuditLog(
            uid=f"audit_{uuid.uuid4().hex[:12]}",
            actor_id=principal.id if principal else None,
            actor_uid=principal.uid if principal else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip or None,
            request_id=request_id,
        )

        async with get_db_manager().session() as session:
            session.add(entry)


def _derive_action(method: str, path: str) -> str:
    """Map HTTP method + path to a human-readable action."""
    if method == "DELETE":
        return "delete"
    if method == "POST":
        if "login" in path or "signup" in path:
            return "auth"
        if "generate-title" in path:
            return "generate_title"
        if "regenerate" in path:
            return "regenerate"
        if "stop" in path:
            return "stop_generation"
        if "rate" in path:
            return "rate"
        if "system-event" in path:
            return "system_event"
        if "chat" in path:
            return "chat"
        return "create"
    if method in ("PUT", "PATCH"):
        return "update"
    return method.lower()


def _parse_resource(path: str) -> tuple[str, str | None]:
    """Extract resource type and ID from URL path."""
    parts = [p for p in path.split("/") if p and p != "api" and p != "v1"]

    resource_type = "unknown"
    resource_id = None

    resource_keywords = [
        "conversations", "messages", "projects", "organizations",
        "accounts", "agents", "skills", "documents", "prompts",
        "models", "traces", "auth",
    ]

    for i, part in enumerate(parts):
        if part in resource_keywords:
            resource_type = part.rstrip("s")
            if i + 1 < len(parts) and not parts[i + 1] in resource_keywords:
                resource_id = parts[i + 1]
            break

    return resource_type, resource_id
