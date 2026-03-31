"""Membership Repository"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Membership, MembershipRole
from cortex.platform.database.repositories.base import BaseRepository


class MembershipRepository(BaseRepository[Membership]):
    """Repository for Membership operations (RBAC)."""

    def __init__(self, session: AsyncSession):
        super().__init__(Membership, session)

    async def find_by_principal(
        self, principal_id: UUID | str, resource_type: Optional[str] = None
    ) -> List[Membership]:
        if isinstance(principal_id, str):
            principal_id = UUID(principal_id)
        query = select(Membership).where(Membership.principal_id == principal_id)
        if resource_type:
            query = query.where(Membership.resource_type == resource_type)
        query = query.order_by(Membership.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_by_resource(
        self, resource_type: str, resource_id: str
    ) -> List[Membership]:
        result = await self.session.execute(
            select(Membership)
            .where(Membership.resource_type == resource_type, Membership.resource_id == resource_id)
            .order_by(Membership.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_membership(
        self, principal_id: UUID | str, resource_type: str, resource_id: str
    ) -> Optional[Membership]:
        if isinstance(principal_id, str):
            principal_id = UUID(principal_id)
        result = await self.session.execute(
            select(Membership).where(
                Membership.principal_id == principal_id,
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_role(
        self, principal_id: UUID | str, resource_type: str, resource_id: str
    ) -> Optional[MembershipRole]:
        if isinstance(principal_id, str):
            principal_id = UUID(principal_id)
        result = await self.session.execute(
            select(Membership.role).where(
                Membership.principal_id == principal_id,
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.scalar_one_or_none()

    async def has_role(
        self, principal_id: UUID | str, resource_type: str, resource_id: str,
        role: MembershipRole,
    ) -> bool:
        actual_role = await self.get_role(principal_id, resource_type, resource_id)
        return actual_role == role

    async def find_by_role(
        self, role: MembershipRole, resource_type: Optional[str] = None
    ) -> List[Membership]:
        query = select(Membership).where(Membership.role == role)
        if resource_type:
            query = query.where(Membership.resource_type == resource_type)
        query = query.order_by(Membership.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_by_resource(self, resource_type: str, resource_id: str) -> int:
        result = await self.session.execute(
            delete(Membership).where(
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.rowcount

    async def delete_membership(
        self, principal_id: UUID | str, resource_type: str, resource_id: str
    ) -> bool:
        if isinstance(principal_id, str):
            principal_id = UUID(principal_id)
        result = await self.session.execute(
            delete(Membership).where(
                Membership.principal_id == principal_id,
                Membership.resource_type == resource_type,
                Membership.resource_id == resource_id,
            )
        )
        return result.rowcount > 0
