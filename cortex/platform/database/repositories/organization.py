"""
Organization Repository

Data access layer for Organization model.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Organization
from cortex.platform.database.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Repository for Organization operations."""

    def __init__(self, session: AsyncSession):
        """Initialize organization repository."""
        super().__init__(Organization, session)

    async def find_by_account(
        self, account_id: int, limit: int = 100, offset: int = 0
    ) -> List[Organization]:
        """
        Find all organizations in an account.

        Args:
            account_id: Account ID
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of organizations
        """
        result = await self.session.execute(
            select(Organization)
            .where(Organization.account_id == account_id)
            .order_by(Organization.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_by_owner(self, owner_id: int) -> List[Organization]:
        """
        Find all organizations owned by a principal.

        Args:
            owner_id: Principal ID

        Returns:
            List of organizations
        """
        result = await self.session.execute(
            select(Organization)
            .where(Organization.owner_id == owner_id)
            .order_by(Organization.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_by_name(self, account_id: int, name: str) -> Optional[Organization]:
        """
        Find organization by name within an account.

        Args:
            account_id: Account ID
            name: Organization name

        Returns:
            Organization instance or None
        """
        result = await self.session.execute(
            select(Organization).where(
                Organization.account_id == account_id, Organization.name == name
            )
        )
        return result.scalar_one_or_none()
