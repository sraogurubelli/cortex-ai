"""
Authentication & Authorization Module

Features:
- JWT-based authentication with multi-salt rotation
- Token extraction from multiple sources
- RBAC with permission checking and caching
- FastAPI dependencies for easy integration
"""

from cortex.platform.auth.jwt import JWTHandler, TokenClaims
from cortex.platform.auth.permissions import Permission, ROLE_PERMISSIONS
from cortex.platform.auth.rbac import PermissionChecker
from cortex.platform.auth.dependencies import (
    require_permission,
    require_any_permission,
    require_all_permissions,
    get_permission_checker,
)

__all__ = [
    # JWT Authentication
    "JWTHandler",
    "TokenClaims",
    # RBAC
    "Permission",
    "ROLE_PERMISSIONS",
    "PermissionChecker",
    # FastAPI Dependencies
    "require_permission",
    "require_any_permission",
    "require_all_permissions",
    "get_permission_checker",
]
