"""
Database Module

SQLAlchemy models for core platform features:
- Accounts (billing entities)
- Organizations (business units)
- Projects (workspaces)
- Principals (users/service accounts)
- Tokens (session, PAT, SAT)
- Memberships (RBAC)
- Documents (file metadata and processing status)

Hierarchy: Account → Organization → Project

Storage Layers:
- PostgreSQL: Core application data (this module)
- Neo4j: Knowledge graph (entities, concepts, relationships)
- Qdrant: Vector embeddings (RAG search)
- S3/Filesystem: Document files (binary storage)
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
    # Documents
    Document,
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
    # Documents
    "Document",
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
]
