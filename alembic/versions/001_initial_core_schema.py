"""initial_core_schema

Revision ID: 001
Revises:
Create Date: 2026-03-29

Creates core database schema with 7 tables:
- principals: Users and service accounts (authentication)
- accounts: Top-level billing entities
- organizations: Business units within accounts
- projects: Workspaces within organizations
- tokens: Session, PAT, and SAT tokens
- memberships: RBAC role assignments
- documents: File metadata and processing status
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create core schema tables."""

    # =========================================================================
    # 1. Create principals table (no dependencies)
    # =========================================================================
    op.create_table(
        'principals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('principal_type', sa.Enum('USER', 'SERVICE_ACCOUNT', name='principaltype'), nullable=False),
        sa.Column('admin', sa.Boolean(), nullable=False),
        sa.Column('blocked', sa.Boolean(), nullable=False),
        sa.Column('salt', sa.String(length=255), nullable=True),
        sa.Column('auth_provider', sa.String(length=50), nullable=False),
        sa.Column('google_id', sa.String(length=255), nullable=True),
        sa.Column('picture_url', sa.String(length=512), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_principals_uid'), 'principals', ['uid'], unique=True)
    op.create_index(op.f('ix_principals_email'), 'principals', ['email'], unique=True)
    op.create_index(op.f('ix_principals_google_id'), 'principals', ['google_id'], unique=True)

    # =========================================================================
    # 2. Create accounts table (depends on principals)
    # =========================================================================
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('billing_email', sa.String(length=255), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'TRIAL', 'SUSPENDED', 'CANCELED', name='accountstatus'), nullable=False),
        sa.Column('subscription_tier', sa.Enum('FREE', 'PRO', 'TEAM', 'ENTERPRISE', name='subscriptiontier'), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('settings', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['principals.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_accounts_uid'), 'accounts', ['uid'], unique=True)
    op.create_index(op.f('ix_accounts_owner_id'), 'accounts', ['owner_id'], unique=False)

    # =========================================================================
    # 3. Create organizations table (depends on accounts, principals)
    # =========================================================================
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.String(length=255), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('settings', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['principals.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_organizations_uid'), 'organizations', ['uid'], unique=True)
    op.create_index(op.f('ix_organizations_account_id'), 'organizations', ['account_id'], unique=False)
    op.create_index(op.f('ix_organizations_owner_id'), 'organizations', ['owner_id'], unique=False)

    # =========================================================================
    # 4. Create projects table (depends on organizations, principals)
    # =========================================================================
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.String(length=255), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('settings', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['principals.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_uid'), 'projects', ['uid'], unique=True)
    op.create_index(op.f('ix_projects_organization_id'), 'projects', ['organization_id'], unique=False)
    op.create_index(op.f('ix_projects_owner_id'), 'projects', ['owner_id'], unique=False)

    # =========================================================================
    # 5. Create tokens table (depends on principals)
    # =========================================================================
    op.create_table(
        'tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.String(length=255), nullable=False),
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('token_type', sa.Enum('SESSION', 'PAT', 'SAT', name='tokentype'), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['principal_id'], ['principals.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tokens_uid'), 'tokens', ['uid'], unique=True)
    op.create_index(op.f('ix_tokens_principal_id'), 'tokens', ['principal_id'], unique=False)

    # =========================================================================
    # 6. Create memberships table (depends on principals)
    # =========================================================================
    op.create_table(
        'memberships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'USER', name='role'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['principal_id'], ['principals.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('principal_id', 'resource_type', 'resource_id', name='uq_membership_principal_resource')
    )
    op.create_index(op.f('ix_memberships_principal_id'), 'memberships', ['principal_id'], unique=False)
    op.create_index(op.f('ix_memberships_resource_type'), 'memberships', ['resource_type'], unique=False)
    op.create_index(op.f('ix_memberships_resource_id'), 'memberships', ['resource_id'], unique=False)

    # =========================================================================
    # 7. Create documents table (depends on organizations)
    # =========================================================================
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('uid', sa.String(length=255), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_url', sa.String(length=512), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('qdrant_doc_id', sa.String(length=100), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('embedding_status', sa.String(length=50), nullable=True),
        sa.Column('neo4j_doc_id', sa.String(length=100), nullable=True),
        sa.Column('entity_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('concept_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('relationship_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('graph_status', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_uid'), 'documents', ['uid'], unique=True)
    op.create_index(op.f('ix_documents_organization_id'), 'documents', ['organization_id'], unique=False)
    op.create_index(op.f('ix_documents_file_hash'), 'documents', ['file_hash'], unique=False)
    op.create_index(op.f('ix_documents_qdrant_doc_id'), 'documents', ['qdrant_doc_id'], unique=False)
    op.create_index(op.f('ix_documents_neo4j_doc_id'), 'documents', ['neo4j_doc_id'], unique=False)
    op.create_index('idx_documents_org_status', 'documents', ['organization_id', 'status'], unique=False)
    op.create_index('idx_documents_org_created', 'documents', ['organization_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Drop all core schema tables."""

    # Drop in reverse order of creation to respect foreign key constraints
    op.drop_index('idx_documents_org_created', table_name='documents')
    op.drop_index('idx_documents_org_status', table_name='documents')
    op.drop_index(op.f('ix_documents_neo4j_doc_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_qdrant_doc_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_file_hash'), table_name='documents')
    op.drop_index(op.f('ix_documents_organization_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_uid'), table_name='documents')
    op.drop_table('documents')

    op.drop_index(op.f('ix_memberships_resource_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_resource_type'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_principal_id'), table_name='memberships')
    op.drop_table('memberships')

    op.drop_index(op.f('ix_tokens_principal_id'), table_name='tokens')
    op.drop_index(op.f('ix_tokens_uid'), table_name='tokens')
    op.drop_table('tokens')

    op.drop_index(op.f('ix_projects_owner_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_organization_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_uid'), table_name='projects')
    op.drop_table('projects')

    op.drop_index(op.f('ix_organizations_owner_id'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_account_id'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_uid'), table_name='organizations')
    op.drop_table('organizations')

    op.drop_index(op.f('ix_accounts_owner_id'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_uid'), table_name='accounts')
    op.drop_table('accounts')

    op.drop_index(op.f('ix_principals_google_id'), table_name='principals')
    op.drop_index(op.f('ix_principals_email'), table_name='principals')
    op.drop_index(op.f('ix_principals_uid'), table_name='principals')
    op.drop_table('principals')
