"""
Model Provider Configuration API

Endpoints for managing LLM providers and querying available models.
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Base, Principal, get_db
from cortex.orchestration.models.capabilities import (
    ModelCapabilities,
    detect_capabilities,
    list_known_models,
)
from cortex.orchestration.models.health import check_provider_health, HealthStatus
from cortex.orchestration.models.provider_registry import (
    ProviderConfig,
    provider_registry,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["models"])


# ---------------------------------------------------------------------------
# DB Model for persisted provider configs
# ---------------------------------------------------------------------------


class ProviderRecord(Base):
    __tablename__ = "model_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False, unique=True)
    provider_type = Column(String(50), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    base_url = Column(String(1024), nullable=True)
    models_json = Column(Text, nullable=True)
    priority = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    max_retries = Column(Integer, default=3)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ModelInfo(BaseModel):
    name: str
    provider: str
    supports_tools: bool = False
    supports_vision: bool = False
    supports_streaming: bool = True
    supports_json_mode: bool = False
    supports_reasoning: bool = False
    context_window: int = 4096
    max_output_tokens: int = 4096
    tags: list[str] = []


class ProviderInfo(BaseModel):
    uid: str
    name: str
    provider_type: str
    base_url: str = ""
    models: list[str] = []
    priority: int = 0
    enabled: bool = True
    health_status: str = "unknown"
    health_latency_ms: float = 0.0


class ProviderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    provider_type: str = Field(..., min_length=1)
    api_key: str = ""
    base_url: str = ""
    models: list[str] = Field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    max_retries: int = 3
    metadata: dict = Field(default_factory=dict)


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: Optional[list[str]] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    max_retries: Optional[int] = None
    metadata: Optional[dict] = None


class ModelTestRequest(BaseModel):
    model: str = "gpt-4o"
    prompt: str = "Say hello in one sentence."


class ModelTestResponse(BaseModel):
    success: bool
    response: str = ""
    error: str = ""
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/models", response_model=list[ModelInfo])
async def list_models(
    principal: Principal = Depends(require_authentication),
):
    """List all known models with their capabilities."""
    models = list_known_models()
    return [
        ModelInfo(
            name=m.model_name,
            provider=m.provider,
            supports_tools=m.supports_tools,
            supports_vision=m.supports_vision,
            supports_streaming=m.supports_streaming,
            supports_json_mode=m.supports_json_mode,
            supports_reasoning=m.supports_reasoning,
            context_window=m.context_window,
            max_output_tokens=m.max_output_tokens,
            tags=m.tags,
        )
        for m in models
    ]


@router.get("/models/providers", response_model=list[ProviderInfo])
async def list_providers(
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    """List configured providers with health status."""
    result = await db.execute(
        select(ProviderRecord).order_by(ProviderRecord.priority)
    )
    providers = result.scalars().all()

    infos: list[ProviderInfo] = []
    for p in providers:
        health = await check_provider_health(
            provider=p.provider_type,
            api_key=p.api_key_encrypted or "",
            base_url=p.base_url or "",
        )
        infos.append(ProviderInfo(
            uid=p.uid,
            name=p.name,
            provider_type=p.provider_type,
            base_url=p.base_url or "",
            models=json.loads(p.models_json) if p.models_json else [],
            priority=p.priority or 0,
            enabled=p.enabled if p.enabled is not None else True,
            health_status=health.status.value,
            health_latency_ms=health.latency_ms,
        ))
    return infos


@router.post("/models/providers", response_model=ProviderInfo, status_code=201)
async def create_provider(
    req: ProviderCreateRequest,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    provider = ProviderRecord(
        uid=str(uuid.uuid4()),
        name=req.name,
        provider_type=req.provider_type,
        api_key_encrypted=req.api_key,
        base_url=req.base_url,
        models_json=json.dumps(req.models),
        priority=req.priority,
        enabled=req.enabled,
        max_retries=req.max_retries,
        metadata_json=json.dumps(req.metadata),
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    provider_registry.register(ProviderConfig(
        name=req.name,
        provider_type=req.provider_type,
        api_key=req.api_key,
        base_url=req.base_url,
        models=req.models,
        priority=req.priority,
        enabled=req.enabled,
    ))

    return ProviderInfo(
        uid=provider.uid,
        name=provider.name,
        provider_type=provider.provider_type,
        base_url=provider.base_url or "",
        models=req.models,
        priority=provider.priority or 0,
        enabled=provider.enabled if provider.enabled is not None else True,
        health_status="unknown",
    )


@router.put("/models/providers/{provider_uid}", response_model=ProviderInfo)
async def update_provider(
    provider_uid: str,
    req: ProviderUpdateRequest,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProviderRecord).where(ProviderRecord.uid == provider_uid)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if req.name is not None:
        provider.name = req.name
    if req.api_key is not None:
        provider.api_key_encrypted = req.api_key
    if req.base_url is not None:
        provider.base_url = req.base_url
    if req.models is not None:
        provider.models_json = json.dumps(req.models)
    if req.priority is not None:
        provider.priority = req.priority
    if req.enabled is not None:
        provider.enabled = req.enabled
    if req.max_retries is not None:
        provider.max_retries = req.max_retries
    if req.metadata is not None:
        provider.metadata_json = json.dumps(req.metadata)

    await db.commit()
    await db.refresh(provider)

    return ProviderInfo(
        uid=provider.uid,
        name=provider.name,
        provider_type=provider.provider_type,
        base_url=provider.base_url or "",
        models=json.loads(provider.models_json) if provider.models_json else [],
        priority=provider.priority or 0,
        enabled=provider.enabled if provider.enabled is not None else True,
        health_status="unknown",
    )


@router.delete("/models/providers/{provider_uid}", status_code=204)
async def delete_provider(
    provider_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProviderRecord).where(ProviderRecord.uid == provider_uid)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    provider_registry.remove(provider.name)
    await db.delete(provider)
    await db.commit()


@router.post("/models/test", response_model=ModelTestResponse)
async def test_model(
    req: ModelTestRequest,
    principal: Principal = Depends(require_authentication),
):
    """Send a test prompt to a model and return the response."""
    import time

    start = time.monotonic()
    try:
        from cortex.orchestration.llm import LLMClient
        from cortex.orchestration.config import ModelConfig

        client = LLMClient(ModelConfig(model=req.model))
        from langchain_core.messages import HumanMessage
        result = await client.ainvoke([HumanMessage(content=req.prompt)])
        latency = (time.monotonic() - start) * 1000

        return ModelTestResponse(
            success=True,
            response=str(result.content),
            latency_ms=latency,
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ModelTestResponse(
            success=False,
            error=str(e),
            latency_ms=latency,
        )
