"""
Principal entity.

Represents an authenticated entity (user or service account) in the system.
"""

from sqlalchemy import Column, String, Boolean, Enum
from sqlalchemy.orm import relationship

from ..base import BaseEntity
from ..enums import PrincipalType


class Principal(BaseEntity):
    """
    Principal model (user or service account).

    Represents an authenticated entity in the system.
    """

    __tablename__ = "principals"

    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    principal_type = Column(
        Enum(PrincipalType), nullable=False, default=PrincipalType.USER
    )
    admin = Column(Boolean, nullable=False, default=False)
    blocked = Column(Boolean, nullable=False, default=False)
    salt = Column(String(255), nullable=True)

    # OAuth support
    auth_provider = Column(
        String(50),
        nullable=False,
        default="jwt",
        comment="Auth provider: jwt, google, github, etc",
    )
    google_id = Column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
        comment="Google account ID (sub claim from ID token)",
    )
    picture_url = Column(String(512), nullable=True, comment="Profile picture URL")
    email_verified = Column(
        Boolean, nullable=False, default=False, comment="Email verification status"
    )

    # Relationships
    tokens = relationship(
        "Token", back_populates="principal", cascade="all, delete-orphan"
    )
    memberships = relationship(
        "Membership", back_populates="principal", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Principal(id={self.id}, email={self.email}, admin={self.admin})>"
        )
