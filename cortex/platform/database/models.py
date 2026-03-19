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
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    """RBAC role enumeration."""

    OWNER = "owner"  # Full access including delete
    ADMIN = "admin"  # Manage resources but cannot delete
    CONTRIBUTOR = "contributor"  # Create and edit
    READER = "reader"  # Read-only access


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
    role = Column(Enum(Role), nullable=False, default=Role.READER)
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
    conversations = relationship("Conversation", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project(id={self.id}, uid={self.uid}, name={self.name}, org_id={self.organization_id})>"


class Conversation(Base):
    """
    Conversation model for AI chat sessions.

    Conversations belong to projects and principals.
    Linked to LangGraph thread_id for session persistence.
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_id = Column(Integer, ForeignKey("principals.id"), nullable=False, index=True)
    thread_id = Column(String(255), nullable=False, index=True)  # LangGraph thread ID
    title = Column(String(500), nullable=True)  # Auto-generated from first message
    meta_json = Column("meta_json", Text, nullable=True)  # JSON: {model: "gpt-4o", agent_name: "assistant"}
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    project = relationship("Project", back_populates="conversations")
    principal = relationship("Principal", foreign_keys=[principal_id])
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation(id={self.id}, uid={self.uid}, project_id={self.project_id}, thread_id={self.thread_id})>"


class Message(Base):
    """
    Message model for conversation history.

    Stores individual messages in conversations (user, assistant, tool).
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # 'user', 'assistant', 'system', 'tool'
    content = Column(Text, nullable=False)
    tool_calls = Column(Text, nullable=True)  # JSON: [{id: "", name: "", args: {}}]
    tool_call_id = Column(String(255), nullable=True)  # For tool response messages
    meta_json = Column("meta_json", Text, nullable=True)  # JSON: {model: "", tokens: {}, cache_metrics: {}}
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    # Index for efficient message retrieval
    __table_args__ = (
        Index("idx_messages_conversation_created", "conversation_id", "created_at"),
    )

    def __repr__(self):
        return f"<Message(id={self.id}, uid={self.uid}, conversation_id={self.conversation_id}, role={self.role})>"
