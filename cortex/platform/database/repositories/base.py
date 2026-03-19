"""
Base Repository

Provides common CRUD operations for all repositories.
"""

from typing import Generic, TypeVar, Type, List, Optional

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base repository with common CRUD operations.

    All model-specific repositories should inherit from this class.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session

    async def create(self, entity: ModelType) -> ModelType:
        """
        Create a new entity.

        Args:
            entity: Entity instance to create

        Returns:
            Created entity with populated ID
        """
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def find_by_id(self, entity_id: int) -> Optional[ModelType]:
        """
        Find entity by ID.

        Args:
            entity_id: Entity ID

        Returns:
            Entity instance or None
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def find_by_uid(self, uid: str) -> Optional[ModelType]:
        """
        Find entity by UID (unique identifier).

        Args:
            uid: Unique identifier

        Returns:
            Entity instance or None
        """
        result = await self.session.execute(
            select(self.model).where(self.model.uid == uid)
        )
        return result.scalar_one_or_none()

    async def find_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        desc: bool = True,
    ) -> List[ModelType]:
        """
        Find all entities with pagination.

        Args:
            limit: Maximum number of entities to return
            offset: Number of entities to skip
            order_by: Field to order by
            desc: Sort descending if True

        Returns:
            List of entities
        """
        query = select(self.model)

        # Order by
        if hasattr(self.model, order_by):
            order_column = getattr(self.model, order_by)
            if desc:
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column)

        # Pagination
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self) -> int:
        """
        Count total number of entities.

        Returns:
            Total count
        """
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()

    async def update(self, entity: ModelType) -> ModelType:
        """
        Update an entity.

        Args:
            entity: Entity instance with updated fields

        Returns:
            Updated entity
        """
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity_id: int) -> bool:
        """
        Delete entity by ID.

        Args:
            entity_id: Entity ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            delete(self.model).where(self.model.id == entity_id)
        )
        return result.rowcount > 0

    async def delete_by_uid(self, uid: str) -> bool:
        """
        Delete entity by UID.

        Args:
            uid: Unique identifier

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            delete(self.model).where(self.model.uid == uid)
        )
        return result.rowcount > 0

    async def exists(self, entity_id: int) -> bool:
        """
        Check if entity exists by ID.

        Args:
            entity_id: Entity ID

        Returns:
            True if exists, False otherwise
        """
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(self.model.id == entity_id)
        )
        return result.scalar_one() > 0

    async def exists_by_uid(self, uid: str) -> bool:
        """
        Check if entity exists by UID.

        Args:
            uid: Unique identifier

        Returns:
            True if exists, False otherwise
        """
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(self.model.uid == uid)
        )
        return result.scalar_one() > 0
