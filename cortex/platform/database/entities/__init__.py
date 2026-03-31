"""
Entity module for Cortex AI platform.

Provides base classes, mixins, enums, and entity definitions.
All models are re-exported here for convenient import.

Adapted from synteraiq-engine core_platform/entities/ package structure.
"""

from .base import Base, BaseEntity, MinimalEntity

from .enums import (
    AccountStatus,
    SubscriptionTier,
    PrincipalType,
    TokenType,
    MembershipRole,
)

# Core entities
from .core.account import Account
from .core.principal import Principal
from .core.user import User
from .core.organization import Organization
from .core.project import Project
from .core.token import Token
from .core.memberships import Membership
from .core.department import Department, DepartmentMembership
from .core.rbac import Role, Permission, RolePermission, UserRole
from .core.business_role import BusinessRole

# Knowledge entities
from .knowledge.document import Document

# Audit
from .audit.audit_event import AuditEvent
from .audit.context import current_actor_id
from .audit.hooks import apply_audit_columns

__all__ = [
    # Base classes
    "Base",
    "BaseEntity",
    "MinimalEntity",
    # Enums
    "AccountStatus",
    "SubscriptionTier",
    "PrincipalType",
    "TokenType",
    "MembershipRole",
    # Core entities
    "Account",
    "Principal",
    "User",
    "Organization",
    "Project",
    "Token",
    "Membership",
    # Department
    "Department",
    "DepartmentMembership",
    # RBAC
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "BusinessRole",
    # Knowledge
    "Document",
    # Audit
    "AuditEvent",
    "current_actor_id",
    "apply_audit_columns",
]
