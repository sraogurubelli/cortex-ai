"""
Prompt Management API Routes

Exposes the PromptRegistry for viewing, editing, rendering, and
testing prompt templates via the REST API.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Principal
from cortex.prompts import PromptRegistry, list_prompts, register_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["prompts"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class PromptInfo(BaseModel):
    key: str
    template: str


class PromptListResponse(BaseModel):
    prompts: list[PromptInfo]
    total: int


class PromptUpdateRequest(BaseModel):
    template: str = Field(..., min_length=1, max_length=50000)


class PromptRenderRequest(BaseModel):
    template: Optional[str] = Field(
        None, description="Raw Jinja2 template to render (uses this instead of stored template)"
    )
    variables: dict[str, Any] = Field(default_factory=dict)


class PromptRenderResponse(BaseModel):
    rendered: str
    key: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/prompts", response_model=PromptListResponse)
async def get_all_prompts(
    principal: Principal = Depends(require_authentication),
):
    """List all registered prompt templates with their raw Jinja2 source."""
    registry = PromptRegistry.instance()
    keys = list_prompts()

    prompts = []
    for key in keys:
        raw = registry._get_raw(key)
        if raw is not None:
            prompts.append(PromptInfo(key=key, template=raw))

    return PromptListResponse(prompts=prompts, total=len(prompts))


@router.get("/prompts/{prompt_key:path}", response_model=PromptInfo)
async def get_prompt_by_key(
    prompt_key: str,
    principal: Principal = Depends(require_authentication),
):
    """Get a single prompt template by its dotted key."""
    registry = PromptRegistry.instance()
    raw = registry._get_raw(prompt_key)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{prompt_key}' not found",
        )
    return PromptInfo(key=prompt_key, template=raw)


@router.put("/prompts/{prompt_key:path}", response_model=PromptInfo)
async def update_prompt(
    prompt_key: str,
    request: PromptUpdateRequest,
    principal: Principal = Depends(require_authentication),
):
    """Update (or create) a prompt template at runtime.

    Changes persist only for the lifetime of the running server.
    For permanent changes, update the corresponding ``*_prompts.py`` file.
    """
    register_prompt(prompt_key, request.template)
    logger.info("Prompt '%s' updated by %s", prompt_key, principal.uid)
    return PromptInfo(key=prompt_key, template=request.template)


@router.post("/prompts/{prompt_key:path}/render", response_model=PromptRenderResponse)
async def render_prompt(
    prompt_key: str,
    request: PromptRenderRequest,
    principal: Principal = Depends(require_authentication),
):
    """Render a prompt with the given variables.

    If ``request.template`` is provided, it renders that string directly
    (useful for previewing edits). Otherwise it renders the stored template.
    """
    registry = PromptRegistry.instance()

    if request.template is not None:
        template_str = request.template
    else:
        template_str = registry._get_raw(prompt_key)
        if template_str is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt '{prompt_key}' not found",
            )

    try:
        rendered = registry._render(template_str, request.variables)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template rendering failed: {exc}",
        )

    return PromptRenderResponse(rendered=rendered, key=prompt_key)
