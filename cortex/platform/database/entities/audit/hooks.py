"""
Audit hooks for SQLAlchemy session events.

Auto-populates created_by / updated_by from the current_actor_id context
variable on every session flush.

Adapted from synteraiq-engine core_platform/entities/audit/hooks.py
"""

from sqlalchemy.orm import Session
from sqlalchemy import inspect
from sqlalchemy.event import listens_for

from .context import current_actor_id


@listens_for(Session, "before_flush")
def apply_audit_columns(session, flush_context, instances) -> None:
    """Populate created_by / updated_by from contextvar if present."""
    actor = current_actor_id.get()
    if actor is None:
        return

    for obj in session.new:
        if hasattr(obj, "created_by") and getattr(obj, "created_by") is None:
            setattr(obj, "created_by", actor)
        if hasattr(obj, "updated_by"):
            setattr(obj, "updated_by", actor)

    for obj in session.dirty:
        state = inspect(obj)
        if state.attrs and hasattr(obj, "updated_by"):
            setattr(obj, "updated_by", actor)
