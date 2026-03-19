"""
Database Module

SQLAlchemy models for platform features:
- Accounts (billing entities)
- Organizations (business units)
- Projects (workspaces)
- Principals (users/service accounts)
- Tokens (session, PAT, SAT)
- Memberships (RBAC)

Hierarchy: Account → Organization → Project
"""

from cortex.platform.database.models import (
    Base,
    # Account & Organization Hierarchy
    Account,
    AccountStatus,
    SubscriptionTier,
    Organization,
    Project,
    # Principals & Authentication
    Principal,
    PrincipalType,
    Token,
    TokenType,
    # RBAC
    Membership,
    Role,
    # Conversations & Messages
    Conversation,
    Message,
)
from cortex.platform.database.session import (
    DatabaseManager,
    get_db_manager,
    get_db,
    init_db,
    close_db,
)
from cortex.platform.database.repositories import (
    BaseRepository,
    AccountRepository,
    OrganizationRepository,
    ProjectRepository,
    PrincipalRepository,
    TokenRepository,
    MembershipRepository,
    ConversationRepository,
    MessageRepository,
)

__all__ = [
    # Base
    "Base",
    # Account Hierarchy
    "Account",
    "AccountStatus",
    "SubscriptionTier",
    "Organization",
    "Project",
    # Principals & Authentication
    "Principal",
    "PrincipalType",
    "Token",
    "TokenType",
    # RBAC
    "Membership",
    "Role",
    # Conversations & Messages
    "Conversation",
    "Message",
    # Session Management
    "DatabaseManager",
    "get_db_manager",
    "get_db",
    "init_db",
    "close_db",
    # Repositories (OLTP Layer)
    "BaseRepository",
    "AccountRepository",
    "OrganizationRepository",
    "ProjectRepository",
    "PrincipalRepository",
    "TokenRepository",
    "MembershipRepository",
    "ConversationRepository",
    "MessageRepository",
]
