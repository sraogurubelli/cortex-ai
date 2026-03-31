"""
Entity base classes for the Cortex platform.

Provides the declarative base and abstract entity classes:
- Base: SQLAlchemy declarative base with naming conventions
- MinimalEntity: Abstract base with UUID PK and timestamps
- BaseEntity: Extends MinimalEntity with soft audit fields (created_by, updated_by)

Adapted from synteraiq-engine core_platform/entities/base.py
"""

import uuid
from datetime import datetime
from typing import Union

from sqlalchemy import MetaData, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, declared_attr, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class MinimalEntity(Base):
    """Base class with minimal fields: UUID PK and timestamps."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        return cls.__name__.lower() + "s"


class BaseEntity(MinimalEntity):
    """Extended base with audit fields (created_by, updated_by)."""

    __abstract__ = True

    created_by: Mapped[Union[uuid.UUID, None]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="User ID who created this record (no FK constraint)",
    )
    updated_by: Mapped[Union[uuid.UUID, None]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="User ID who last updated this record (no FK constraint)",
    )
