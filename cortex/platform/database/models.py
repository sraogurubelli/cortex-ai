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


class AuditLog(Base):
    """
    Audit log entry for tracking mutations across the platform.

    Records who did what, to which resource, and when.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("principals.id"), nullable=True, index=True)
    actor_uid = Column(String(255), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(String(255), nullable=True, index=True)
    resource_name = Column(String(500), nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    request_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor = relationship("Principal", foreign_keys=[actor_id])

    __table_args__ = (
        Index("idx_audit_actor_created", "actor_id", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, resource={self.resource_type}/{self.resource_id})>"


class UsageRecord(Base):
    """
    Usage metering record for per-tenant token/cost tracking.

    Aggregated from session-level model_usage data.
    """

    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    project_id = Column(String(255), nullable=True, index=True)
    principal_id = Column(String(255), nullable=True, index=True)
    model = Column(String(255), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cached_tokens = Column(Integer, nullable=False, default=0)
    request_count = Column(Integer, nullable=False, default=0)
    cost_estimate_usd = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_usage_tenant_date", "tenant_id", "date"),
        Index("idx_usage_tenant_model_date", "tenant_id", "model", "date"),
    )

    def __repr__(self):
        return f"<UsageRecord(tenant={self.tenant_id}, model={self.model}, date={self.date}, tokens={self.total_tokens})>"


class FeatureFlag(Base):
    """
    Lightweight feature flag for per-tenant feature gating.
    """

    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("key", "tenant_id", name="uq_flag_key_tenant"),
    )

    def __repr__(self):
        return f"<FeatureFlag(key={self.key}, tenant={self.tenant_id}, enabled={self.enabled})>"


class Webhook(Base):
    """
    Outbound webhook registration.

    Tenants register URLs to receive event notifications.
    """

    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    secret = Column(String(255), nullable=True)
    events = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<Webhook(uid={self.uid}, tenant={self.tenant_id}, url={self.url[:50]})>"


class WebhookDelivery(Base):
    """
    Record of a webhook delivery attempt.
    """

    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    webhook_id = Column(Integer, ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    attempt = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    webhook = relationship("Webhook")

    def __repr__(self):
        return f"<WebhookDelivery(webhook_id={self.webhook_id}, event={self.event_type}, success={self.success})>"


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
    attachments_json = Column(Text, nullable=True)  # JSON: [{id, name, mime_type, size_bytes}]
    rating = Column(Integer, nullable=True)  # -1 = thumbs down, 0 = neutral, 1 = thumbs up
    rating_feedback = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    # Index for efficient message retrieval
    __table_args__ = (
        Index("idx_messages_conversation_created", "conversation_id", "created_at"),
    )

    def __repr__(self):
        return f"<Message(id={self.id}, uid={self.uid}, conversation_id={self.conversation_id}, role={self.role})>"
