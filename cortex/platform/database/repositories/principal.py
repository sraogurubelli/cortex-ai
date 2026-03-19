"""
Principal Repository

Data access layer for Principal model.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Principal, PrincipalType
from cortex.platform.database.repositories.base import BaseRepository


class PrincipalRepository(BaseRepository[Principal]):
    """Repository for Principal operations."""

    def __init__(self, session: AsyncSession):
        """Initialize principal repository."""
        super().__init__(Principal, session)

    async def find_by_email(self, email: str) -> Optional[Principal]:
        """
        Find principal by email.

        Args:
            email: Email address

        Returns:
            Principal instance or None
        """
        result = await self.session.execute(
            select(Principal).where(Principal.email == email)
        )
        return result.scalar_one_or_none()

    async def find_by_type(
        self, principal_type: PrincipalType, limit: int = 100, offset: int = 0
    ) -> List[Principal]:
        """
        Find principals by type.

        Args:
            principal_type: Principal type (USER or SERVICE_ACCOUNT)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of principals
        """
        result = await self.session.execute(
            select(Principal)
            .where(Principal.principal_type == principal_type)
            .order_by(Principal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_admins(self, limit: int = 100, offset: int = 0) -> List[Principal]:
        """
        Find all system administrators.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of admin principals
        """
        result = await self.session.execute(
            select(Principal)
            .where(Principal.admin == True)
            .order_by(Principal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_blocked(self, limit: int = 100, offset: int = 0) -> List[Principal]:
        """
        Find all blocked principals.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of blocked principals
        """
        result = await self.session.execute(
            select(Principal)
            .where(Principal.blocked == True)
            .order_by(Principal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def is_admin(self, principal_id: int) -> bool:
        """
        Check if principal is a system administrator.

        Args:
            principal_id: Principal ID

        Returns:
            True if admin, False otherwise
        """
        result = await self.session.execute(
            select(Principal.admin).where(Principal.id == principal_id)
        )
        admin_status = result.scalar_one_or_none()
        return admin_status is True if admin_status is not None else False

    async def is_blocked(self, principal_id: int) -> bool:
        """
        Check if principal is blocked.

        Args:
            principal_id: Principal ID

        Returns:
            True if blocked, False otherwise
        """
        result = await self.session.execute(
            select(Principal.blocked).where(Principal.id == principal_id)
        )
        blocked_status = result.scalar_one_or_none()
        return blocked_status is True if blocked_status is not None else False
