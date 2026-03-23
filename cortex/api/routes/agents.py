"""
Agent Configuration CRUD API

Manages agent definitions (persist in DB) so agents can be configured
via UI rather than code.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Base, Principal, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["agents"])


# ---------------------------------------------------------------------------
# DB Model
# ---------------------------------------------------------------------------


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    project_uid = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    model = Column(String(255), nullable=False, default="gpt-4o")
    tools_json = Column(Text, nullable=True)
    skills_json = Column(Text, nullable=True)
    middleware_json = Column(Text, nullable=True)
    max_iterations = Column(Integer, default=25)
    temperature = Column(Integer, default=0)
    metadata_json = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    system_prompt: str = ""
    model: str = "gpt-4o"
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    middleware: dict = Field(default_factory=dict)
    max_iterations: int = 25
    temperature: float = 0.0
    metadata: dict = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    middleware: Optional[dict] = None
    max_iterations: Optional[int] = None
    temperature: Optional[float] = None
    metadata: Optional[dict] = None
    enabled: Optional[bool] = None


class AgentResponse(BaseModel):
    uid: str
    project_uid: str
    name: str
    description: str
    system_prompt: str
    model: str
    tools: list[str]
    skills: list[str]
    middleware: dict
    max_iterations: int
    temperature: float
    metadata: dict
    enabled: bool
    created_by: str
    created_at: str
    updated_at: str


def _to_response(row: AgentDefinition) -> AgentResponse:
    return AgentResponse(
        uid=row.uid,
        project_uid=row.project_uid,
        name=row.name,
        description=row.description or "",
        system_prompt=row.system_prompt or "",
        model=row.model,
        tools=json.loads(row.tools_json) if row.tools_json else [],
        skills=json.loads(row.skills_json) if row.skills_json else [],
        middleware=json.loads(row.middleware_json) if row.middleware_json else {},
        max_iterations=row.max_iterations or 25,
        temperature=float(row.temperature or 0),
        metadata=json.loads(row.metadata_json) if row.metadata_json else {},
        enabled=row.enabled if row.enabled is not None else True,
        created_by=row.created_by or "",
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/projects/{project_uid}/agents", response_model=AgentResponse, status_code=201)
async def create_agent(
    project_uid: str,
    req: AgentCreateRequest,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    agent = AgentDefinition(
        uid=str(uuid.uuid4()),
        project_uid=project_uid,
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        model=req.model,
        tools_json=json.dumps(req.tools),
        skills_json=json.dumps(req.skills),
        middleware_json=json.dumps(req.middleware),
        max_iterations=req.max_iterations,
        temperature=int(req.temperature * 100),
        metadata_json=json.dumps(req.metadata),
        created_by=principal.uid,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _to_response(agent)


@router.get("/projects/{project_uid}/agents", response_model=list[AgentResponse])
async def list_agents(
    project_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentDefinition)
        .where(AgentDefinition.project_uid == project_uid)
        .order_by(AgentDefinition.created_at.desc())
    )
    return [_to_response(r) for r in result.scalars().all()]


@router.get("/agents/{agent_uid}", response_model=AgentResponse)
async def get_agent(
    agent_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.uid == agent_uid)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _to_response(agent)


@router.put("/agents/{agent_uid}", response_model=AgentResponse)
async def update_agent(
    agent_uid: str,
    req: AgentUpdateRequest,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.uid == agent_uid)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if req.name is not None:
        agent.name = req.name
    if req.description is not None:
        agent.description = req.description
    if req.system_prompt is not None:
        agent.system_prompt = req.system_prompt
    if req.model is not None:
        agent.model = req.model
    if req.tools is not None:
        agent.tools_json = json.dumps(req.tools)
    if req.skills is not None:
        agent.skills_json = json.dumps(req.skills)
    if req.middleware is not None:
        agent.middleware_json = json.dumps(req.middleware)
    if req.max_iterations is not None:
        agent.max_iterations = req.max_iterations
    if req.temperature is not None:
        agent.temperature = int(req.temperature * 100)
    if req.metadata is not None:
        agent.metadata_json = json.dumps(req.metadata)
    if req.enabled is not None:
        agent.enabled = req.enabled

    await db.commit()
    await db.refresh(agent)
    return _to_response(agent)


@router.delete("/agents/{agent_uid}", status_code=204)
async def delete_agent(
    agent_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.uid == agent_uid)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()
