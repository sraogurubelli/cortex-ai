"""
BusinessRole entity.

Domain-level roles that define what a person does in a playbook context
(e.g., HOD, Finance Controller, Project Manager).

Distinct from RBAC Role which grants system permissions.
BusinessRole is used by RoleMap to assign users to business functions
within playbooks, driving approval chains and workflow routing.

Adapted from synteraiq-engine core_platform/entities/core/business_role.py
"""

from sqlalchemy import Column, String, Index

from ..base import BaseEntity
from ..mixins import StandardEntityMixin


class BusinessRole(BaseEntity, StandardEntityMixin):
    """
    Business role definition.

    Playbook-scoped (or global when playbook_id is null) roles that represent
    organizational functions like HOD, Finance Controller, etc.

    These roles are mapped to users via RoleMap and drive:
    - Approval chain resolution
    - Workflow step assignment
    - Threshold-based routing
    """

    __tablename__ = "business_roles"
    __table_args__ = (
        Index("ix_business_roles_account_id", "account_id"),
        Index("ix_business_roles_code", "account_id", "code"),
        {"comment": "Domain roles for playbook-driven business functions"},
    )

    code = Column(
        String(50),
        nullable=False,
        comment="Unique role code within account (e.g., 'hod', 'finance_controller')",
    )
    name = Column(
        String(255), nullable=False, comment="Display name (e.g., 'Head of Department')"
    )
    category = Column(
        String(100),
        nullable=True,
        comment="Role category (e.g., 'approval', 'management', 'finance')",
    )
    scope = Column(
        String(50),
        nullable=True,
        comment="Scope level (e.g., 'department', 'organization', 'global')",
    )
    description = Column(String(500), nullable=True)
