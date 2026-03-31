"""
Permission Definitions (SIMPLIFIED)

Simplified permission system with 5 basic permissions for 2 roles.
"""

from enum import Enum
from cortex.platform.database.models import MembershipRole


class Permission(str, Enum):
    """
    Simplified permission enumeration for RBAC.

    All resources use the same set of permissions.
    """

    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    MANAGE_MEMBERS = "manage_members"


# ============================================================================
# Role-Permission Mappings (SIMPLIFIED)
# ============================================================================

ROLE_PERMISSIONS: dict[MembershipRole, set[Permission]] = {
    MembershipRole.ADMIN: {
        Permission.VIEW,
        Permission.CREATE,
        Permission.EDIT,
        Permission.DELETE,
        Permission.MANAGE_MEMBERS,
    },
    MembershipRole.USER: {
        Permission.VIEW,
        Permission.CREATE,
        Permission.EDIT,
    },
}


def get_permissions_for_role(role: MembershipRole) -> set[Permission]:
    """Get all permissions for a membership role."""
    return ROLE_PERMISSIONS[role]


def has_permission(role: MembershipRole, permission: Permission) -> bool:
    """Check if a membership role has a specific permission."""
    try:
        role_perms = get_permissions_for_role(role)
        return permission in role_perms
    except KeyError:
        return False
