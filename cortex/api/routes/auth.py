"""
Authentication API Routes

Handles user signup, login, Google OAuth, magic link, password reset, and token management.
All entity PKs are UUIDs.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from passlib.hash import bcrypt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import JWTHandler
from cortex.platform.auth.oauth_google import GoogleOAuthProvider
from cortex.platform.config import get_settings
from cortex.platform.database import (
    Principal,
    PrincipalType,
    User,
    Account,
    AccountStatus,
    SubscriptionTier,
    Organization,
    Membership,
    MembershipRole,
    get_db,
)
from cortex.platform.database.repositories import (
    PrincipalRepository,
    AccountRepository,
    OrganizationRepository,
    MembershipRepository,
    UserRepository,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_jwt_handler():
    settings = get_settings()
    return JWTHandler(
        secrets=settings.jwt_secrets,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
    )


def _issue_tokens(jwt_handler: JWTHandler, principal: Principal) -> dict:
    settings = get_settings()
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
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    }


def _company_name_from_email(email: str) -> str | None:
    domain = email.split("@")[1]
    common = {
        "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
        "icloud.com", "protonmail.com", "aol.com", "mail.com", "zoho.com",
    }
    if domain in common:
        return None
    return domain.split(".")[0].capitalize()


async def _provision_account_and_org(
    session: AsyncSession,
    principal: Principal,
    company_name: str | None = None,
    account_name: str | None = None,
):
    """Create Account + Organization + ADMIN Memberships for a new user."""
    account_repo = AccountRepository(session)
    org_repo = OrganizationRepository(session)
    membership_repo = MembershipRepository(session)

    display = principal.display_name or principal.email.split("@")[0]
    final_account_name = account_name or f"{display}'s Account"

    account = Account(
        name=final_account_name,
        billing_email=principal.email,
        status=AccountStatus.TRIAL,
        subscription_tier=SubscriptionTier.FREE,
        owner_id=principal.id,
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    account = await account_repo.create(account)

    comp = company_name or _company_name_from_email(principal.email)
    org_name = comp if comp else f"{display}'s Workspace"

    org = Organization(
        account_id=account.id,
        name=org_name,
        owner_id=principal.id,
    )
    org = await org_repo.create(org)

    await membership_repo.create(Membership(
        principal_id=principal.id,
        resource_type="account",
        resource_id=str(account.id),
        role=MembershipRole.ADMIN,
    ))
    await membership_repo.create(Membership(
        principal_id=principal.id,
        resource_type="organization",
        resource_id=str(org.id),
        role=MembershipRole.ADMIN,
    ))

    return account, org


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    company_name: str | None = Field(None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInfo(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    display_name: str | None = None
    principal_type: str
    admin: bool
    blocked: bool
    created_at: datetime


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(..., min_length=8, max_length=128)


class MagicLinkSendRequest(BaseModel):
    email: EmailStr


class MagicLinkVerifyRequest(BaseModel):
    token: str


class MagicLinkSignupRequest(BaseModel):
    token: str
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    company_name: str | None = Field(None, max_length=255)


# ---------------------------------------------------------------------------
# Signup / Login
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignupRequest,
    session: AsyncSession = Depends(get_db),
):
    """Email + password signup. Creates Principal, User, Account, Organization, Memberships."""
    settings = get_settings()
    principal_repo = PrincipalRepository(session)
    user_repo = UserRepository(session)

    existing = await principal_repo.find_by_email(request.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    display_name = f"{request.first_name} {request.last_name}".strip()

    principal = Principal(
        email=request.email,
        display_name=display_name,
        principal_type=PrincipalType.USER,
        admin=request.email in settings.admin_emails,
        blocked=False,
        auth_provider="jwt",
        email_verified=False,
    )
    principal = await principal_repo.create(principal)

    user = User(
        principal_id=principal.id,
        email=request.email,
        password_hash=bcrypt.hash(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        display_name=display_name,
        status="active",
        email_verified=False,
    )
    user = await user_repo.create(user)

    await _provision_account_and_org(
        session, principal, company_name=request.company_name,
    )

    await session.commit()

    jwt_handler = _get_jwt_handler()
    return _issue_tokens(jwt_handler, principal)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db),
):
    """Email + password login."""
    principal_repo = PrincipalRepository(session)
    user_repo = UserRepository(session)

    principal = await principal_repo.find_by_email(request.email)
    if not principal:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if principal.blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked")

    user = await user_repo.find_by_principal_id(principal.id)
    if not user or not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not bcrypt.verify(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    jwt_handler = _get_jwt_handler()
    return _issue_tokens(jwt_handler, principal)


# ---------------------------------------------------------------------------
# Token refresh / logout / me
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_db),
):
    jwt_handler = _get_jwt_handler()
    try:
        claims = jwt_handler.verify_token(request.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    if claims.token_type != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    principal_repo = PrincipalRepository(session)
    principal = await principal_repo.find_by_id(claims.principal_id)
    if not principal:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if principal.blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked")

    return _issue_tokens(jwt_handler, principal)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(principal: Principal = Depends(require_authentication)):
    return None


@router.get("/me", response_model=UserInfo)
async def get_current_user(
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(session)
    user = await user_repo.find_by_principal_id(principal.id)

    return UserInfo(
        id=str(principal.id),
        email=principal.email,
        first_name=user.first_name if user else "",
        last_name=user.last_name if user else "",
        display_name=user.display_name if user else principal.display_name,
        principal_type=principal.principal_type.value,
        admin=principal.admin,
        blocked=principal.blocked,
        created_at=principal.created_at,
    )


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

@router.get("/google/login")
async def google_login():
    settings = get_settings()
    if not settings.google_oauth_enabled:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google OAuth is not enabled")

    try:
        provider = GoogleOAuthProvider()
        auth_url = provider.get_authorization_url()
        return {"authorization_url": auth_url}
    except Exception as e:
        logger.error(f"Google OAuth init failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initialize Google OAuth")


@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    session: AsyncSession = Depends(get_db),
):
    """
    Google redirects here with ?code=. We exchange the code for tokens,
    create/find the user, then redirect the browser to the frontend with
    access_token and refresh_token as URL fragment params.
    """
    frontend_url = "http://localhost:5177"
    settings = get_settings()

    if not settings.google_oauth_enabled:
        return RedirectResponse(f"{frontend_url}/signin?error=google_oauth_disabled")

    try:
        provider = GoogleOAuthProvider()
        user_info = await provider.exchange_code(code)
        if not user_info:
            return RedirectResponse(f"{frontend_url}/signin?error=invalid_google_token")
        if not user_info.get("email_verified"):
            return RedirectResponse(f"{frontend_url}/signin?error=email_not_verified")

        principal_repo = PrincipalRepository(session)
        user_repo = UserRepository(session)
        principal = await principal_repo.find_by_email(user_info["email"])

        if not principal:
            logger.info(f"Creating new user from Google OAuth: {user_info['email']}")
            name = user_info.get("name", user_info["email"].split("@")[0])
            parts = name.split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

            principal = Principal(
                email=user_info["email"],
                display_name=name,
                principal_type=PrincipalType.USER,
                admin=user_info["email"] in settings.admin_emails,
                blocked=False,
                auth_provider="google",
                google_id=user_info["google_id"],
                picture_url=user_info.get("picture"),
                email_verified=True,
            )
            principal = await principal_repo.create(principal)

            user = User(
                principal_id=principal.id,
                email=user_info["email"],
                first_name=first_name,
                last_name=last_name,
                display_name=name,
                avatar_url=user_info.get("picture"),
                status="active",
                email_verified=True,
            )
            await user_repo.create(user)

            await _provision_account_and_org(session, principal)
            await session.commit()

        else:
            if not principal.google_id:
                principal.google_id = user_info["google_id"]
                principal.auth_provider = "google"
                principal.picture_url = user_info.get("picture")
                principal.email_verified = True
                await session.commit()

        if principal.blocked:
            return RedirectResponse(f"{frontend_url}/signin?error=account_blocked")

        jwt_handler = _get_jwt_handler()
        tokens = _issue_tokens(jwt_handler, principal)

        from urllib.parse import urlencode
        params = urlencode({
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
        })
        return RedirectResponse(f"{frontend_url}/auth/google/callback?{params}")

    except Exception as e:
        logger.error(f"Google OAuth callback failed: {e}", exc_info=True)
        return RedirectResponse(f"{frontend_url}/signin?error=auth_failed")


# ---------------------------------------------------------------------------
# Password Reset (simplified direct reset)
# ---------------------------------------------------------------------------

@router.post("/password-reset/direct", status_code=status.HTTP_200_OK)
async def password_reset_direct(
    request: PasswordResetRequest,
    session: AsyncSession = Depends(get_db),
):
    """Direct password reset (no email verification token yet)."""
    user_repo = UserRepository(session)
    user = await user_repo.find_by_email(request.email)
    if not user:
        return {"message": "If the email exists, the password has been reset."}

    user.password_hash = bcrypt.hash(request.new_password)
    await session.commit()
    return {"message": "If the email exists, the password has been reset."}


# ---------------------------------------------------------------------------
# Magic Link
# ---------------------------------------------------------------------------

@router.post("/magic-link/send", status_code=status.HTTP_200_OK)
async def magic_link_send(
    request: MagicLinkSendRequest,
    session: AsyncSession = Depends(get_db),
):
    """Generate a magic link token. In production this would be emailed."""
    jwt_handler = _get_jwt_handler()
    token = jwt_handler.create_magic_link_token(email=request.email)
    # In production: send token via email. For now return it directly.
    return {"token": token, "message": "Magic link generated (dev mode: token returned directly)"}


@router.post("/magic-link/verify")
async def magic_link_verify(
    request: MagicLinkVerifyRequest,
    session: AsyncSession = Depends(get_db),
):
    """Verify magic link token. Returns user info and whether the user already exists."""
    jwt_handler = _get_jwt_handler()
    try:
        claims = jwt_handler.verify_token(request.token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired magic link")

    if claims.token_type != "magic_link":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    principal_repo = PrincipalRepository(session)
    principal = await principal_repo.find_by_email(claims.email)

    if principal:
        if principal.blocked:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked")
        tokens = _issue_tokens(jwt_handler, principal)
        return {"exists": True, "email": claims.email, **tokens}

    return {"exists": False, "email": claims.email}


@router.post("/magic-link/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def magic_link_signup(
    request: MagicLinkSignupRequest,
    session: AsyncSession = Depends(get_db),
):
    """Complete signup for magic-link users (no password)."""
    jwt_handler = _get_jwt_handler()
    try:
        claims = jwt_handler.verify_token(request.token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired magic link")

    if claims.token_type != "magic_link":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    settings = get_settings()
    principal_repo = PrincipalRepository(session)
    user_repo = UserRepository(session)

    existing = await principal_repo.find_by_email(claims.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    display_name = f"{request.first_name} {request.last_name}".strip()

    principal = Principal(
        email=claims.email,
        display_name=display_name,
        principal_type=PrincipalType.USER,
        admin=claims.email in settings.admin_emails,
        blocked=False,
        auth_provider="magic_link",
        email_verified=True,
    )
    principal = await principal_repo.create(principal)

    user = User(
        principal_id=principal.id,
        email=claims.email,
        first_name=request.first_name,
        last_name=request.last_name,
        display_name=display_name,
        status="active",
        email_verified=True,
    )
    await user_repo.create(user)

    await _provision_account_and_org(session, principal, company_name=request.company_name)
    await session.commit()

    return _issue_tokens(jwt_handler, principal)
