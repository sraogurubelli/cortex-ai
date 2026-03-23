"""
Skills Management API

CRUD endpoints for managing agent skills (upload, list, enable/disable,
attach to agents).
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["skills"])


# ---------------------------------------------------------------------------
# DB Models
# ---------------------------------------------------------------------------


class SkillRecord(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    skill_md_content = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    metadata_json = Column(Text, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentSkillLink(Base):
    """Many-to-many link between agents and skills."""
    __tablename__ = "agent_skill_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_uid = Column(String(255), nullable=False, index=True)
    skill_uid = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SkillCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    skill_md_content: str = Field(..., min_length=1)
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)


class SkillUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    skill_md_content: Optional[str] = None
    enabled: Optional[bool] = None
    metadata: Optional[dict] = None


class SkillResponse(BaseModel):
    uid: str
    name: str
    description: str
    skill_md_content: str
    enabled: bool
    metadata: dict
    created_by: str
    created_at: str
    updated_at: str


def _to_response(row: SkillRecord) -> SkillResponse:
    return SkillResponse(
        uid=row.uid,
        name=row.name,
        description=row.description or "",
        skill_md_content=row.skill_md_content or "",
        enabled=row.enabled if row.enabled is not None else True,
        metadata=json.loads(row.metadata_json) if row.metadata_json else {},
        created_by=row.created_by or "",
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/skills", response_model=SkillResponse, status_code=201)
async def create_skill(
    req: SkillCreateRequest,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    skill = SkillRecord(
        uid=str(uuid.uuid4()),
        name=req.name,
        description=req.description,
        skill_md_content=req.skill_md_content,
        enabled=req.enabled,
        metadata_json=json.dumps(req.metadata),
        created_by=principal.uid,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _to_response(skill)


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SkillRecord).order_by(SkillRecord.created_at.desc())
    )
    return [_to_response(r) for r in result.scalars().all()]


@router.get("/skills/{skill_uid}", response_model=SkillResponse)
async def get_skill(
    skill_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SkillRecord).where(SkillRecord.uid == skill_uid)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _to_response(skill)


@router.put("/skills/{skill_uid}", response_model=SkillResponse)
async def update_skill(
    skill_uid: str,
    req: SkillUpdateRequest,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SkillRecord).where(SkillRecord.uid == skill_uid)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    if req.name is not None:
        skill.name = req.name
    if req.description is not None:
        skill.description = req.description
    if req.skill_md_content is not None:
        skill.skill_md_content = req.skill_md_content
    if req.enabled is not None:
        skill.enabled = req.enabled
    if req.metadata is not None:
        skill.metadata_json = json.dumps(req.metadata)

    await db.commit()
    await db.refresh(skill)
    return _to_response(skill)


@router.delete("/skills/{skill_uid}", status_code=204)
async def delete_skill(
    skill_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SkillRecord).where(SkillRecord.uid == skill_uid)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Remove agent links
    await db.execute(
        select(AgentSkillLink).where(AgentSkillLink.skill_uid == skill_uid)
    )
    await db.delete(skill)
    await db.commit()


@router.post("/agents/{agent_uid}/skills/{skill_uid}", status_code=201)
async def attach_skill_to_agent(
    agent_uid: str,
    skill_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(AgentSkillLink)
        .where(AgentSkillLink.agent_uid == agent_uid)
        .where(AgentSkillLink.skill_uid == skill_uid)
    )
    if existing.scalar_one_or_none():
        return {"message": "Skill already attached"}

    link = AgentSkillLink(agent_uid=agent_uid, skill_uid=skill_uid)
    db.add(link)
    await db.commit()
    return {"message": "Skill attached", "agent_uid": agent_uid, "skill_uid": skill_uid}


@router.delete("/agents/{agent_uid}/skills/{skill_uid}", status_code=204)
async def detach_skill_from_agent(
    agent_uid: str,
    skill_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentSkillLink)
        .where(AgentSkillLink.agent_uid == agent_uid)
        .where(AgentSkillLink.skill_uid == skill_uid)
    )
    link = result.scalar_one_or_none()
    if link:
        await db.delete(link)
        await db.commit()


@router.get("/agents/{agent_uid}/skills", response_model=list[SkillResponse])
async def list_agent_skills(
    agent_uid: str,
    principal: Principal = Depends(require_authentication),
    db: AsyncSession = Depends(get_db),
):
    links = await db.execute(
        select(AgentSkillLink.skill_uid).where(AgentSkillLink.agent_uid == agent_uid)
    )
    skill_uids = [r[0] for r in links.all()]
    if not skill_uids:
        return []

    result = await db.execute(
        select(SkillRecord).where(SkillRecord.uid.in_(skill_uids))
    )
    return [_to_response(r) for r in result.scalars().all()]
