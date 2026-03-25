"""
API Key Management Routes

CRUD endpoints for Personal Access Tokens (PAT) and Service Account Tokens (SAT).
Uses the existing Token model and TokenRepository.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import Principal, Token, get_db
from cortex.platform.database.models import TokenType
from cortex.platform.database.repositories import TokenRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    """Create a new API key."""
    name: str = Field(..., min_length=1, max_length=255, description="Key name")
    token_type: str = Field(
        default="pat",
        description="Token type: pat (Personal Access Token) or sat (Service Account Token)",
    )
    scopes: Optional[list[str]] = Field(
        default=None, description="Permission scopes (null = inherit role permissions)"
    )
    expires_in_days: Optional[int] = Field(
        default=90, ge=1, le=365, description="Expiration in days (default 90)"
    )


class ApiKeyInfo(BaseModel):
    """API key information (never includes the raw key)."""
    id: str
    name: Optional[str]
    token_type: str
    scopes: Optional[list[str]]
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime


class ApiKeyCreated(BaseModel):
    """Response when a new API key is created (only time raw key is shown)."""
    id: str
    name: str
    token_type: str
    key: str
    expires_at: Optional[datetime]
    created_at: datetime


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateApiKeyRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Create a new API key.

    The raw key is returned ONLY in this response -- store it securely.
    """
    raw_key = f"ctx_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    token_type = TokenType.PAT if request.token_type == "pat" else TokenType.SAT

    import json
    scopes_json = json.dumps(request.scopes) if request.scopes else None

    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)

    token = Token(
        uid=f"tok_{uuid.uuid4().hex[:12]}",
        principal_id=principal.id,
        token_type=token_type,
        token_hash=key_hash,
        name=request.name,
        scopes=scopes_json,
        expires_at=expires_at,
    )

    token_repo = TokenRepository(session)
    token = await token_repo.create(token)
    await session.commit()

    return ApiKeyCreated(
        id=token.uid,
        name=token.name,
        token_type=request.token_type,
        key=raw_key,
        expires_at=token.expires_at,
        created_at=token.created_at,
    )


@router.get("/api-keys", response_model=list[ApiKeyInfo])
async def list_api_keys(
    token_type: Optional[str] = Query(None, description="Filter by type: pat or sat"),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """List all API keys for the authenticated principal."""
    token_repo = TokenRepository(session)

    type_filter = None
    if token_type == "pat":
        type_filter = TokenType.PAT
    elif token_type == "sat":
        type_filter = TokenType.SAT

    tokens = await token_repo.find_by_principal(principal.id, token_type=type_filter)

    import json
    return [
        ApiKeyInfo(
            id=t.uid,
            name=t.name,
            token_type=t.token_type.value if t.token_type else "unknown",
            scopes=json.loads(t.scopes) if t.scopes else None,
            last_used_at=t.last_used_at,
            expires_at=t.expires_at,
            created_at=t.created_at,
        )
        for t in tokens
        if t.token_type in (TokenType.PAT, TokenType.SAT)
    ]


@router.delete("/api-keys/{key_uid}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Revoke (delete) an API key."""
    token_repo = TokenRepository(session)
    token = await token_repo.find_by_uid(key_uid)

    if not token:
        raise HTTPException(status_code=404, detail="API key not found")

    if token.principal_id != principal.id and not principal.admin:
        raise HTTPException(status_code=403, detail="Cannot revoke another user's key")

    await token_repo.delete(token.id)
    await session.commit()
    return None


@router.post("/api-keys/{key_uid}/rotate", response_model=ApiKeyCreated)
async def rotate_api_key(
    key_uid: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """Rotate an API key: revokes the old one and creates a new one with the same config."""
    token_repo = TokenRepository(session)
    old_token = await token_repo.find_by_uid(key_uid)

    if not old_token:
        raise HTTPException(status_code=404, detail="API key not found")

    if old_token.principal_id != principal.id and not principal.admin:
        raise HTTPException(status_code=403, detail="Cannot rotate another user's key")

    raw_key = f"ctx_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    remaining_days = None
    if old_token.expires_at:
        remaining = old_token.expires_at - datetime.now(timezone.utc)
        remaining_days = max(1, remaining.days)

    new_token = Token(
        uid=f"tok_{uuid.uuid4().hex[:12]}",
        principal_id=principal.id,
        token_type=old_token.token_type,
        token_hash=key_hash,
        name=old_token.name,
        scopes=old_token.scopes,
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=remaining_days)
            if remaining_days
            else None
        ),
    )

    await token_repo.delete(old_token.id)
    new_token = await token_repo.create(new_token)
    await session.commit()

    return ApiKeyCreated(
        id=new_token.uid,
        name=new_token.name,
        token_type=new_token.token_type.value if new_token.token_type else "unknown",
        key=raw_key,
        expires_at=new_token.expires_at,
        created_at=new_token.created_at,
    )
