"""
Project API Routes

CRUD operations for projects with RBAC.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import (
    Principal,
    Project,
    Membership,
    Role,
    get_db,
)
from cortex.platform.database.repositories import (
    OrganizationRepository,
    ProjectRepository,
    MembershipRepository,
)

router = APIRouter(prefix="/api/v1", tags=["projects"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ProjectInfo(BaseModel):
    """Project information response."""

    id: str
    organization_id: str
    name: str
    description: str | None
    owner_id: str
    created_at: datetime
    updated_at: datetime


class CreateProjectRequest(BaseModel):
    """Create project request."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)


class UpdateProjectRequest(BaseModel):
    """Update project request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/organizations/{org_uid}/projects", response_model=ProjectInfo, status_code=status.HTTP_201_CREATED)
async def create_project(
    org_uid: str,
    request: CreateProjectRequest,
    principal: Principal = Depends(require_permission(Permission.CREATE, "organization", "org_uid")),
    session: AsyncSession = Depends(get_db),
):
    """
    Create a new project in an organization.

    Requires ORG_CREATE_PROJECT permission.
    Creator becomes OWNER of the project.
    """
    org_repo = OrganizationRepository(session)
    project_repo = ProjectRepository(session)
    membership_repo = MembershipRepository(session)

    # Verify organization exists
    org = await org_repo.find_by_uid(org_uid)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Check if project name already exists in this organization
    existing = await project_repo.find_by_name(org.id, request.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project name already exists in this organization",
        )

    # Create project
    project = Project(
        uid=f"prj_{uuid.uuid4().hex[:12]}",
        organization_id=org.id,
        name=request.name,
        description=request.description,
        owner_id=principal.id,
    )
    project = await project_repo.create(project)

    # Create OWNER membership
    membership = Membership(
        principal_id=principal.id,
        resource_type="project",
        resource_id=project.uid,
        role=Role.OWNER,
    )
    await membership_repo.create(membership)

    await session.commit()

    return ProjectInfo(
        id=project.uid,
        organization_id=org.uid,
        name=project.name,
        description=project.description,
        owner_id=str(project.owner_id),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("/projects/{uid}", response_model=ProjectInfo)
async def get_project(
    uid: str,
    principal: Principal = Depends(require_permission(Permission.VIEW, "project")),
    session: AsyncSession = Depends(get_db),
):
    """
    Get project by ID.

    Requires PROJECT_VIEW permission.
    """
    project_repo = ProjectRepository(session)
    org_repo = OrganizationRepository(session)

    project = await project_repo.find_by_uid(uid)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    org = await org_repo.find_by_id(project.organization_id)

    return ProjectInfo(
        id=project.uid,
        organization_id=org.uid if org else str(project.organization_id),
        name=project.name,
        description=project.description,
        owner_id=str(project.owner_id),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.patch("/projects/{uid}", response_model=ProjectInfo)
async def update_project(
    uid: str,
    request: UpdateProjectRequest,
    principal: Principal = Depends(require_permission(Permission.EDIT, "project")),
    session: AsyncSession = Depends(get_db),
):
    """
    Update project settings.

    Requires PROJECT_EDIT permission.
    """
    project_repo = ProjectRepository(session)
    org_repo = OrganizationRepository(session)

    project = await project_repo.find_by_uid(uid)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Update fields
    if request.name is not None:
        project.name = request.name

    if request.description is not None:
        project.description = request.description

    # Save changes
    project = await project_repo.update(project)
    await session.commit()

    org = await org_repo.find_by_id(project.organization_id)

    return ProjectInfo(
        id=project.uid,
        organization_id=org.uid if org else str(project.organization_id),
        name=project.name,
        description=project.description,
        owner_id=str(project.owner_id),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.delete("/projects/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    uid: str,
    principal: Principal = Depends(require_permission(Permission.DELETE, "project")),
    session: AsyncSession = Depends(get_db),
):
    """
    Delete a project.

    Requires PROJECT_DELETE permission.
    """
    project_repo = ProjectRepository(session)

    deleted = await project_repo.delete_by_uid(uid)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    await session.commit()
    return None
