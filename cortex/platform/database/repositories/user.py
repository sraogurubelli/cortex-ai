"""User Repository"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.entities.core.user import User
from cortex.platform.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User (business profile) operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def find_by_principal_id(self, principal_id: UUID | str) -> Optional[User]:
        if isinstance(principal_id, str):
            principal_id = UUID(principal_id)
        result = await self.session.execute(
            select(User).where(User.principal_id == principal_id)
        )
        return result.scalar_one_or_none()

    async def find_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
