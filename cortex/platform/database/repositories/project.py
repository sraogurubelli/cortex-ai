"""
Project Repository

Data access layer for Project model.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Project
from cortex.platform.database.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project operations."""

    def __init__(self, session: AsyncSession):
        """Initialize project repository."""
        super().__init__(Project, session)

    async def find_by_organization(
        self, organization_id: int, limit: int = 100, offset: int = 0
    ) -> List[Project]:
        """
        Find all projects in an organization.

        Args:
            organization_id: Organization ID
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of projects
        """
        result = await self.session.execute(
            select(Project)
            .where(Project.organization_id == organization_id)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_by_owner(self, owner_id: int) -> List[Project]:
        """
        Find all projects owned by a principal.

        Args:
            owner_id: Principal ID

        Returns:
            List of projects
        """
        result = await self.session.execute(
            select(Project)
            .where(Project.owner_id == owner_id)
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_name(
        self, organization_id: int, name: str
    ) -> Optional[Project]:
        """
        Find project by name within an organization.

        Args:
            organization_id: Organization ID
            name: Project name

        Returns:
            Project instance or None
        """
        result = await self.session.execute(
            select(Project).where(
                Project.organization_id == organization_id, Project.name == name
            )
        )
        return result.scalar_one_or_none()
