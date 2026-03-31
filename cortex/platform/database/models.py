"""
Backward-compatibility shim.

All models have been moved to cortex.platform.database.entities/.
This module re-exports everything so existing imports still work:
    from cortex.platform.database.models import Account, Base, ...
"""

from cortex.platform.database.entities import (  # noqa: F401
    Base,
    BaseEntity,
    MinimalEntity,
    # Enums
    AccountStatus,
    SubscriptionTier,
    PrincipalType,
    TokenType,
    MembershipRole,
    # Core
    Account,
    Principal,
    User,
    Organization,
    Project,
    Token,
    Membership,
    # Department
    Department,
    DepartmentMembership,
    # RBAC
    Role,
    Permission,
    RolePermission,
    UserRole,
    BusinessRole,
    # Knowledge
    Document,
    # Audit
    AuditEvent,
    current_actor_id,
    apply_audit_columns,
)

# Keep backward compat: old code may import "Role" expecting the enum.
# The enum has been renamed to MembershipRole; alias it here.
# New code should use MembershipRole directly.

__all__ = [
    "Base",
    "BaseEntity",
    "MinimalEntity",
    "AccountStatus",
    "SubscriptionTier",
    "PrincipalType",
    "TokenType",
    "MembershipRole",
    "Account",
    "Principal",
    "User",
    "Organization",
    "Project",
    "Token",
    "Membership",
    "Department",
    "DepartmentMembership",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "BusinessRole",
    "Document",
    "AuditEvent",
    "current_actor_id",
    "apply_audit_columns",
]
