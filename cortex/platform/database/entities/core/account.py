"""
Account entity.

Top-level billing entity that contains one or more organizations.
"""

from sqlalchemy import Column, String, Text, ForeignKey, Enum, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..base import BaseEntity
from ..enums import AccountStatus, SubscriptionTier


class Account(BaseEntity):
    """
    Account model (top-level billing entity).

    Hierarchy: Account -> Organization -> Project -> Resources
    """

    __tablename__ = "accounts"

    name = Column(String(255), nullable=False)
    billing_email = Column(String(255), nullable=False)
    status = Column(
        Enum(AccountStatus), nullable=False, default=AccountStatus.TRIAL
    )
    subscription_tier = Column(
        Enum(SubscriptionTier), nullable=False, default=SubscriptionTier.FREE
    )
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("principals.id"), nullable=False, index=True
    )
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    settings = Column(Text, nullable=True)

    # Relationships
    owner = relationship("Principal", foreign_keys=[owner_id])
    organizations = relationship(
        "Organization", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Account(id={self.id}, name={self.name}, "
            f"tier={self.subscription_tier}, status={self.status})>"
        )
