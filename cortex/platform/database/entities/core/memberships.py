"""
Membership entity.

Resource-level RBAC: defines a principal's role on a specific resource.
Uses polymorphic resource_type + resource_id pattern.
"""

from sqlalchemy import Column, String, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey

from ..base import MinimalEntity
from ..enums import MembershipRole


class Membership(MinimalEntity):
    """
    Membership model for resource-level RBAC.

    Defines principal's role on a resource.
    Supports multi-tenancy via resource_type and resource_id.

    For account-level RBAC, see UserRole in rbac.py.
    """

    __tablename__ = "memberships"

    principal_id = Column(
        UUID(as_uuid=True), ForeignKey("principals.id"), nullable=False, index=True
    )
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(String(255), nullable=False, index=True)
    role = Column(Enum(MembershipRole), nullable=False, default=MembershipRole.USER)

    # Relationships
    principal = relationship("Principal", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint(
            "principal_id",
            "resource_type",
            "resource_id",
            name="uq_membership_principal_resource",
        ),
    )

    def __repr__(self):
        return (
            f"<Membership(principal_id={self.principal_id}, "
            f"resource_type={self.resource_type}, "
            f"resource_id={self.resource_id}, role={self.role})>"
        )
