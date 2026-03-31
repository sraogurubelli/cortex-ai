"""
Project entity.

Workspace within an organization that groups resources (documents, conversations, etc.).
"""

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..base import BaseEntity


class Project(BaseEntity):
    """
    Project model (workspace within organization).

    Projects group resources and memberships.
    Hierarchy: Account -> Organization -> Project -> Resources
    """

    __tablename__ = "projects"

    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("principals.id"), nullable=False, index=True
    )
    settings = Column(Text, nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="projects")
    owner = relationship("Principal", foreign_keys=[owner_id])

    def __repr__(self):
        return (
            f"<Project(id={self.id}, name={self.name}, "
            f"org_id={self.organization_id})>"
        )
