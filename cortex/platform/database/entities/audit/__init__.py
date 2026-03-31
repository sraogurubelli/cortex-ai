"""
Audit infrastructure for Cortex AI platform.

Event-sourcing architecture:
- AuditEvent: Universal event store (primary audit mechanism)
- context: ContextVar for current actor ID
- hooks: Session hooks to auto-populate created_by/updated_by

Adapted from synteraiq-engine core_platform/entities/audit/
"""

from .audit_event import AuditEvent
from .context import current_actor_id
from .hooks import apply_audit_columns

__all__ = [
    "AuditEvent",
    "current_actor_id",
    "apply_audit_columns",
]
