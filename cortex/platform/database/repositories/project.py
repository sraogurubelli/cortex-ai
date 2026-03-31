"""Project Repository"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Project
from cortex.platform.database.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Project, session)

    async def find_by_organization(
        self, organization_id: UUID | str, limit: int = 100, offset: int = 0
    ) -> List[Project]:
        if isinstance(organization_id, str):
            organization_id = UUID(organization_id)
        result = await self.session.execute(
            select(Project)
            .where(Project.organization_id == organization_id)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_by_owner(self, owner_id: UUID | str) -> List[Project]:
        if isinstance(owner_id, str):
            owner_id = UUID(owner_id)
        result = await self.session.execute(
            select(Project)
            .where(Project.owner_id == owner_id)
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_name(
        self, organization_id: UUID | str, name: str
    ) -> Optional[Project]:
        if isinstance(organization_id, str):
            organization_id = UUID(organization_id)
        result = await self.session.execute(
            select(Project).where(
                Project.organization_id == organization_id, Project.name == name
            )
        )
        return result.scalar_one_or_none()
