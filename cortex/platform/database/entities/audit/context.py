"""
Audit context variable.

Carries the current actor's user ID through the async request context.
Set by auth middleware, consumed by audit hooks to auto-populate
created_by / updated_by on entity flush.

Adapted from synteraiq-engine core_platform/entities/audit/context.py
"""

from contextvars import ContextVar
from typing import Optional
from uuid import UUID

current_actor_id: ContextVar[Optional[UUID]] = ContextVar(
    "current_actor_id", default=None
)
