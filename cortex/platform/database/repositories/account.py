"""Account Repository"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Account, AccountStatus, SubscriptionTier
from cortex.platform.database.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    """Repository for Account operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Account, session)

    async def find_by_email(self, billing_email: str) -> Optional[Account]:
        result = await self.session.execute(
            select(Account).where(Account.billing_email == billing_email)
        )
        return result.scalar_one_or_none()

    async def find_by_owner(self, owner_id: UUID | str) -> List[Account]:
        if isinstance(owner_id, str):
            owner_id = UUID(owner_id)
        result = await self.session.execute(
            select(Account)
            .where(Account.owner_id == owner_id)
            .order_by(Account.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_status(
        self, status: AccountStatus, limit: int = 100, offset: int = 0
    ) -> List[Account]:
        result = await self.session.execute(
            select(Account)
            .where(Account.status == status)
            .order_by(Account.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_by_tier(
        self, tier: SubscriptionTier, limit: int = 100, offset: int = 0
    ) -> List[Account]:
        result = await self.session.execute(
            select(Account)
            .where(Account.subscription_tier == tier)
            .order_by(Account.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_expiring_trials(self, limit: int = 100) -> List[Account]:
        result = await self.session.execute(
            select(Account)
            .where(Account.status == AccountStatus.TRIAL, Account.trial_ends_at.isnot(None))
            .order_by(Account.trial_ends_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
