"""
Base Repository

Provides common CRUD operations for all repositories.
All entity IDs are UUID.
"""

from typing import Generic, TypeVar, Type, List, Optional, Any
from uuid import UUID

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with common CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def create(self, entity: ModelType) -> ModelType:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def find_by_id(self, entity_id: UUID | str) -> Optional[ModelType]:
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)
        result = await self.session.execute(
            select(self.model).where(self.model.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def find_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        desc: bool = True,
    ) -> List[ModelType]:
        query = select(self.model)
        if hasattr(self.model, order_by):
            order_column = getattr(self.model, order_by)
            if desc:
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column)
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()

    async def update(self, entity: ModelType) -> ModelType:
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity_id: UUID | str) -> bool:
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)
        result = await self.session.execute(
            delete(self.model).where(self.model.id == entity_id)
        )
        return result.rowcount > 0

    async def exists(self, entity_id: UUID | str) -> bool:
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(self.model.id == entity_id)
        )
        return result.scalar_one() > 0
