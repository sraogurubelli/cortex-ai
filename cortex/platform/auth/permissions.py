"""
Permission Definitions

Fine-grained permissions for RBAC system.
Adapted from harness-code/gitness/types/enum/permission.go
"""

from enum import Enum


class Permission(str, Enum):
    """
    Permission enumeration for RBAC.

    Permissions are organized by resource type.
    """

    # =========================================================================
    # Account Permissions
    # =========================================================================
    ACCOUNT_VIEW = "account_view"  # View account details
    ACCOUNT_EDIT = "account_edit"  # Edit account settings
    ACCOUNT_DELETE = "account_delete"  # Delete account
    ACCOUNT_MANAGE_BILLING = "account_manage_billing"  # Manage subscription & billing
    ACCOUNT_MANAGE_MEMBERS = "account_manage_members"  # Invite/remove members

    # =========================================================================
    # Organization Permissions
    # =========================================================================
    ORG_VIEW = "org_view"  # View organization details
    ORG_EDIT = "org_edit"  # Edit organization settings
    ORG_DELETE = "org_delete"  # Delete organization
    ORG_MANAGE_MEMBERS = "org_manage_members"  # Invite/remove members
    ORG_CREATE_PROJECT = "org_create_project"  # Create projects in org

    # =========================================================================
    # Project Permissions
    # =========================================================================
    PROJECT_VIEW = "project_view"  # View project details
    PROJECT_EDIT = "project_edit"  # Edit project settings
    PROJECT_DELETE = "project_delete"  # Delete project
    PROJECT_MANAGE_MEMBERS = "project_manage_members"  # Invite/remove members

    # =========================================================================
    # Document Permissions (for RAG documents)
    # =========================================================================
    DOCUMENT_VIEW = "document_view"  # View documents
    DOCUMENT_UPLOAD = "document_upload"  # Upload documents
    DOCUMENT_EDIT = "document_edit"  # Edit document metadata
    DOCUMENT_DELETE = "document_delete"  # Delete documents

    # =========================================================================
    # Conversation Permissions (for AI conversations)
    # =========================================================================
    CONVERSATION_VIEW = "conversation_view"  # View conversations
    CONVERSATION_CREATE = "conversation_create"  # Create conversations
    CONVERSATION_EDIT = "conversation_edit"  # Edit conversation metadata
    CONVERSATION_DELETE = "conversation_delete"  # Delete conversations

    # =========================================================================
    # API Key Permissions
    # =========================================================================
    APIKEY_VIEW = "apikey_view"  # View API keys
    APIKEY_CREATE = "apikey_create"  # Create API keys
    APIKEY_DELETE = "apikey_delete"  # Delete API keys


# ============================================================================
# Role-Permission Mappings
# ============================================================================

ROLE_PERMISSIONS = {
    # OWNER - Full access to everything
    "owner": [
        # Account
        Permission.ACCOUNT_VIEW,
        Permission.ACCOUNT_EDIT,
        Permission.ACCOUNT_DELETE,
        Permission.ACCOUNT_MANAGE_BILLING,
        Permission.ACCOUNT_MANAGE_MEMBERS,
        # Organization
        Permission.ORG_VIEW,
        Permission.ORG_EDIT,
        Permission.ORG_DELETE,
        Permission.ORG_MANAGE_MEMBERS,
        Permission.ORG_CREATE_PROJECT,
        # Project
        Permission.PROJECT_VIEW,
        Permission.PROJECT_EDIT,
        Permission.PROJECT_DELETE,
        Permission.PROJECT_MANAGE_MEMBERS,
        # Documents
        Permission.DOCUMENT_VIEW,
        Permission.DOCUMENT_UPLOAD,
        Permission.DOCUMENT_EDIT,
        Permission.DOCUMENT_DELETE,
        # Conversations
        Permission.CONVERSATION_VIEW,
        Permission.CONVERSATION_CREATE,
        Permission.CONVERSATION_EDIT,
        Permission.CONVERSATION_DELETE,
        # API Keys
        Permission.APIKEY_VIEW,
        Permission.APIKEY_CREATE,
        Permission.APIKEY_DELETE,
    ],
    # ADMIN - Manage resources but cannot delete account/org
    "admin": [
        # Account
        Permission.ACCOUNT_VIEW,
        Permission.ACCOUNT_EDIT,
        Permission.ACCOUNT_MANAGE_MEMBERS,
        # Organization
        Permission.ORG_VIEW,
        Permission.ORG_EDIT,
        Permission.ORG_MANAGE_MEMBERS,
        Permission.ORG_CREATE_PROJECT,
        # Project
        Permission.PROJECT_VIEW,
        Permission.PROJECT_EDIT,
        Permission.PROJECT_DELETE,
        Permission.PROJECT_MANAGE_MEMBERS,
        # Documents
        Permission.DOCUMENT_VIEW,
        Permission.DOCUMENT_UPLOAD,
        Permission.DOCUMENT_EDIT,
        Permission.DOCUMENT_DELETE,
        # Conversations
        Permission.CONVERSATION_VIEW,
        Permission.CONVERSATION_CREATE,
        Permission.CONVERSATION_EDIT,
        Permission.CONVERSATION_DELETE,
        # API Keys
        Permission.APIKEY_VIEW,
        Permission.APIKEY_CREATE,
        Permission.APIKEY_DELETE,
    ],
    # CONTRIBUTOR - Create and edit content
    "contributor": [
        # Account
        Permission.ACCOUNT_VIEW,
        # Organization
        Permission.ORG_VIEW,
        Permission.ORG_CREATE_PROJECT,
        # Project
        Permission.PROJECT_VIEW,
        Permission.PROJECT_EDIT,
        # Documents
        Permission.DOCUMENT_VIEW,
        Permission.DOCUMENT_UPLOAD,
        Permission.DOCUMENT_EDIT,
        # Conversations
        Permission.CONVERSATION_VIEW,
        Permission.CONVERSATION_CREATE,
        Permission.CONVERSATION_EDIT,
        # API Keys
        Permission.APIKEY_VIEW,
        Permission.APIKEY_CREATE,
    ],
    # READER - Read-only access
    "reader": [
        # Account
        Permission.ACCOUNT_VIEW,
        # Organization
        Permission.ORG_VIEW,
        # Project
        Permission.PROJECT_VIEW,
        # Documents
        Permission.DOCUMENT_VIEW,
        # Conversations
        Permission.CONVERSATION_VIEW,
        # API Keys
        Permission.APIKEY_VIEW,
    ],
}


def get_permissions_for_role(role: str) -> list[Permission]:
    """
    Get all permissions for a role.

    Args:
        role: Role name (owner, admin, contributor, reader)

    Returns:
        List of permissions

    Raises:
        KeyError: If role is invalid
    """
    return ROLE_PERMISSIONS[role.lower()]


def has_permission(role: str, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    Args:
        role: Role name
        permission: Permission to check

    Returns:
        True if role has permission, False otherwise
    """
    try:
        role_perms = get_permissions_for_role(role)
        return permission in role_perms
    except KeyError:
        return False
