"""
RBAC Permission Checker

Permission verification with Redis caching (15s TTL).
Adapted from harness-code/gitness/app/auth/authz/membership.go
"""

import json
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.auth.permissions import Permission, ROLE_PERMISSIONS
from cortex.platform.database import Principal, MembershipRepository
from cortex.platform.database.repositories import ProjectRepository


class PermissionChecker:
    """
    Permission checker with caching.

    Checks if a principal has a specific permission on a resource.
    Uses Redis for caching with 15-second TTL to reduce database load.
    """

    def __init__(
        self,
        session: AsyncSession,
        redis: Optional[Redis] = None,
        cache_ttl: int = 15,
    ):
        """
        Initialize permission checker.

        Args:
            session: Database session
            redis: Redis client for caching (optional)
            cache_ttl: Cache TTL in seconds (default: 15)
        """
        self.session = session
        self.redis = redis
        self.cache_ttl = cache_ttl
        self.membership_repo = MembershipRepository(session)

    async def check(
        self,
        principal: Principal,
        resource_type: str,
        resource_id: str,
        permission: Permission,
    ) -> bool:
        """
        Check if principal has permission on resource (SIMPLIFIED).

        Simplified logic:
        1. System admin → always True
        2. Blocked → always False
        3. Get principal's role on resource (or parent)
        4. Check if role grants permission

        Args:
            principal: Principal to check
            resource_type: Resource type (account, organization, project, etc.)
            resource_id: Resource ID (UID)
            permission: Permission to check

        Returns:
            True if principal has permission, False otherwise
        """
        # System admin bypass
        if principal.admin:
            return True

        # Blocked principals denied
        if principal.blocked:
            return False

        # Try cache first (stores role as string)
        cache_key = f"perm:{principal.id}:{permission}:{resource_type}:{resource_id}"
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached is not None:
                cached_value = cached.decode("utf-8") if isinstance(cached, bytes) else cached
                if cached_value == "true":
                    return True
                elif cached_value == "false":
                    return False

        # Get role on resource
        role = await self.membership_repo.get_role(
            principal_id=principal.id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        # If no direct membership, check parent resource
        if not role and resource_type == "project":
            # Try org membership (inherit from organization)
            # This fixes the "no project membership" issue
            project_repo = ProjectRepository(self.session)
            project = await project_repo.find_by_uid(resource_id)
            if project:
                org_role = await self.membership_repo.get_role(
                    principal_id=principal.id,
                    resource_type="organization",
                    resource_id=project.organization.uid,
                )
                role = org_role  # Inherit role from org

        if not role:
            result = False
        else:
            # Check if role grants permission (using simplified mapping)
            allowed_permissions = ROLE_PERMISSIONS.get(role, set())
            result = permission in allowed_permissions

        # Cache result
        if self.redis:
            await self.redis.setex(cache_key, self.cache_ttl, "true" if result else "false")

        return result

    async def check_any(
        self,
        principal: Principal,
        resource_type: str,
        resource_id: str,
        permissions: list[Permission],
    ) -> bool:
        """
        Check if principal has ANY of the specified permissions.

        Args:
            principal: Principal to check
            resource_type: Resource type
            resource_id: Resource ID
            permissions: List of permissions (OR logic)

        Returns:
            True if principal has any permission, False otherwise
        """
        for permission in permissions:
            if await self.check(principal, resource_type, resource_id, permission):
                return True
        return False

    async def check_all(
        self,
        principal: Principal,
        resource_type: str,
        resource_id: str,
        permissions: list[Permission],
    ) -> bool:
        """
        Check if principal has ALL of the specified permissions.

        Args:
            principal: Principal to check
            resource_type: Resource type
            resource_id: Resource ID
            permissions: List of permissions (AND logic)

        Returns:
            True if principal has all permissions, False otherwise
        """
        for permission in permissions:
            if not await self.check(principal, resource_type, resource_id, permission):
                return False
        return True

    async def get_role(
        self,
        principal: Principal,
        resource_type: str,
        resource_id: str,
    ) -> Optional[str]:
        """
        Get principal's role on a resource.

        Args:
            principal: Principal
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            Role name or None
        """
        # Try cache first
        if self.redis:
            cached_role = await self._get_cached_role(
                principal.id, resource_type, resource_id
            )
            if cached_role is not None:
                return cached_role if cached_role != "" else None

        # Cache miss - query database
        role = await self.membership_repo.get_role(
            principal_id=principal.id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        # Cache result
        if self.redis:
            role_value = role.value if role else ""
            await self._cache_role(principal.id, resource_type, resource_id, role_value)

        return role.value if role else None

    async def invalidate_cache(
        self,
        principal_id: int,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        """
        Invalidate cached permissions for a resource.

        Useful when membership changes.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            True if cache was invalidated, False if no Redis
        """
        if not self.redis:
            return False

        cache_key = self._cache_key(principal_id, resource_type, resource_id)
        await self.redis.delete(cache_key)
        return True

    async def invalidate_all_for_principal(self, principal_id: int) -> int:
        """
        Invalidate all cached permissions for a principal.

        Args:
            principal_id: Principal ID

        Returns:
            Number of cache keys deleted
        """
        if not self.redis:
            return 0

        # Find all cache keys for this principal
        pattern = self._cache_key(principal_id, "*", "*")
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            keys.append(key)

        # Delete all keys
        if keys:
            return await self.redis.delete(*keys)
        return 0

    def _cache_key(
        self, principal_id: int, resource_type: str, resource_id: str
    ) -> str:
        """
        Generate cache key for permission.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            Cache key string
        """
        return f"perm:{principal_id}:{resource_type}:{resource_id}"

    async def _get_cached_role(
        self, principal_id: int, resource_type: str, resource_id: str
    ) -> Optional[str]:
        """
        Get role from cache.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            Role name, empty string (no membership), or None (cache miss)
        """
        if not self.redis:
            return None

        cache_key = self._cache_key(principal_id, resource_type, resource_id)
        cached = await self.redis.get(cache_key)

        if cached is None:
            return None  # Cache miss

        return cached.decode("utf-8") if isinstance(cached, bytes) else cached

    async def _cache_role(
        self,
        principal_id: int,
        resource_type: str,
        resource_id: str,
        role: str,
    ) -> None:
        """
        Cache role for principal on resource.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID
            role: Role name (empty string if no membership)
        """
        if not self.redis:
            return

        cache_key = self._cache_key(principal_id, resource_type, resource_id)
        await self.redis.setex(cache_key, self.cache_ttl, role)
