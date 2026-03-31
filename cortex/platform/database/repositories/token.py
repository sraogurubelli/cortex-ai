"""Token Repository"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Token, TokenType
from cortex.platform.database.repositories.base import BaseRepository


class TokenRepository(BaseRepository[Token]):
    """Repository for Token operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Token, session)

    async def find_by_principal(
        self, principal_id: UUID | str, token_type: Optional[TokenType] = None
    ) -> List[Token]:
        if isinstance(principal_id, str):
            principal_id = UUID(principal_id)
        query = select(Token).where(Token.principal_id == principal_id)
        if token_type:
            query = query.where(Token.token_type == token_type)
        query = query.order_by(Token.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_by_hash(self, token_hash: str) -> Optional[Token]:
        result = await self.session.execute(
            select(Token).where(Token.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def find_by_type(
        self, token_type: TokenType, limit: int = 100, offset: int = 0
    ) -> List[Token]:
        result = await self.session.execute(
            select(Token)
            .where(Token.token_type == token_type)
            .order_by(Token.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_expired(self, limit: int = 100) -> List[Token]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Token)
            .where(Token.expires_at.isnot(None), Token.expires_at < now)
            .order_by(Token.expires_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_last_used(self, token_id: UUID | str) -> bool:
        if isinstance(token_id, str):
            token_id = UUID(token_id)
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(Token).where(Token.id == token_id).values(last_used_at=now)
        )
        return result.rowcount > 0

    async def delete_expired(self) -> int:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            delete(Token).where(Token.expires_at.isnot(None), Token.expires_at < now)
        )
        return result.rowcount
