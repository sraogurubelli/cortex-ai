"""
Organization API Routes

CRUD operations for organizations with RBAC.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import (
    Principal,
    Organization,
    Membership,
    Role,
    get_db,
)
from cortex.platform.database.repositories import (
    AccountRepository,
    OrganizationRepository,
    ProjectRepository,
    MembershipRepository,
)

router = APIRouter(prefix="/api/v1", tags=["organizations"])


# ============================================================================
# Request/Response Models
# ============================================================================


class OrganizationInfo(BaseModel):
    """Organization information response."""

    id: str
    account_id: str
    name: str
    description: str | None
    owner_id: str
    created_at: datetime
    updated_at: datetime


class CreateOrganizationRequest(BaseModel):
    """Create organization request."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)


class UpdateOrganizationRequest(BaseModel):
    """Update organization request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)


class ProjectSummary(BaseModel):
    """Project summary."""

    id: str
    name: str
    description: str | None
    created_at: datetime


class OrganizationProjects(BaseModel):
    """Organization projects list."""

    projects: list[ProjectSummary]
    total: int


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/accounts/{account_uid}/organizations", response_model=OrganizationInfo, status_code=status.HTTP_201_CREATED)
async def create_organization(
    account_uid: str,
    request: CreateOrganizationRequest,
    principal: Principal = Depends(require_permission(Permission.EDIT, "account", "account_uid")),
    session: AsyncSession = Depends(get_db),
):
    """
    Create a new organization in an account.

    Requires ACCOUNT_EDIT permission on the account.
    Creator becomes OWNER of the organization.
    """
    account_repo = AccountRepository(session)
    org_repo = OrganizationRepository(session)
    membership_repo = MembershipRepository(session)

    # Verify account exists
    account = await account_repo.find_by_uid(account_uid)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Check if org name already exists in this account
    existing = await org_repo.find_by_name(account.id, request.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization name already exists in this account",
        )

    # Create organization
    org = Organization(
        uid=f"org_{uuid.uuid4().hex[:12]}",
        account_id=account.id,
        name=request.name,
        description=request.description,
        owner_id=principal.id,
    )
    org = await org_repo.create(org)

    # Create OWNER membership
    membership = Membership(
        principal_id=principal.id,
        resource_type="organization",
        resource_id=org.uid,
        role=Role.OWNER,
    )
    await membership_repo.create(membership)

    await session.commit()

    return OrganizationInfo(
        id=org.uid,
        account_id=account.uid,
        name=org.name,
        description=org.description,
        owner_id=str(org.owner_id),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.get("/organizations/{uid}", response_model=OrganizationInfo)
async def get_organization(
    uid: str,
    principal: Principal = Depends(require_permission(Permission.VIEW, "organization")),
    session: AsyncSession = Depends(get_db),
):
    """
    Get organization by ID.

    Requires ORG_VIEW permission.
    """
    org_repo = OrganizationRepository(session)
    account_repo = AccountRepository(session)

    org = await org_repo.find_by_uid(uid)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    account = await account_repo.find_by_id(org.account_id)

    return OrganizationInfo(
        id=org.uid,
        account_id=account.uid if account else str(org.account_id),
        name=org.name,
        description=org.description,
        owner_id=str(org.owner_id),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.patch("/organizations/{uid}", response_model=OrganizationInfo)
async def update_organization(
    uid: str,
    request: UpdateOrganizationRequest,
    principal: Principal = Depends(require_permission(Permission.EDIT, "organization")),
    session: AsyncSession = Depends(get_db),
):
    """
    Update organization settings.

    Requires ORG_EDIT permission.
    """
    org_repo = OrganizationRepository(session)
    account_repo = AccountRepository(session)

    org = await org_repo.find_by_uid(uid)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Update fields
    if request.name is not None:
        org.name = request.name

    if request.description is not None:
        org.description = request.description

    # Save changes
    org = await org_repo.update(org)
    await session.commit()

    account = await account_repo.find_by_id(org.account_id)

    return OrganizationInfo(
        id=org.uid,
        account_id=account.uid if account else str(org.account_id),
        name=org.name,
        description=org.description,
        owner_id=str(org.owner_id),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.get("/organizations/{uid}/projects", response_model=OrganizationProjects)
async def list_organization_projects(
    uid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_permission(Permission.VIEW, "organization")),
    session: AsyncSession = Depends(get_db),
):
    """
    List projects in an organization.

    Requires ORG_VIEW permission.
    """
    org_repo = OrganizationRepository(session)
    project_repo = ProjectRepository(session)

    # Verify organization exists
    org = await org_repo.find_by_uid(uid)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Get projects
    projects = await project_repo.find_by_organization(
        organization_id=org.id,
        limit=limit,
        offset=offset,
    )

    project_summaries = [
        ProjectSummary(
            id=project.uid,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
        )
        for project in projects
    ]

    return OrganizationProjects(
        projects=project_summaries,
        total=len(project_summaries),
    )
