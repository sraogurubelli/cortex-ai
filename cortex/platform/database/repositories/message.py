"""
Message Repository

Data access layer for Message model (conversation messages).
"""

from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Message
from cortex.platform.database.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    """Repository for Message operations."""

    def __init__(self, session: AsyncSession):
        """Initialize message repository."""
        super().__init__(Message, session)

    async def find_by_conversation(
        self,
        conversation_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """
        Get messages for a conversation (chronological order).

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of messages in chronological order
        """
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())  # Chronological order
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_conversation(self, conversation_id: int) -> int:
        """
        Count messages in a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Number of messages
        """
        result = await self.session.execute(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation_id
            )
        )
        return result.scalar_one()

    async def create_batch(self, messages: list[Message]) -> list[Message]:
        """
        Bulk insert messages.

        Args:
            messages: List of Message instances

        Returns:
            List of created messages with IDs
        """
        self.session.add_all(messages)
        await self.session.flush()  # Get IDs without committing
        return messages

    async def get_last_message(self, conversation_id: int) -> Optional[Message]:
        """
        Get the most recent message in a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Latest message or None
        """
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def search_content(
        self,
        conversation_id: int,
        query: str,
        limit: int = 50,
    ) -> list[Message]:
        """Search messages by content within a conversation."""
        pattern = f"%{query}%"
        result = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.content.ilike(pattern),
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_after(
        self, conversation_id: int, after_created_at
    ) -> int:
        """Delete all messages created after a given timestamp."""
        from sqlalchemy import delete as sa_delete

        result = await self.session.execute(
            sa_delete(Message).where(
                Message.conversation_id == conversation_id,
                Message.created_at > after_created_at,
            )
        )
        return result.rowcount

    async def find_by_role(
        self,
        conversation_id: int,
        role: str,
        limit: int = 100,
    ) -> list[Message]:
        """
        Get messages by role in a conversation.

        Args:
            conversation_id: Conversation ID
            role: Message role ('user', 'assistant', 'system', 'tool')
            limit: Maximum number of results

        Returns:
            List of messages with specified role
        """
        result = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == role,
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
