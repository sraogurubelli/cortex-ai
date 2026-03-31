"""Principal Repository"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Principal, PrincipalType
from cortex.platform.database.repositories.base import BaseRepository


class PrincipalRepository(BaseRepository[Principal]):
    """Repository for Principal operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Principal, session)

    async def find_by_email(self, email: str) -> Optional[Principal]:
        result = await self.session.execute(
            select(Principal).where(Principal.email == email)
        )
        return result.scalar_one_or_none()

    async def find_by_google_id(self, google_id: str) -> Optional[Principal]:
        result = await self.session.execute(
            select(Principal).where(Principal.google_id == google_id)
        )
        return result.scalar_one_or_none()

    async def find_by_type(
        self, principal_type: PrincipalType, limit: int = 100, offset: int = 0
    ) -> List[Principal]:
        result = await self.session.execute(
            select(Principal)
            .where(Principal.principal_type == principal_type)
            .order_by(Principal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_admins(self, limit: int = 100, offset: int = 0) -> List[Principal]:
        result = await self.session.execute(
            select(Principal)
            .where(Principal.admin == True)
            .order_by(Principal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def is_admin(self, principal_id: UUID | str) -> bool:
        if isinstance(principal_id, str):
            principal_id = UUID(principal_id)
        result = await self.session.execute(
            select(Principal.admin).where(Principal.id == principal_id)
        )
        admin_status = result.scalar_one_or_none()
        return admin_status is True if admin_status is not None else False
