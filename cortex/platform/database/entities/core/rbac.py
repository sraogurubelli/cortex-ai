"""
RBAC entities: Role, Permission, RolePermission, UserRole.

Account-level role-based access control with fine-grained permissions.
Complements the resource-level Membership model.

Adapted from synteraiq-engine core_platform/entities/core/rbac.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List

from sqlalchemy import (
    Column,
    String,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Index,
    CheckConstraint,
    DateTime,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import BaseEntity, Base
from ..mixins import StandardEntityMixin, SoftDeleteMixin


class Role(BaseEntity, StandardEntityMixin):
    """
    Role definition for account-wide access control.

    Account-scoped roles with permission assignments.
    System roles (is_system=True) cannot be deleted by users.
    """

    __tablename__ = "roles"

    name = Column(String(64), nullable=False)
    slug = Column(String(64), nullable=False)
    description = Column(String(255))
    is_system = Column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        Index("ix_roles_account_id", "account_id"),
        Index("ix_roles_created_at", "created_at"),
        CheckConstraint("length(slug) >= 2", name="ck_roles_slug_min_length"),
        CheckConstraint("length(name) >= 2", name="ck_roles_name_min_length"),
        {"comment": "Role definitions for RBAC system (account-scoped)"},
    )

    role_permissions = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )
    user_roles = relationship(
        "UserRole", back_populates="role", cascade="all, delete-orphan"
    )

    @property
    def permissions(self) -> List[Any]:
        if not self.role_permissions:
            return []
        return [rp.permission for rp in self.role_permissions if rp.permission]


class Permission(BaseEntity, StandardEntityMixin):
    """
    Permission definition for fine-grained access control.

    Hierarchical permission keys (e.g., "capex.request.create").
    Account-scoped for multi-tenancy.
    """

    __tablename__ = "permissions"

    key = Column(String(128), nullable=False)
    description = Column(String(255))

    __table_args__ = (
        UniqueConstraint("account_id", "key", name="uq_permissions_account_key"),
        Index(
            "ux_permissions_account_lower_key",
            "account_id",
            func.lower(key),
            unique=True,
        ),
        Index("ix_permissions_account_id", "account_id"),
        Index("ix_permissions_created_at", "created_at"),
        CheckConstraint("length(key) >= 3", name="ck_permissions_key_min_length"),
        CheckConstraint(
            "key ~ '^[a-z0-9._]+$'", name="ck_permissions_key_format"
        ),
        {"comment": "Permission definitions for RBAC system (account-scoped)"},
    )

    role_permissions = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    """
    Role-Permission mapping (join table).

    Composite PK prevents duplicates. Cascade delete from parent entities.
    """

    __tablename__ = "role_permissions"

    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    created_by = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="User ID who created this record (no FK constraint)",
    )

    __table_args__ = (
        Index("ix_role_permissions_role_id", "role_id"),
        Index("ix_role_permissions_permission_id", "permission_id"),
        {"comment": "Maps roles to permissions"},
    )

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class UserRole(BaseEntity, SoftDeleteMixin):
    """
    User-Role assignment for account-scope access control.

    Supports temporal role assignments with expiration,
    and delegation tracking.
    """

    __tablename__ = "user_roles"

    principal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Assignment metadata
    assigned_by = Column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Delegation
    is_delegated = Column(Boolean, nullable=False, server_default=text("false"))
    delegation_chain = Column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_user_roles_principal_id", "principal_id"),
        Index("ix_user_roles_role_id", "role_id"),
        Index("ix_user_roles_account_id", "account_id"),
        Index("ix_user_roles_expires_at", "expires_at"),
        Index("ix_user_roles_created_at", "created_at"),
        UniqueConstraint(
            "principal_id",
            "role_id",
            "account_id",
            name="uq_user_roles_assignment",
        ),
        {"comment": "User role assignments (account-scoped)"},
    )

    principal = relationship(
        "Principal", foreign_keys=[principal_id]
    )
    role = relationship("Role", back_populates="user_roles", foreign_keys=[role_id])
    account = relationship("Account", foreign_keys=[account_id])

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_active(self) -> bool:
        return not self.deleted_at and not self.is_expired()
