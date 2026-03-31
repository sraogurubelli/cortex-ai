"""
AuditEvent entity -- universal event store for event-sourcing audit.

Immutable, append-only event log. All system changes are recorded here
as structured events with payload and metadata.

Adapted from synteraiq-engine core_platform/entities/audit/audit_event.py
Key change: uses the shared Base (via MinimalEntity) instead of a separate
declarative_base(), so it's included in the main Alembic migration.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, String, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from ..base import Base


class AuditEvent(Base):
    """
    Universal audit event -- source of truth for all system changes.

    Event-sourcing pattern:
    - Immutable: events are never updated or deleted
    - Append-only: new events are always added
    - Source of truth: current state can be derived from events
    - Replay: can rebuild any entity state from its event stream
    """

    __tablename__ = "audit_events"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    event_type = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(PG_UUID(as_uuid=True), nullable=False)

    account_id = Column(PG_UUID(as_uuid=True), nullable=False)
    actor_id = Column(PG_UUID(as_uuid=True), nullable=True)

    entity_audit_id = Column(
        PG_UUID(as_uuid=True),
        nullable=True,
        comment="Optional link to entity-specific audit table row",
    )

    payload = Column(JSONB, nullable=False)
    event_metadata = Column("metadata", JSONB, nullable=True)

    timestamp = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    stream_id = Column(String(100), nullable=False)

    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_account", "account_id"),
        Index("ix_audit_events_actor", "actor_id"),
        Index("ix_audit_events_type", "event_type"),
        Index("ix_audit_events_timestamp", "timestamp"),
        Index("ix_audit_events_stream", "stream_id"),
        {"comment": "Universal event store for event-sourcing audit"},
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent(id={self.id}, event_type='{self.event_type}', "
            f"entity_type='{self.entity_type}', entity_id={self.entity_id})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id),
            "account_id": str(self.account_id),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "entity_audit_id": str(self.entity_audit_id) if self.entity_audit_id else None,
            "payload": self.payload,
            "metadata": self.event_metadata,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "stream_id": self.stream_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEvent":
        entity_audit_id = data.get("entity_audit_id")
        if entity_audit_id and isinstance(entity_audit_id, str):
            entity_audit_id = UUID(entity_audit_id)

        return cls(
            event_type=data["event_type"],
            entity_type=data["entity_type"],
            entity_id=UUID(data["entity_id"]) if isinstance(data["entity_id"], str) else data["entity_id"],
            account_id=UUID(data["account_id"]) if isinstance(data["account_id"], str) else data["account_id"],
            actor_id=UUID(data["actor_id"]) if data.get("actor_id") and isinstance(data["actor_id"], str) else data.get("actor_id"),
            entity_audit_id=entity_audit_id,
            payload=data["payload"],
            event_metadata=data.get("metadata"),
            stream_id=data["stream_id"],
        )
