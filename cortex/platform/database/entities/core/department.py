"""
Department and DepartmentMembership entities.

Represents organizational departments within an account, scoped to an organization.
Departments support hierarchical structure (parent/child) and user membership.

Adapted from synteraiq-engine core_platform/entities/core/department.py
and core_platform/entities/core/memberships.py (DepartmentMembership).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Column,
    String,
    Text,
    ForeignKey,
    Boolean,
    Index,
    UniqueConstraint,
    CheckConstraint,
    DateTime,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from ..base import BaseEntity, Base
from ..mixins import StandardEntityMixin


class Department(BaseEntity, StandardEntityMixin):
    """
    Department entity.

    Represents a department or organizational unit within an account,
    scoped to an organization. Supports hierarchical parent/child structure.
    """

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("account_id", "code", name="uq_department_account_code"),
        Index("ix_department_account_id", "account_id"),
        Index("ix_department_is_active", "is_active"),
        Index("ix_department_parent", "parent_id"),
        Index("ix_department_organization", "organization_id"),
    )

    code = Column(
        String(50), nullable=False, comment="Unique department code within account"
    )
    name = Column(String(255), nullable=False, comment="Department name")
    description = Column(Text, nullable=True, comment="Department description")

    # Hierarchical structure
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        comment="Parent department for hierarchical structure",
    )

    # Organization scope (replaces synteraiq-engine's workspace_id)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        comment="Organization for data isolation",
    )

    # Department head/manager
    manager_id = Column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="SET NULL"),
        nullable=True,
        comment="Department manager/head",
    )

    # Cost center
    cost_center = Column(
        String(50), nullable=True, comment="Cost center code for financial tracking"
    )
    annual_budget = Column(
        String(50),
        nullable=True,
        comment="Annual budget allocation (stored as string for flexibility)",
    )
    currency = Column(
        String(3), nullable=False, default="USD", comment="Default currency"
    )

    # Status
    is_active = Column(
        Boolean, nullable=False, default=True, comment="Whether department is active"
    )

    # Contact
    email = Column(String(255), nullable=True, comment="Department contact email")
    phone = Column(String(50), nullable=True, comment="Department contact phone")
    location = Column(
        String(255), nullable=True, comment="Physical location of department"
    )

    # Metadata
    meta_data = Column(
        "metadata",
        Text,
        nullable=True,
        comment="Additional department metadata in JSON format",
    )

    # Relationships
    parent = relationship(
        "Department", remote_side="Department.id", backref="children"
    )
    organization = relationship("Organization", foreign_keys=[organization_id])
    manager = relationship("Principal", foreign_keys=[manager_id])
    memberships = relationship(
        "DepartmentMembership",
        back_populates="department",
        cascade="all, delete-orphan",
        foreign_keys="DepartmentMembership.department_id",
    )

    @property
    def full_path(self) -> str:
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name

    @property
    def level(self) -> int:
        if self.parent:
            return self.parent.level + 1
        return 0

    def __repr__(self) -> Any:
        return f"<Department(code={self.code}, name={self.name})>"


class DepartmentMembership(Base):
    """
    User-Department membership tracking.

    Many-to-many relationship between principals and departments
    with role and status tracking.
    """

    __tablename__ = "department_memberships"

    # Composite PK
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    principal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Timestamps & audit
    created_at = Column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    joined_at = Column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    created_by = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="User ID who created this record (no FK constraint)",
    )
    updated_by = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="User ID who updated this record (no FK constraint)",
    )

    # Department-specific fields
    role = Column(
        String(50),
        nullable=False,
        server_default=text("'member'"),
        comment="Role within department (member, lead, coordinator, viewer)",
    )
    status = Column(
        String(32), nullable=False, server_default=text("'active'")
    )
    attributes = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        Index("ix_dept_memberships_department_id", "department_id"),
        Index("ix_dept_memberships_principal_id", "principal_id"),
        Index("ix_dept_memberships_status", "status"),
        Index("ix_dept_memberships_role", "role"),
        Index("ix_dept_memberships_active", "department_id", "status"),
        CheckConstraint(
            "status in ('active','inactive','suspended')",
            name="ck_dept_memberships_status_known",
        ),
        CheckConstraint(
            "role in ('member','lead','coordinator','viewer')",
            name="ck_dept_memberships_role_known",
        ),
        {"comment": "Maps principals to departments for many-to-many relationship"},
    )

    department = relationship(
        "Department", back_populates="memberships", foreign_keys=[department_id]
    )
    principal = relationship("Principal", foreign_keys=[principal_id])
