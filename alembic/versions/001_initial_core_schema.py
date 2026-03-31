"""initial_core_schema

Revision ID: 001
Revises:
Create Date: 2026-03-30

Creates complete platform schema with 16 tables (UUID PKs):
 1. principals      - Authentication identities (users / service accounts)
 2. accounts        - Top-level billing entities
 3. organizations   - Business units within accounts
 4. users           - Human user profiles (1:1 with principal)
 5. projects        - Workspaces within organizations
 6. tokens          - Session, PAT, SAT tokens
 7. memberships     - Resource-level RBAC assignments
 8. departments     - Org structure (hierarchical)
 9. department_memberships - Principal-department mapping
10. roles           - Account-scoped RBAC roles
11. permissions     - Account-scoped permissions
12. role_permissions - Role-permission mapping
13. user_roles      - Principal-role assignments
14. business_roles  - Domain/playbook-scoped roles
15. documents       - File metadata + processing status
16. audit_events    - Universal event-sourcing audit log
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")
_GEN_UUID = sa.text("gen_random_uuid()")


def upgrade() -> None:
    """Create platform schema (16 tables)."""

    # -- Enum types --------------------------------------------------------
    principaltype = sa.Enum("USER", "SERVICE_ACCOUNT", name="principaltype")
    tokentype = sa.Enum("SESSION", "PAT", "SAT", name="tokentype")
    membershiprole = sa.Enum("ADMIN", "USER", name="membershiprole")
    accountstatus = sa.Enum("ACTIVE", "TRIAL", "SUSPENDED", "CANCELED", name="accountstatus")
    subscriptiontier = sa.Enum("FREE", "PRO", "TEAM", "ENTERPRISE", name="subscriptiontier")

    # =====================================================================
    # 1. principals (no deps)
    # =====================================================================
    op.create_table(
        "principals",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("principal_type", principaltype, nullable=False),
        sa.Column("admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("salt", sa.String(255), nullable=True),
        sa.Column("auth_provider", sa.String(50), nullable=False, server_default=sa.text("'jwt'")),
        sa.Column("google_id", sa.String(255), nullable=True),
        sa.Column("picture_url", sa.String(512), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_principals"),
    )
    op.create_index("ix_principals_email", "principals", ["email"], unique=True)
    op.create_index("ix_principals_google_id", "principals", ["google_id"], unique=True)
    op.create_index("ix_principals_created_by", "principals", ["created_by"])
    op.create_index("ix_principals_updated_by", "principals", ["updated_by"])

    # =====================================================================
    # 2. accounts (depends on principals)
    # =====================================================================
    op.create_table(
        "accounts",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("billing_email", sa.String(255), nullable=False),
        sa.Column("status", accountstatus, nullable=False),
        sa.Column("subscription_tier", subscriptiontier, nullable=False),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("trial_ends_at", _TS, nullable=True),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["principals.id"], name="fk_accounts_owner_principals"
        ),
    )
    op.create_index("ix_accounts_owner_id", "accounts", ["owner_id"])
    op.create_index("ix_accounts_created_by", "accounts", ["created_by"])
    op.create_index("ix_accounts_updated_by", "accounts", ["updated_by"])

    # =====================================================================
    # 3. organizations (depends on accounts, principals)
    # =====================================================================
    op.create_table(
        "organizations",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("account_id", _UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_organizations_account_accounts"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["principals.id"], name="fk_organizations_owner_principals"
        ),
    )
    op.create_index("ix_organizations_account_id", "organizations", ["account_id"])
    op.create_index("ix_organizations_owner_id", "organizations", ["owner_id"])
    op.create_index("ix_organizations_created_by", "organizations", ["created_by"])
    op.create_index("ix_organizations_updated_by", "organizations", ["updated_by"])

    # =====================================================================
    # 4. users (depends on principals)
    # =====================================================================
    op.create_table(
        "users",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("principal_id", _UUID, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", _TS, nullable=True),
        sa.Column("settings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
        sa.Column("delete_reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.ForeignKeyConstraint(
            ["principal_id"], ["principals.id"],
            name="fk_users_principal_principals", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["principals.id"],
            name="fk_users_deleted_by_principals", ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status in ('active','inactive','suspended','deleted')",
            name="ck_users_status_known",
        ),
        sa.CheckConstraint("length(email) >= 3", name="ck_users_email_min_length"),
        sa.CheckConstraint("email LIKE '%@%'", name="ck_users_email_format"),
    )
    op.create_index("ix_users_principal_id", "users", ["principal_id"], unique=True)
    op.create_index(
        "ux_users_lower_email", "users",
        [sa.text("lower(email)")], unique=True,
    )
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("ix_users_email_verified", "users", ["email_verified"])
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_users_last_login", "users", ["last_login_at"])
    op.create_index("ix_users_active", "users", ["status", "email_verified"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])
    op.create_index("ix_users_created_by", "users", ["created_by"])
    op.create_index("ix_users_updated_by", "users", ["updated_by"])

    # =====================================================================
    # 5. projects (depends on organizations, principals)
    # =====================================================================
    op.create_table(
        "projects",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_projects_org_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["principals.id"],
            name="fk_projects_owner_principals",
        ),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_index("ix_projects_created_by", "projects", ["created_by"])
    op.create_index("ix_projects_updated_by", "projects", ["updated_by"])

    # =====================================================================
    # 6. tokens (depends on principals)
    # =====================================================================
    op.create_table(
        "tokens",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("principal_id", _UUID, nullable=False),
        sa.Column("token_type", tokentype, nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_used_at", _TS, nullable=True),
        sa.Column("expires_at", _TS, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tokens"),
        sa.ForeignKeyConstraint(
            ["principal_id"], ["principals.id"],
            name="fk_tokens_principal_principals",
        ),
    )
    op.create_index("ix_tokens_principal_id", "tokens", ["principal_id"])

    # =====================================================================
    # 7. memberships (depends on principals)
    # =====================================================================
    op.create_table(
        "memberships",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("principal_id", _UUID, nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("role", membershiprole, nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.ForeignKeyConstraint(
            ["principal_id"], ["principals.id"],
            name="fk_memberships_principal_principals",
        ),
        sa.UniqueConstraint(
            "principal_id", "resource_type", "resource_id",
            name="uq_membership_principal_resource",
        ),
    )
    op.create_index("ix_memberships_principal_id", "memberships", ["principal_id"])
    op.create_index("ix_memberships_resource_type", "memberships", ["resource_type"])
    op.create_index("ix_memberships_resource_id", "memberships", ["resource_id"])

    # =====================================================================
    # 8. departments (depends on accounts, organizations, principals)
    # =====================================================================
    op.create_table(
        "departments",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", _UUID, nullable=True),
        sa.Column("organization_id", _UUID, nullable=True),
        sa.Column("manager_id", _UUID, nullable=True),
        sa.Column("cost_center", sa.String(50), nullable=True),
        sa.Column("annual_budget", sa.String(50), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("account_id", _UUID, nullable=False),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
        sa.Column("delete_reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.UniqueConstraint("account_id", "code", name="uq_department_account_code"),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["departments.id"],
            name="fk_departments_parent_departments", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_departments_org_organizations", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"], ["principals.id"],
            name="fk_departments_manager_principals", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_departments_account_accounts", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["principals.id"],
            name="fk_departments_deleted_by_principals", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_department_account_id", "departments", ["account_id"])
    op.create_index("ix_department_is_active", "departments", ["is_active"])
    op.create_index("ix_department_parent", "departments", ["parent_id"])
    op.create_index("ix_department_organization", "departments", ["organization_id"])
    op.create_index("ix_departments_created_by", "departments", ["created_by"])
    op.create_index("ix_departments_updated_by", "departments", ["updated_by"])
    op.create_index("ix_departments_deleted_at", "departments", ["deleted_at"])

    # =====================================================================
    # 9. department_memberships (depends on departments, principals)
    # =====================================================================
    op.create_table(
        "department_memberships",
        sa.Column("department_id", _UUID, nullable=False),
        sa.Column("principal_id", _UUID, nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("joined_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default=sa.text("'member'")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("attributes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("department_id", "principal_id", name="pk_department_memberships"),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"],
            name="fk_dept_memberships_dept_departments", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"], ["principals.id"],
            name="fk_dept_memberships_principal_principals", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status in ('active','inactive','suspended')",
            name="ck_dept_memberships_status_known",
        ),
        sa.CheckConstraint(
            "role in ('member','lead','coordinator','viewer')",
            name="ck_dept_memberships_role_known",
        ),
    )
    op.create_index("ix_dept_memberships_department_id", "department_memberships", ["department_id"])
    op.create_index("ix_dept_memberships_principal_id", "department_memberships", ["principal_id"])
    op.create_index("ix_dept_memberships_status", "department_memberships", ["status"])
    op.create_index("ix_dept_memberships_role", "department_memberships", ["role"])
    op.create_index("ix_dept_memberships_active", "department_memberships", ["department_id", "status"])
    op.create_index("ix_dept_memberships_created_by", "department_memberships", ["created_by"])
    op.create_index("ix_dept_memberships_updated_by", "department_memberships", ["updated_by"])

    # =====================================================================
    # 10. roles (depends on accounts, principals)
    # =====================================================================
    op.create_table(
        "roles",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("account_id", _UUID, nullable=False),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
        sa.Column("delete_reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_roles_account_accounts", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["principals.id"],
            name="fk_roles_deleted_by_principals", ondelete="SET NULL",
        ),
        sa.CheckConstraint("length(slug) >= 2", name="ck_roles_slug_min_length"),
        sa.CheckConstraint("length(name) >= 2", name="ck_roles_name_min_length"),
    )
    op.create_index("ix_roles_account_id", "roles", ["account_id"])
    op.create_index("ix_roles_created_at", "roles", ["created_at"])
    op.create_index("ix_roles_created_by", "roles", ["created_by"])
    op.create_index("ix_roles_updated_by", "roles", ["updated_by"])
    op.create_index("ix_roles_deleted_at", "roles", ["deleted_at"])

    # =====================================================================
    # 11. permissions (depends on accounts, principals)
    # =====================================================================
    op.create_table(
        "permissions",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("account_id", _UUID, nullable=False),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
        sa.Column("delete_reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("account_id", "key", name="uq_permissions_account_key"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_permissions_account_accounts", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["principals.id"],
            name="fk_permissions_deleted_by_principals", ondelete="SET NULL",
        ),
        sa.CheckConstraint("length(key) >= 3", name="ck_permissions_key_min_length"),
        sa.CheckConstraint("key ~ '^[a-z0-9._]+$'", name="ck_permissions_key_format"),
    )
    op.create_index("ix_permissions_account_id", "permissions", ["account_id"])
    op.create_index("ix_permissions_created_at", "permissions", ["created_at"])
    op.create_index(
        "ux_permissions_account_lower_key", "permissions",
        ["account_id", sa.text("lower(key)")], unique=True,
    )
    op.create_index("ix_permissions_created_by", "permissions", ["created_by"])
    op.create_index("ix_permissions_updated_by", "permissions", ["updated_by"])
    op.create_index("ix_permissions_deleted_at", "permissions", ["deleted_at"])

    # =====================================================================
    # 12. role_permissions (depends on roles, permissions)
    # =====================================================================
    op.create_table(
        "role_permissions",
        sa.Column("role_id", _UUID, nullable=False),
        sa.Column("permission_id", _UUID, nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW),
        sa.Column("created_by", _UUID, nullable=True),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"],
            name="fk_role_permissions_role_roles", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"],
            name="fk_role_permissions_perm_permissions", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])
    op.create_index("ix_role_permissions_created_by", "role_permissions", ["created_by"])

    # =====================================================================
    # 13. user_roles (depends on principals, roles, accounts)
    # =====================================================================
    op.create_table(
        "user_roles",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("principal_id", _UUID, nullable=False),
        sa.Column("role_id", _UUID, nullable=False),
        sa.Column("account_id", _UUID, nullable=False),
        sa.Column("assigned_by", _UUID, nullable=True),
        sa.Column("assigned_at", _TS, nullable=False, server_default=_NOW),
        sa.Column("expires_at", _TS, nullable=True),
        sa.Column("is_delegated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("delegation_chain", sa.String(500), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
        sa.Column("delete_reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_user_roles"),
        sa.UniqueConstraint(
            "principal_id", "role_id", "account_id",
            name="uq_user_roles_assignment",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"], ["principals.id"],
            name="fk_user_roles_principal_principals", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"],
            name="fk_user_roles_role_roles", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_user_roles_account_accounts", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"], ["principals.id"],
            name="fk_user_roles_assigned_by_principals", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["principals.id"],
            name="fk_user_roles_deleted_by_principals", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_user_roles_principal_id", "user_roles", ["principal_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_index("ix_user_roles_account_id", "user_roles", ["account_id"])
    op.create_index("ix_user_roles_expires_at", "user_roles", ["expires_at"])
    op.create_index("ix_user_roles_created_at", "user_roles", ["created_at"])
    op.create_index("ix_user_roles_deleted_at", "user_roles", ["deleted_at"])
    op.create_index("ix_user_roles_created_by", "user_roles", ["created_by"])
    op.create_index("ix_user_roles_updated_by", "user_roles", ["updated_by"])

    # =====================================================================
    # 14. business_roles (depends on accounts, principals)
    # =====================================================================
    op.create_table(
        "business_roles",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("scope", sa.String(50), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("updated_by", _UUID, nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("account_id", _UUID, nullable=False),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
        sa.Column("delete_reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_business_roles"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_business_roles_account_accounts", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["principals.id"],
            name="fk_business_roles_deleted_by_principals", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_business_roles_account_id", "business_roles", ["account_id"])
    op.create_index("ix_business_roles_code", "business_roles", ["account_id", "code"])
    op.create_index("ix_business_roles_created_by", "business_roles", ["created_by"])
    op.create_index("ix_business_roles_updated_by", "business_roles", ["updated_by"])
    op.create_index("ix_business_roles_deleted_at", "business_roles", ["deleted_at"])

    # =====================================================================
    # 15. documents (depends on organizations)
    # =====================================================================
    op.create_table(
        "documents",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_url", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("qdrant_doc_id", sa.String(100), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("embedding_status", sa.String(50), nullable=True),
        sa.Column("neo4j_doc_id", sa.String(100), nullable=True),
        sa.Column("entity_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("concept_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("relationship_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("graph_status", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_documents_org_organizations",
        ),
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_qdrant_doc_id", "documents", ["qdrant_doc_id"])
    op.create_index("ix_documents_neo4j_doc_id", "documents", ["neo4j_doc_id"])
    op.create_index("idx_documents_org_status", "documents", ["organization_id", "status"])
    op.create_index("idx_documents_org_created", "documents", ["organization_id", "created_at"])

    # =====================================================================
    # 16. audit_events (no FK deps -- UUID refs without constraints)
    # =====================================================================
    op.create_table(
        "audit_events",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", _UUID, nullable=False),
        sa.Column("account_id", _UUID, nullable=False),
        sa.Column("actor_id", _UUID, nullable=True),
        sa.Column("entity_audit_id", _UUID, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("stream_id", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_index("ix_audit_events_account", "audit_events", ["account_id"])
    op.create_index("ix_audit_events_actor", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index("ix_audit_events_stream", "audit_events", ["stream_id"])


def downgrade() -> None:
    """Drop all tables in reverse dependency order, then enum types."""

    # 16 → 1
    op.drop_table("audit_events")
    op.drop_table("documents")
    op.drop_table("business_roles")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("department_memberships")
    op.drop_table("departments")
    op.drop_table("memberships")
    op.drop_table("tokens")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("organizations")
    op.drop_table("accounts")
    op.drop_table("principals")

    # Enum types
    sa.Enum(name="subscriptiontier").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="accountstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="membershiprole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tokentype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="principaltype").drop(op.get_bind(), checkfirst=True)
