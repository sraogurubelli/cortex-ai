"""
Conversation Repository

Data access layer for Conversation model (AI chat sessions).
"""

from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Conversation
from cortex.platform.database.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for Conversation operations."""

    def __init__(self, session: AsyncSession):
        """Initialize conversation repository."""
        super().__init__(Conversation, session)

    async def find_by_thread_id(self, thread_id: str) -> Optional[Conversation]:
        """
        Find conversation by LangGraph thread ID.

        Args:
            thread_id: LangGraph thread ID

        Returns:
            Conversation instance or None
        """
        result = await self.session.execute(
            select(Conversation).where(Conversation.thread_id == thread_id)
        )
        return result.scalar_one_or_none()

    async def find_by_project(
        self,
        project_id: int,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "updated_at",
        desc_order: bool = True,
    ) -> list[Conversation]:
        """
        List conversations in a project.

        Args:
            project_id: Project ID
            limit: Maximum number of results
            offset: Offset for pagination
            order_by: Column to order by (created_at, updated_at)
            desc_order: Whether to order descending

        Returns:
            List of conversations
        """
        query = select(Conversation).where(Conversation.project_id == project_id)

        # Order by specified column
        if order_by == "created_at":
            order_column = Conversation.created_at
        else:
            order_column = Conversation.updated_at

        if desc_order:
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(order_column)

        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_project(self, project_id: int) -> int:
        """
        Count conversations in a project.

        Args:
            project_id: Project ID

        Returns:
            Number of conversations
        """
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(Conversation.id)).where(
                Conversation.project_id == project_id
            )
        )
        return result.scalar_one()

    async def update_title(
        self, conversation_id: int, title: str
    ) -> Optional[Conversation]:
        """
        Update conversation title.

        Args:
            conversation_id: Conversation ID
            title: New title

        Returns:
            Updated conversation or None
        """
        conversation = await self.find_by_id(conversation_id)
        if not conversation:
            return None

        conversation.title = title
        return await self.update(conversation)

    async def search(
        self,
        project_id: int,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Conversation], int]:
        """Search conversations by title using ILIKE.

        Returns (matching_conversations, total_count).
        """
        from sqlalchemy import func as sa_func

        pattern = f"%{query}%"

        base = select(Conversation).where(
            Conversation.project_id == project_id,
            Conversation.title.ilike(pattern),
        )
        count_q = select(sa_func.count(Conversation.id)).where(
            Conversation.project_id == project_id,
            Conversation.title.ilike(pattern),
        )

        total = (await self.session.execute(count_q)).scalar_one()

        results = await self.session.execute(
            base.order_by(desc(Conversation.updated_at))
            .limit(limit)
            .offset(offset)
        )
        return list(results.scalars().all()), total

    async def find_by_project_and_principal(
        self,
        project_id: int,
        principal_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Conversation]:
        """
        List conversations for a specific principal in a project.

        Args:
            project_id: Project ID
            principal_id: Principal ID
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of conversations
        """
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.project_id == project_id,
                Conversation.principal_id == principal_id,
            )
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
