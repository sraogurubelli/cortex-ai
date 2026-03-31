"""Organization Repository"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Organization
from cortex.platform.database.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Repository for Organization operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Organization, session)

    async def find_by_account(
        self, account_id: UUID | str, limit: int = 100, offset: int = 0
    ) -> List[Organization]:
        if isinstance(account_id, str):
            account_id = UUID(account_id)
        result = await self.session.execute(
            select(Organization)
            .where(Organization.account_id == account_id)
            .order_by(Organization.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_by_owner(self, owner_id: UUID | str) -> List[Organization]:
        if isinstance(owner_id, str):
            owner_id = UUID(owner_id)
        result = await self.session.execute(
            select(Organization)
            .where(Organization.owner_id == owner_id)
            .order_by(Organization.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_name(self, account_id: UUID | str, name: str) -> Optional[Organization]:
        if isinstance(account_id, str):
            account_id = UUID(account_id)
        result = await self.session.execute(
            select(Organization).where(
                Organization.account_id == account_id, Organization.name == name
            )
        )
        return result.scalar_one_or_none()
