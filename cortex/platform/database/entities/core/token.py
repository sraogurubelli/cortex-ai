"""
Token entity.

Authentication tokens for principals: session, PAT, and SAT.
"""

from sqlalchemy import Column, String, Text, ForeignKey, Enum, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..base import MinimalEntity
from ..enums import TokenType


class Token(MinimalEntity):
    """
    Token model for authentication.

    Supports multiple token types:
    - SESSION: Short-lived session tokens
    - PAT: Personal Access Tokens (long-lived)
    - SAT: Service Account Tokens
    """

    __tablename__ = "tokens"

    principal_id = Column(
        UUID(as_uuid=True), ForeignKey("principals.id"), nullable=False, index=True
    )
    token_type = Column(Enum(TokenType), nullable=False, default=TokenType.SESSION)
    token_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    scopes = Column(Text, nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    principal = relationship("Principal", back_populates="tokens")

    def __repr__(self):
        return (
            f"<Token(id={self.id}, type={self.token_type}, "
            f"principal_id={self.principal_id})>"
        )
