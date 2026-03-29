"""
Permission Definitions (SIMPLIFIED)

Simplified permission system with 5 basic permissions for 2 roles.
"""

from enum import Enum
from cortex.platform.database.models import Role


class Permission(str, Enum):
    """
    Simplified permission enumeration for RBAC.

    All resources use the same set of permissions.
    """

    # Resource access (applies to all resources: accounts, orgs, projects, documents, conversations)
    VIEW = "view"               # View any resource
    CREATE = "create"           # Create resources (projects, docs, convos)
    EDIT = "edit"               # Edit resources
    DELETE = "delete"           # Delete resources (ADMIN only)
    MANAGE_MEMBERS = "manage_members"  # Add/remove users, assign roles (ADMIN only)


# ============================================================================
# Role-Permission Mappings (SIMPLIFIED)
# ============================================================================

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        Permission.VIEW,
        Permission.CREATE,
        Permission.EDIT,
        Permission.DELETE,
        Permission.MANAGE_MEMBERS,
    },
    Role.USER: {
        Permission.VIEW,
        Permission.CREATE,
        Permission.EDIT,
    },
}


def get_permissions_for_role(role: Role) -> set[Permission]:
    """
    Get all permissions for a role.

    Args:
        role: Role enum value

    Returns:
        Set of permissions

    Raises:
        KeyError: If role is invalid
    """
    return ROLE_PERMISSIONS[role]


def has_permission(role: Role, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    Args:
        role: Role enum value
        permission: Permission to check

    Returns:
        True if role has permission, False otherwise
    """
    try:
        role_perms = get_permissions_for_role(role)
        return permission in role_perms
    except KeyError:
        return False
