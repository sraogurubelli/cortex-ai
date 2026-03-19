"""
Database Session Management

SQLAlchemy session management with async support.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from cortex.platform.config import get_settings


class DatabaseManager:
    """Database connection manager."""

    def __init__(self, database_url: str | None = None):
        """
        Initialize database manager.

        Args:
            database_url: PostgreSQL connection URL (overrides settings)
        """
        settings = get_settings()
        self.database_url = database_url or settings.database_url

        # Convert postgresql:// to postgresql+asyncpg://
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://"
            )

        # Create async engine
        self.engine = create_async_engine(
            self.database_url,
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            poolclass=NullPool if "sqlite" in self.database_url else None,
        )

        # Create session factory
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get async database session.

        Usage:
            async with db_manager.session() as session:
                result = await session.execute(...)
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self):
        """Close database engine."""
        await self.engine.dispose()


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """
    Get global database manager instance (singleton).

    Returns:
        DatabaseManager instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    Usage:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    db_manager = get_db_manager()
    async with db_manager.session() as session:
        yield session


async def init_db() -> None:
    """
    Initialize database (create tables if they don't exist).

    Called on application startup.
    """
    from cortex.platform.database.models import Base

    db_manager = get_db_manager()

    async with db_manager.engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.

    Called on application shutdown.
    """
    global _db_manager
    if _db_manager is not None:
        await _db_manager.close()
        _db_manager = None
