"""
Database Models for Platform Features

SQLAlchemy models for:
- Accounts (top-level billing entities)
- Organizations (business units within accounts)
- Projects (workspaces within organizations)
- Principals (users/service accounts)
- Tokens (session, PAT, SAT)
- Memberships (RBAC)

Hierarchy: Account → Organization → Project → Resources

Adapted from harness-code/gitness database schemas.
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class PrincipalType(str, PyEnum):
    """Principal type enumeration."""

    USER = "user"
    SERVICE_ACCOUNT = "service_account"


class TokenType(str, PyEnum):
    """Token type enumeration."""

    SESSION = "session"  # Short-lived session token
    PAT = "pat"  # Personal Access Token
    SAT = "sat"  # Service Account Token


class Role(str, PyEnum):
    """RBAC role enumeration (SIMPLIFIED)."""

    ADMIN = "admin"  # Full access: view, create, edit, delete, manage members
    USER = "user"    # Regular user: view, create, edit (no delete or member management)


class AccountStatus(str, PyEnum):
    """Account status enumeration."""

    ACTIVE = "active"  # Active subscription
    TRIAL = "trial"  # Trial period
    SUSPENDED = "suspended"  # Payment issue or violation
    CANCELED = "canceled"  # User canceled


class SubscriptionTier(str, PyEnum):
    """Subscription tier enumeration."""

    FREE = "free"  # Free tier
    PRO = "pro"  # Professional tier
    TEAM = "team"  # Team tier
    ENTERPRISE = "enterprise"  # Enterprise tier


class Account(Base):
    """
    Account model (top-level billing entity).

    Represents a billing account that contains one or more organizations.
    Handles subscription, billing, and account-level settings.
    """

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    billing_email = Column(String(255), nullable=False)
    status = Column(Enum(AccountStatus), nullable=False, default=AccountStatus.TRIAL)
    subscription_tier = Column(
        Enum(SubscriptionTier), nullable=False, default=SubscriptionTier.FREE
    )
    owner_id = Column(Integer, ForeignKey("principals.id"), nullable=False, index=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    settings = Column(Text, nullable=True)  # JSON settings
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    owner = relationship("Principal", foreign_keys=[owner_id])
    organizations = relationship(
        "Organization", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Account(id={self.id}, uid={self.uid}, name={self.name}, tier={self.subscription_tier}, status={self.status})>"


class Organization(Base):
    """
    Organization model (business unit within account).

    Represents a team or business unit within an account.
    Contains projects and has its own members.
    """

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("principals.id"), nullable=False, index=True)
    settings = Column(Text, nullable=True)  # JSON settings
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    account = relationship("Account", back_populates="organizations")
    owner = relationship("Principal", foreign_keys=[owner_id])
    projects = relationship("Project", back_populates="organization", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization(id={self.id}, uid={self.uid}, name={self.name}, account_id={self.account_id})>"


class Principal(Base):
    """
    Principal model (user or service account).

    Represents an authenticated entity in the system.
    """

    __tablename__ = "principals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)  # Unique identifier
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    principal_type = Column(
        Enum(PrincipalType), nullable=False, default=PrincipalType.USER
    )
    admin = Column(Boolean, nullable=False, default=False)  # System admin flag
    blocked = Column(Boolean, nullable=False, default=False)  # Account blocked
    salt = Column(String(255), nullable=True)  # Password salt (if using password auth)

    # OAuth Support
    auth_provider = Column(
        String(50), nullable=False, default="jwt",
        comment="Auth provider: jwt, google, github, etc"
    )
    google_id = Column(
        String(255), nullable=True, unique=True, index=True,
        comment="Google account ID (sub claim from ID token)"
    )
    picture_url = Column(
        String(512), nullable=True,
        comment="Profile picture URL"
    )
    email_verified = Column(
        Boolean, nullable=False, default=False,
        comment="Email verification status"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    tokens = relationship("Token", back_populates="principal", cascade="all, delete-orphan")
    memberships = relationship(
        "Membership", back_populates="principal", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Principal(id={self.id}, uid={self.uid}, email={self.email}, admin={self.admin})>"


class Token(Base):
    """
    Token model for authentication.

    Supports multiple token types:
    - SESSION: Short-lived session tokens
    - PAT: Personal Access Tokens (long-lived)
    - SAT: Service Account Tokens
    """

    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)  # Token identifier
    principal_id = Column(Integer, ForeignKey("principals.id"), nullable=False, index=True)
    token_type = Column(Enum(TokenType), nullable=False, default=TokenType.SESSION)
    token_hash = Column(String(255), nullable=False)  # Hashed token value
    name = Column(String(255), nullable=True)  # Optional name for PAT/SAT
    scopes = Column(Text, nullable=True)  # JSON array of scopes
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    principal = relationship("Principal", back_populates="tokens")

    def __repr__(self):
        return f"<Token(id={self.id}, uid={self.uid}, type={self.token_type}, principal_id={self.principal_id})>"


class Membership(Base):
    """
    Membership model for RBAC.

    Defines principal's role on a resource.
    Supports multi-tenancy via resource_type and resource_id.
    """

    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    principal_id = Column(Integer, ForeignKey("principals.id"), nullable=False, index=True)
    resource_type = Column(
        String(50), nullable=False, index=True
    )  # "project", "document", etc.
    resource_id = Column(String(255), nullable=False, index=True)  # Resource UUID
    role = Column(Enum(Role), nullable=False, default=Role.USER)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    principal = relationship("Principal", back_populates="memberships")

    # Unique constraint: one role per principal per resource
    __table_args__ = (
        UniqueConstraint(
            "principal_id",
            "resource_type",
            "resource_id",
            name="uq_membership_principal_resource",
        ),
    )

    def __repr__(self):
        return f"<Membership(principal_id={self.principal_id}, resource_type={self.resource_type}, resource_id={self.resource_id}, role={self.role})>"


class Project(Base):
    """
    Project model (workspace within organization).

    Projects group resources (documents, conversations, etc.) and memberships.
    Belongs to an organization.
    """

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("principals.id"), nullable=False, index=True)
    settings = Column(Text, nullable=True)  # JSON settings
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization", back_populates="projects")
    owner = relationship("Principal", foreign_keys=[owner_id])

    def __repr__(self):
        return f"<Project(id={self.id}, uid={self.uid}, name={self.name}, org_id={self.organization_id})>"


class Document(Base):
    """
    Document model for file metadata and processing status.

    Stores metadata about uploaded documents. Actual file content is stored in:
    - S3 or filesystem (file_url points to storage location)
    - Qdrant (chunked embeddings for RAG)
    - Neo4j (knowledge graph entities/concepts)

    This model tracks processing status across all three storage layers.
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # File metadata
    filename = Column(String(255), nullable=False)
    file_url = Column(String(512), nullable=False)  # S3 URL or filesystem path
    file_size = Column(Integer, nullable=False)  # Size in bytes
    file_hash = Column(String(64), nullable=False, index=True)  # SHA256 hash
    mime_type = Column(String(100), nullable=True)

    # Overall processing status
    status = Column(
        String(50),
        nullable=False,
        default="uploading",
        index=True,
    )  # uploading, processing, completed, failed

    # RAG metadata (Qdrant vector store)
    qdrant_doc_id = Column(String(100), nullable=True, index=True)  # Document ID in Qdrant
    chunk_count = Column(Integer, nullable=False, default=0)
    embedding_status = Column(String(50), nullable=True)  # pending, completed, failed

    # GraphRAG metadata (Neo4j knowledge graph)
    neo4j_doc_id = Column(String(100), nullable=True, index=True)  # Document ID in Neo4j
    entity_count = Column(Integer, nullable=False, default=0)
    concept_count = Column(Integer, nullable=False, default=0)
    relationship_count = Column(Integer, nullable=False, default=0)
    graph_status = Column(String(50), nullable=True)  # pending, completed, failed

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization", back_populates="documents")

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_documents_org_status", "organization_id", "status"),
        Index("idx_documents_org_created", "organization_id", "created_at"),
    )

    def __repr__(self):
        return f"<Document(id={self.id}, uid={self.uid}, filename={self.filename}, status={self.status})>"
