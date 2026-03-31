"""
User entity.

Business profile for human users. Linked 1:1 to a Principal (auth identity).
Service accounts (Principal with type=SERVICE_ACCOUNT) do NOT have a User record.

All domain entities (departments, roles, proposals, approvals, notifications)
reference User. Only auth middleware touches Principal directly.

Adapted from synteraiq-engine core_platform/entities/core/user.py
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func

from ..base import BaseEntity
from ..mixins import SoftDeleteMixin


def _norm_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not v or "@" not in v:
        raise ValueError("invalid email")
    return v


class User(BaseEntity, SoftDeleteMixin):
    """
    User profile (business identity).

    Represents a human user in the system with profile data, status,
    and relationships to departments, roles, etc.

    Linked 1:1 to Principal via principal_id.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ux_users_lower_email", func.lower(text("email")), unique=True),
        Index("ix_users_status", "status"),
        Index("ix_users_email_verified", "email_verified"),
        Index("ix_users_created_at", "created_at"),
        Index("ix_users_last_login", "last_login_at"),
        Index("ix_users_active", "status", "email_verified"),
        CheckConstraint(
            "status in ('active','inactive','suspended','deleted')",
            name="ck_users_status_known",
        ),
        CheckConstraint("length(email) >= 3", name="ck_users_email_min_length"),
        CheckConstraint("email LIKE '%@%'", name="ck_users_email_format"),
        {"comment": "User profiles with business identity and settings"},
    )

    # Link to auth identity (1:1)
    principal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="Linked auth identity (Principal)",
    )

    # Auth
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=True)

    # Profile
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)

    # Status
    status = Column(
        String(20), default="active", nullable=False, server_default=text("'active'")
    )
    email_verified = Column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )

    # Tracking
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Settings
    settings = Column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Relationships
    principal = relationship("Principal", foreign_keys=[principal_id], uselist=False)
    department_memberships = relationship(
        "DepartmentMembership",
        primaryjoin="User.principal_id == foreign(DepartmentMembership.principal_id)",
        viewonly=True,
    )
    user_roles = relationship(
        "UserRole",
        primaryjoin="User.principal_id == foreign(UserRole.principal_id)",
        viewonly=True,
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @validates("email")
    def _v_email(self, _, value: str) -> str:
        return _norm_email(value)
