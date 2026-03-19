"""
Token Repository

Data access layer for Token model.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.platform.database.models import Token, TokenType
from cortex.platform.database.repositories.base import BaseRepository


class TokenRepository(BaseRepository[Token]):
    """Repository for Token operations."""

    def __init__(self, session: AsyncSession):
        """Initialize token repository."""
        super().__init__(Token, session)

    async def find_by_principal(
        self, principal_id: int, token_type: Optional[TokenType] = None
    ) -> List[Token]:
        """
        Find all tokens for a principal.

        Args:
            principal_id: Principal ID
            token_type: Optional token type filter

        Returns:
            List of tokens
        """
        query = select(Token).where(Token.principal_id == principal_id)

        if token_type:
            query = query.where(Token.token_type == token_type)

        query = query.order_by(Token.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_by_hash(self, token_hash: str) -> Optional[Token]:
        """
        Find token by hash.

        Args:
            token_hash: Hashed token value

        Returns:
            Token instance or None
        """
        result = await self.session.execute(
            select(Token).where(Token.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def find_by_type(
        self, token_type: TokenType, limit: int = 100, offset: int = 0
    ) -> List[Token]:
        """
        Find tokens by type.

        Args:
            token_type: Token type
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of tokens
        """
        result = await self.session.execute(
            select(Token)
            .where(Token.token_type == token_type)
            .order_by(Token.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def find_expired(self, limit: int = 100) -> List[Token]:
        """
        Find expired tokens.

        Args:
            limit: Maximum number of results

        Returns:
            List of expired tokens
        """
        now = datetime.now()
        result = await self.session.execute(
            select(Token)
            .where(
                Token.expires_at.isnot(None),
                Token.expires_at < now,
            )
            .order_by(Token.expires_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_last_used(self, token_id: int) -> bool:
        """
        Update token's last_used_at timestamp.

        Args:
            token_id: Token ID

        Returns:
            True if updated, False if not found
        """
        now = datetime.now()
        result = await self.session.execute(
            update(Token)
            .where(Token.id == token_id)
            .values(last_used_at=now)
        )
        return result.rowcount > 0

    async def delete_expired(self) -> int:
        """
        Delete all expired tokens.

        Returns:
            Number of tokens deleted
        """
        now = datetime.now()
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(Token).where(
                Token.expires_at.isnot(None),
                Token.expires_at < now,
            )
        )
        return result.rowcount
