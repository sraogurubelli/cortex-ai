"""
Organization entity.

Business unit within an account. Contains projects and has its own members.
Replaces synteraiq-engine's Workspace concept.
"""

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..base import BaseEntity


class Organization(BaseEntity):
    """
    Organization model (business unit within account).

    Hierarchy: Account -> Organization -> Project
    """

    __tablename__ = "organizations"

    account_id = Column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("principals.id"), nullable=False, index=True
    )
    settings = Column(Text, nullable=True)

    # Relationships
    account = relationship("Account", back_populates="organizations")
    owner = relationship("Principal", foreign_keys=[owner_id])
    projects = relationship(
        "Project", back_populates="organization", cascade="all, delete-orphan"
    )
    documents = relationship(
        "Document", back_populates="organization", cascade="all, delete-orphan"
    )
    departments = relationship(
        "Department", back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Organization(id={self.id}, name={self.name}, "
            f"account_id={self.account_id})>"
        )
