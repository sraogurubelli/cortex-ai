"""
FastAPI Dependencies for RBAC

Provides easy-to-use permission checking for API endpoints.
"""

import logging
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.auth.permissions import Permission
from cortex.platform.auth.rbac import PermissionChecker
from cortex.platform.database import Principal, get_db

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None
_redis_unavailable = False


async def get_redis() -> Redis | None:
    """
    Get a shared Redis client for permission caching.

    Lazily creates a connection from settings on first call.
    If Redis is unreachable, marks it as unavailable and returns None
    (permission checks still work — just without caching).
    """
    global _redis_client, _redis_unavailable

    if _redis_unavailable:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        from cortex.platform.config import get_settings

        settings = get_settings()
        client = Redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            decode_responses=True,
        )
        await client.ping()
        _redis_client = client
        logger.info("Redis connected for permission caching")
        return _redis_client
    except Exception:
        _redis_unavailable = True
        logger.info(
            "Redis unavailable — permission caching disabled (lookups still work via DB)"
        )
        return None


async def get_permission_checker(
    session: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> PermissionChecker:
    """
    Get permission checker instance.

    Args:
        session: Database session
        redis: Redis client

    Returns:
        PermissionChecker instance
    """
    from cortex.platform.config import get_settings

    settings = get_settings()
    return PermissionChecker(
        session=session,
        redis=redis,
        cache_ttl=settings.permission_cache_ttl_seconds,
    )


def require_permission(
    permission: Permission,
    resource_type: str | None = None,
    resource_id_param: str = "uid",
) -> Callable:
    """
    Require a specific permission for an endpoint.

    Usage:
        @app.get("/projects/{uid}")
        async def get_project(
            uid: str,
            principal: Principal = Depends(
                require_permission(Permission.PROJECT_VIEW, "project")
            ),
        ):
            # principal is guaranteed to have PROJECT_VIEW on this project
            ...

    Args:
        permission: Required permission
        resource_type: Resource type (if None, extracts from path)
        resource_id_param: Path parameter name for resource ID (default: "uid")

    Returns:
        FastAPI dependency
    """

    async def dependency(
        request: Request,
        checker: PermissionChecker = Depends(get_permission_checker),
    ) -> Principal:
        # Get current principal (from auth middleware)
        principal: Principal | None = getattr(request.state, "principal", None)
        if not principal:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract resource ID from path parameters
        resource_id = request.path_params.get(resource_id_param)
        if not resource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing resource ID parameter: {resource_id_param}",
            )

        # Determine resource type
        actual_resource_type = resource_type
        if actual_resource_type is None:
            # Try to infer from path
            path = request.url.path
            if "/accounts/" in path:
                actual_resource_type = "account"
            elif "/organizations/" in path or "/orgs/" in path:
                actual_resource_type = "organization"
            elif "/projects/" in path:
                actual_resource_type = "project"
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Cannot infer resource type from path",
                )

        # Check permission
        has_permission = await checker.check(
            principal=principal,
            resource_type=actual_resource_type,
            resource_id=resource_id,
            permission=permission,
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission.value}",
            )

        return principal

    return dependency


def require_any_permission(
    permissions: list[Permission],
    resource_type: str | None = None,
    resource_id_param: str = "uid",
) -> Callable:
    """
    Require ANY of the specified permissions (OR logic).

    Args:
        permissions: List of permissions (any one is sufficient)
        resource_type: Resource type
        resource_id_param: Path parameter name for resource ID

    Returns:
        FastAPI dependency
    """

    async def dependency(
        request: Request,
        checker: PermissionChecker = Depends(get_permission_checker),
    ) -> Principal:
        principal: Principal | None = getattr(request.state, "principal", None)
        if not principal:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        resource_id = request.path_params.get(resource_id_param)
        if not resource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing resource ID parameter: {resource_id_param}",
            )

        # Determine resource type
        actual_resource_type = resource_type or _infer_resource_type(request.url.path)

        # Check if principal has ANY permission
        has_any = await checker.check_any(
            principal=principal,
            resource_type=actual_resource_type,
            resource_id=resource_id,
            permissions=permissions,
        )

        if not has_any:
            perm_names = [p.value for p in permissions]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permissions: {', '.join(perm_names)}",
            )

        return principal

    return dependency


def require_all_permissions(
    permissions: list[Permission],
    resource_type: str | None = None,
    resource_id_param: str = "uid",
) -> Callable:
    """
    Require ALL of the specified permissions (AND logic).

    Args:
        permissions: List of permissions (all required)
        resource_type: Resource type
        resource_id_param: Path parameter name for resource ID

    Returns:
        FastAPI dependency
    """

    async def dependency(
        request: Request,
        checker: PermissionChecker = Depends(get_permission_checker),
    ) -> Principal:
        principal: Principal | None = getattr(request.state, "principal", None)
        if not principal:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        resource_id = request.path_params.get(resource_id_param)
        if not resource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing resource ID parameter: {resource_id_param}",
            )

        # Determine resource type
        actual_resource_type = resource_type or _infer_resource_type(request.url.path)

        # Check if principal has ALL permissions
        has_all = await checker.check_all(
            principal=principal,
            resource_type=actual_resource_type,
            resource_id=resource_id,
            permissions=permissions,
        )

        if not has_all:
            perm_names = [p.value for p in permissions]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permissions: {', '.join(perm_names)}",
            )

        return principal

    return dependency


def _infer_resource_type(path: str) -> str:
    """
    Infer resource type from request path.

    Args:
        path: Request path

    Returns:
        Resource type

    Raises:
        HTTPException: If cannot infer
    """
    if "/accounts/" in path:
        return "account"
    elif "/organizations/" in path or "/orgs/" in path:
        return "organization"
    elif "/projects/" in path:
        return "project"
    elif "/documents/" in path:
        return "document"
    elif "/conversations/" in path:
        return "conversation"
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cannot infer resource type from path",
        )
