"""
Database Module

SQLAlchemy models for core platform features:
- Accounts (billing entities)
- Organizations (business units)
- Projects (workspaces)
- Principals (users/service accounts)
- Tokens (session, PAT, SAT)
- Memberships (resource-level RBAC)
- Departments (org structure)
- Roles, Permissions, UserRoles (account-level RBAC)
- Documents (file metadata and processing status)

Hierarchy: Account -> Organization -> Project

Storage Layers:
- PostgreSQL: Core application data (this module)
- Neo4j: Knowledge graph (entities, concepts, relationships)
- Qdrant: Vector embeddings (RAG search)
- S3/Filesystem: Document files (binary storage)
"""

from cortex.platform.database.entities import (
    Base,
    BaseEntity,
    MinimalEntity,
    # Enums
    AccountStatus,
    SubscriptionTier,
    PrincipalType,
    TokenType,
    MembershipRole,
    # Account & Organization Hierarchy
    Account,
    Organization,
    Project,
    # Principals & Authentication
    Principal,
    User,
    Token,
    # Resource-level RBAC
    Membership,
    # Org Structure
    Department,
    DepartmentMembership,
    # Account-level RBAC
    Role,
    Permission,
    RolePermission,
    UserRole,
    BusinessRole,
    # Knowledge
    Document,
    # Audit
    AuditEvent,
    current_actor_id,
    apply_audit_columns,
)

# Session and repository imports are deferred so that entity-only usage
# (e.g. Alembic env, tests) does not require the full config stack.
_session_loaded = False


def _load_session():
    global _session_loaded
    global DatabaseManager, get_db_manager, get_db, init_db, close_db
    if not _session_loaded:
        from cortex.platform.database.session import (
            DatabaseManager as _DM,
            get_db_manager as _gdm,
            get_db as _gdb,
            init_db as _idb,
            close_db as _cdb,
        )
        DatabaseManager = _DM
        get_db_manager = _gdm
        get_db = _gdb
        init_db = _idb
        close_db = _cdb
        _session_loaded = True


_repos_loaded = False


def _load_repos():
    global _repos_loaded
    global BaseRepository, AccountRepository, OrganizationRepository
    global ProjectRepository, PrincipalRepository, TokenRepository, MembershipRepository
    global UserRepository
    if not _repos_loaded:
        from cortex.platform.database.repositories import (
            BaseRepository as _BR,
            AccountRepository as _AR,
            OrganizationRepository as _OR,
            ProjectRepository as _PR,
            PrincipalRepository as _PrR,
            TokenRepository as _TR,
            MembershipRepository as _MR,
            UserRepository as _UR,
        )
        BaseRepository = _BR
        AccountRepository = _AR
        OrganizationRepository = _OR
        ProjectRepository = _PR
        PrincipalRepository = _PrR
        TokenRepository = _TR
        MembershipRepository = _MR
        UserRepository = _UR
        _repos_loaded = True


def __getattr__(name):
    """Lazy-load session and repository symbols on first access."""
    _session_names = {"DatabaseManager", "get_db_manager", "get_db", "init_db", "close_db"}
    _repo_names = {
        "BaseRepository", "AccountRepository", "OrganizationRepository",
        "ProjectRepository", "PrincipalRepository", "TokenRepository",
        "MembershipRepository", "UserRepository",
    }
    if name in _session_names:
        _load_session()
        return globals()[name]
    if name in _repo_names:
        _load_repos()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Base
    "Base",
    "BaseEntity",
    "MinimalEntity",
    # Enums
    "AccountStatus",
    "SubscriptionTier",
    "PrincipalType",
    "TokenType",
    "MembershipRole",
    # Account Hierarchy
    "Account",
    "Organization",
    "Project",
    # Principals & Authentication
    "Principal",
    "User",
    "Token",
    # Resource-level RBAC
    "Membership",
    # Org Structure
    "Department",
    "DepartmentMembership",
    # Account-level RBAC
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "BusinessRole",
    # Knowledge
    "Document",
    # Audit
    "AuditEvent",
    "current_actor_id",
    "apply_audit_columns",
    # Session Management (lazy)
    "DatabaseManager",
    "get_db_manager",
    "get_db",
    "init_db",
    "close_db",
    # Repositories (lazy)
    "BaseRepository",
    "AccountRepository",
    "OrganizationRepository",
    "ProjectRepository",
    "PrincipalRepository",
    "TokenRepository",
    "MembershipRepository",
    "UserRepository",
]
