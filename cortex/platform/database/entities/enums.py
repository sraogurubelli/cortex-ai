"""
Enum definitions for platform entities.

Centralizes all enums used across entity models.
"""

from enum import Enum as PyEnum


class PrincipalType(str, PyEnum):
    """Principal type enumeration."""

    USER = "user"
    SERVICE_ACCOUNT = "service_account"


class TokenType(str, PyEnum):
    """Token type enumeration."""

    SESSION = "session"
    PAT = "pat"
    SAT = "sat"


class MembershipRole(str, PyEnum):
    """
    Simple role enum for resource-level memberships.

    Used by the Membership table for coarse-grained resource access.
    Fine-grained RBAC is handled by the Role/Permission/UserRole tables.
    """

    ADMIN = "admin"
    USER = "user"


class AccountStatus(str, PyEnum):
    """Account status enumeration."""

    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    CANCELED = "canceled"


class SubscriptionTier(str, PyEnum):
    """Subscription tier enumeration."""

    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"
