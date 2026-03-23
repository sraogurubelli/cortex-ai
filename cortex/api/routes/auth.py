"""
Authentication API Routes

Handles user signup, login, and token management.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import JWTHandler
from cortex.platform.config import get_settings
from cortex.platform.database import (
    Principal,
    PrincipalType,
    Account,
    AccountStatus,
    SubscriptionTier,
    Organization,
    Membership,
    Role,
    get_db,
)
from cortex.platform.database.repositories import (
    PrincipalRepository,
    AccountRepository,
    OrganizationRepository,
    MembershipRepository,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


# ============================================================================
# Request/Response Models
# ============================================================================


class SignupRequest(BaseModel):
    """Signup request."""

    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=255)
    account_name: str | None = Field(None, description="Account name (optional)")


class LoginRequest(BaseModel):
    """Login request."""

    email: EmailStr
    # Note: For MVP, we're using JWT tokens only
    # In production, add password field here


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserInfo(BaseModel):
    """Current user information."""

    id: str
    email: str
    display_name: str
    principal_type: str
    admin: bool
    blocked: bool
    created_at: datetime


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignupRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Sign up a new user.

    Creates:
    - Principal (user)
    - Account (with FREE tier, TRIAL status)
    - Default Organization
    - OWNER membership

    Returns JWT tokens.
    """
    settings = get_settings()
    principal_repo = PrincipalRepository(session)
    account_repo = AccountRepository(session)
    org_repo = OrganizationRepository(session)
    membership_repo = MembershipRepository(session)

    # Check if email already exists
    existing = await principal_repo.find_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create principal
    principal = Principal(
        uid=f"usr_{uuid.uuid4().hex[:12]}",
        email=request.email,
        display_name=request.display_name,
        principal_type=PrincipalType.USER,
        admin=request.email in settings.admin_emails,  # Bootstrap admins
        blocked=False,
    )
    principal = await principal_repo.create(principal)

    # Create account
    account_name = request.account_name or f"{request.display_name}'s Account"
    trial_ends_at = datetime.now() + timedelta(days=14)  # 14-day trial

    account = Account(
        uid=f"acc_{uuid.uuid4().hex[:12]}",
        name=account_name,
        billing_email=request.email,
        status=AccountStatus.TRIAL,
        subscription_tier=SubscriptionTier.FREE,
        owner_id=principal.id,
        trial_ends_at=trial_ends_at,
    )
    account = await account_repo.create(account)

    # Create default organization
    org = Organization(
        uid=f"org_{uuid.uuid4().hex[:12]}",
        account_id=account.id,
        name="Default Organization",
        owner_id=principal.id,
    )
    org = await org_repo.create(org)

    # Create OWNER membership for account
    account_membership = Membership(
        principal_id=principal.id,
        resource_type="account",
        resource_id=account.uid,
        role=Role.OWNER,
    )
    await membership_repo.create(account_membership)

    # Create OWNER membership for organization
    org_membership = Membership(
        principal_id=principal.id,
        resource_type="organization",
        resource_id=org.uid,
        role=Role.OWNER,
    )
    await membership_repo.create(org_membership)

    await session.commit()

    # Generate JWT tokens
    jwt_handler = JWTHandler(
        secrets=settings.jwt_secrets,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
    )

    access_token = jwt_handler.create_access_token(
        principal_id=principal.id,
        email=principal.email,
        admin=principal.admin,
    )

    refresh_token = jwt_handler.create_refresh_token(
        principal_id=principal.id,
        email=principal.email,
        admin=principal.admin,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Login existing user.

    For MVP: Just checks if user exists.
    In production: Add password verification.

    Returns JWT tokens.
    """
    settings = get_settings()
    principal_repo = PrincipalRepository(session)

    # Find user by email
    principal = await principal_repo.find_by_email(request.email)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if blocked
    if principal.blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    # Generate JWT tokens
    jwt_handler = JWTHandler(
        secrets=settings.jwt_secrets,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
    )

    access_token = jwt_handler.create_access_token(
        principal_id=principal.id,
        email=principal.email,
        admin=principal.admin,
    )

    refresh_token = jwt_handler.create_refresh_token(
        principal_id=principal.id,
        email=principal.email,
        admin=principal.admin,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Refresh an access token using a valid refresh token.

    Returns new access and refresh tokens.
    """
    settings = get_settings()

    jwt_handler = JWTHandler(
        secrets=settings.jwt_secrets,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
    )

    try:
        claims = jwt_handler.verify_token(request.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if claims.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    principal_repo = PrincipalRepository(session)
    principal = await principal_repo.find_by_id(claims.principal_id)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if principal.blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    access_token = jwt_handler.create_access_token(
        principal_id=principal.id,
        email=principal.email,
        admin=principal.admin,
    )

    new_refresh_token = jwt_handler.create_refresh_token(
        principal_id=principal.id,
        email=principal.email,
        admin=principal.admin,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    principal: Principal = Depends(require_authentication),
):
    """
    Logout the current user.

    For MVP, this is a no-op on the server side (client clears tokens).
    In production, add token deny-listing via Redis.
    """
    return None


@router.get("/me", response_model=UserInfo)
async def get_current_user(
    principal: Principal = Depends(require_authentication),
):
    """
    Get current authenticated user information.

    Requires valid JWT token.
    """
    return UserInfo(
        id=principal.uid,
        email=principal.email,
        display_name=principal.display_name,
        principal_type=principal.principal_type.value,
        admin=principal.admin,
        blocked=principal.blocked,
        created_at=principal.created_at,
    )
