"""
Request-scoped context using contextvars.

Stores request-scoped data (tenant_id, project_id, stream_writer, etc.)
that can be accessed anywhere during request processing without explicit
parameter passing.

Ported from ml-infra capabilities/tools/grpc/request_context.py
(Harness-specific auth context removed; replaced with generic cortex fields).

Usage::

    from cortex.orchestration.context import request_context

    # In a route handler:
    with request_context(
        tenant_id=account.uid,
        project_id=project.uid,
        principal_id=principal.uid,
        conversation_id=conversation.uid,
        stream_writer=writer,
    ):
        result = await agent.stream(...)

    # In a tool or middleware:
    from cortex.orchestration.context import get_project_id
    project_id = get_project_id()
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

_tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
_project_id_var: ContextVar[Optional[str]] = ContextVar("project_id", default=None)
_principal_id_var: ContextVar[Optional[str]] = ContextVar("principal_id", default=None)
_conversation_id_var: ContextVar[Optional[str]] = ContextVar("conversation_id", default=None)
_stream_writer_var: ContextVar[Optional[Any]] = ContextVar("stream_writer", default=None)
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_agent_name_var: ContextVar[Optional[str]] = ContextVar("agent_name", default=None)
_model_name_var: ContextVar[Optional[str]] = ContextVar("model_name", default=None)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

def get_tenant_id() -> Optional[str]:
    return _tenant_id_var.get()

def get_project_id() -> Optional[str]:
    return _project_id_var.get()

def get_principal_id() -> Optional[str]:
    return _principal_id_var.get()

def get_conversation_id() -> Optional[str]:
    return _conversation_id_var.get()

def get_stream_writer() -> Optional[Any]:
    return _stream_writer_var.get()

def get_request_id() -> Optional[str]:
    return _request_id_var.get()

def get_agent_name() -> Optional[str]:
    return _agent_name_var.get()

def get_model_name() -> Optional[str]:
    return _model_name_var.get()


# ---------------------------------------------------------------------------
# Setters
# ---------------------------------------------------------------------------

def set_tenant_id(value: str) -> None:
    _tenant_id_var.set(value)

def set_project_id(value: str) -> None:
    _project_id_var.set(value)

def set_principal_id(value: str) -> None:
    _principal_id_var.set(value)

def set_conversation_id(value: str) -> None:
    _conversation_id_var.set(value)

def set_stream_writer(value: Any) -> None:
    _stream_writer_var.set(value)

def set_request_id(value: str) -> None:
    _request_id_var.set(value)

def set_agent_name(value: str) -> None:
    _agent_name_var.set(value)

def set_model_name(value: str) -> None:
    _model_name_var.set(value)


# ---------------------------------------------------------------------------
# Bulk clear
# ---------------------------------------------------------------------------

def clear_request_context() -> None:
    """Reset all context vars to None."""
    _tenant_id_var.set(None)
    _project_id_var.set(None)
    _principal_id_var.set(None)
    _conversation_id_var.set(None)
    _stream_writer_var.set(None)
    _request_id_var.set(None)
    _agent_name_var.set(None)
    _model_name_var.set(None)


# ---------------------------------------------------------------------------
# Context manager for scoped lifecycle
# ---------------------------------------------------------------------------

@contextmanager
def request_context(
    *,
    tenant_id: Optional[str] = None,
    project_id: Optional[str] = None,
    principal_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    stream_writer: Optional[Any] = None,
    request_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
):
    """Context manager that sets request-scoped vars and clears them on exit.

    Example::

        with request_context(tenant_id="acc_123", project_id="prj_456"):
            await agent.run(...)
    """
    tokens = []
    if tenant_id is not None:
        tokens.append(_tenant_id_var.set(tenant_id))
    if project_id is not None:
        tokens.append(_project_id_var.set(project_id))
    if principal_id is not None:
        tokens.append(_principal_id_var.set(principal_id))
    if conversation_id is not None:
        tokens.append(_conversation_id_var.set(conversation_id))
    if stream_writer is not None:
        tokens.append(_stream_writer_var.set(stream_writer))
    if request_id is not None:
        tokens.append(_request_id_var.set(request_id))
    if agent_name is not None:
        tokens.append(_agent_name_var.set(agent_name))
    if model_name is not None:
        tokens.append(_model_name_var.set(model_name))

    try:
        yield
    finally:
        clear_request_context()
