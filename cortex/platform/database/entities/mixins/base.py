"""
Base mixins for entity scoping and lifecycle management.

Adapted from synteraiq-engine core_platform/entities/mixins/base.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID as UUID_TYPE

from sqlalchemy import Column, ForeignKey, String, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property


class TenantScopedMixin:
    """Adds tenant scoping for multi-tenant entities (Account boundary)."""

    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant/Account owner",
    )


class SoftDeleteMixin:
    """
    Soft delete with tombstone pattern.
    Tracks deletion timestamp, user, and reason.
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Soft delete timestamp",
    )

    deleted_by: Mapped[Optional[UUID_TYPE]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who deleted this record",
    )

    delete_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Reason for deletion",
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @hybrid_property
    def is_active_record(self) -> bool:
        return self.deleted_at is None

    def soft_delete(
        self,
        user_id: Optional[UUID_TYPE] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.deleted_at = datetime.now(timezone.utc)
        self.deleted_by = user_id
        if reason:
            self.delete_reason = reason[:500]

    def restore(self, user_id: Optional[UUID_TYPE] = None) -> None:
        self.deleted_at = None
        self.deleted_by = None
        self.delete_reason = None

        if hasattr(self, "updated_by"):
            self.updated_by = user_id
        if hasattr(self, "updated_at"):
            self.updated_at = datetime.now(timezone.utc)


class StandardEntityMixin(TenantScopedMixin, SoftDeleteMixin):
    """
    For account-scoped entities with soft delete.
    Combine with BaseEntity for: id, timestamps, created_by, updated_by,
    account_id, deleted_at/deleted_by/delete_reason.
    """

    pass
