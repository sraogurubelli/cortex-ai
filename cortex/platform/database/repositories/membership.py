"""
Membership Repository

Data access layer for Membership model (RBAC).
"""

from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Membership, Role
from cortex.platform.database.repositories.base import BaseRepository


class MembershipRepository(BaseRepository[Membership]):
    """Repository for Membership operations (RBAC)."""

    def __init__(self, session: AsyncSession):
        """Initialize membership repository."""
        super().__init__(Membership, session)

    async def find_by_principal(
        self, principal_id: int, resource_type: Optional[str] = None
    ) -> List[Membership]:
        """
        Find all memberships for a principal.

        Args:
            principal_id: Principal ID
            resource_type: Optional resource type filter

        Returns:
            List of memberships
        """
        query = select(Membership).where(Membership.principal_id == principal_id)

        if resource_type:
            query = query.where(Membership.resource_type == resource_type)

        query = query.order_by(Membership.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_by_resource(
        self, resource_type: str, resource_id: str
    ) -> List[Membership]:
        """
        Find all memberships for a resource.

        Args:
            resource_type: Resource type (e.g., "account", "organization", "project")
            resource_id: Resource ID

        Returns:
            List of memberships
        """
        result = await self.session.execute(
            select(Membership)
            .where(
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
            .order_by(Membership.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_membership(
        self, principal_id: int, resource_type: str, resource_id: str
    ) -> Optional[Membership]:
        """
        Find specific membership.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            Membership instance or None
        """
        result = await self.session.execute(
            select(Membership).where(
                Membership.principal_id == principal_id,
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_role(
        self, principal_id: int, resource_type: str, resource_id: str
    ) -> Optional[Role]:
        """
        Get principal's role for a resource.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            Role or None if no membership exists
        """
        result = await self.session.execute(
            select(Membership.role).where(
                Membership.principal_id == principal_id,
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.scalar_one_or_none()

    async def has_role(
        self,
        principal_id: int,
        resource_type: str,
        resource_id: str,
        role: Role,
    ) -> bool:
        """
        Check if principal has a specific role on a resource.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID
            role: Role to check

        Returns:
            True if principal has the role, False otherwise
        """
        actual_role = await self.get_role(principal_id, resource_type, resource_id)
        return actual_role == role

    async def find_by_role(
        self, role: Role, resource_type: Optional[str] = None
    ) -> List[Membership]:
        """
        Find all memberships with a specific role.

        Args:
            role: Role to filter by
            resource_type: Optional resource type filter

        Returns:
            List of memberships
        """
        query = select(Membership).where(Membership.role == role)

        if resource_type:
            query = query.where(Membership.resource_type == resource_type)

        query = query.order_by(Membership.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_by_resource(self, resource_type: str, resource_id: str) -> int:
        """
        Delete all memberships for a resource.

        Useful when deleting a resource.

        Args:
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            Number of memberships deleted
        """
        result = await self.session.execute(
            delete(Membership).where(
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.rowcount

    async def delete_membership(
        self, principal_id: int, resource_type: str, resource_id: str
    ) -> bool:
        """
        Delete a specific membership.

        Args:
            principal_id: Principal ID
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            delete(Membership).where(
                Membership.principal_id == principal_id,
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.rowcount > 0
