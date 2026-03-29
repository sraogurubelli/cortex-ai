"""
Account API Routes

CRUD operations for accounts with RBAC.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import (
    Principal,
    Account,
    AccountStatus,
    SubscriptionTier,
    get_db,
)
from cortex.platform.database.repositories import (
    AccountRepository,
    OrganizationRepository,
    MembershipRepository,
)

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


# ============================================================================
# Request/Response Models
# ============================================================================


class AccountInfo(BaseModel):
    """Account information response."""

    id: str
    name: str
    billing_email: str
    status: AccountStatus
    subscription_tier: SubscriptionTier
    owner_id: str
    trial_ends_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AccountList(BaseModel):
    """List of accounts."""

    accounts: list[AccountInfo]
    total: int


class UpdateAccountRequest(BaseModel):
    """Update account request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    billing_email: EmailStr | None = None


class OrganizationSummary(BaseModel):
    """Organization summary."""

    id: str
    name: str
    description: str | None
    created_at: datetime


class AccountOrganizations(BaseModel):
    """Account organizations list."""

    organizations: list[OrganizationSummary]
    total: int


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=AccountList)
async def list_accounts(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    List all accounts the current user has access to.

    Returns accounts where the user is a member.
    """
    account_repo = AccountRepository(session)
    membership_repo = MembershipRepository(session)

    # Get all account memberships for this principal
    memberships = await membership_repo.find_by_principal(
        principal_id=principal.id,
        resource_type="account",
    )

    # Get unique account IDs
    account_uids = {m.resource_id for m in memberships}

    # Fetch accounts
    accounts = []
    for uid in account_uids:
        account = await account_repo.find_by_uid(uid)
        if account:
            accounts.append(
                AccountInfo(
                    id=account.uid,
                    name=account.name,
                    billing_email=account.billing_email,
                    status=account.status,
                    subscription_tier=account.subscription_tier,
                    owner_id=str(account.owner_id),
                    trial_ends_at=account.trial_ends_at,
                    created_at=account.created_at,
                    updated_at=account.updated_at,
                )
            )

    # Apply pagination
    total = len(accounts)
    paginated = accounts[offset : offset + limit]

    return AccountList(accounts=paginated, total=total)


@router.get("/{uid}", response_model=AccountInfo)
async def get_account(
    uid: str,
    principal: Principal = Depends(require_permission(Permission.VIEW, "account")),
    session: AsyncSession = Depends(get_db),
):
    """
    Get account by ID.

    Requires ACCOUNT_VIEW permission.
    """
    account_repo = AccountRepository(session)
    account = await account_repo.find_by_uid(uid)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    return AccountInfo(
        id=account.uid,
        name=account.name,
        billing_email=account.billing_email,
        status=account.status,
        subscription_tier=account.subscription_tier,
        owner_id=str(account.owner_id),
        trial_ends_at=account.trial_ends_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.patch("/{uid}", response_model=AccountInfo)
async def update_account(
    uid: str,
    request: UpdateAccountRequest,
    principal: Principal = Depends(require_permission(Permission.EDIT, "account")),
    session: AsyncSession = Depends(get_db),
):
    """
    Update account settings.

    Requires ACCOUNT_EDIT permission.
    """
    account_repo = AccountRepository(session)
    account = await account_repo.find_by_uid(uid)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Update fields
    if request.name is not None:
        account.name = request.name

    if request.billing_email is not None:
        account.billing_email = request.billing_email

    # Save changes
    account = await account_repo.update(account)
    await session.commit()

    return AccountInfo(
        id=account.uid,
        name=account.name,
        billing_email=account.billing_email,
        status=account.status,
        subscription_tier=account.subscription_tier,
        owner_id=str(account.owner_id),
        trial_ends_at=account.trial_ends_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("/{uid}/organizations", response_model=AccountOrganizations)
async def list_account_organizations(
    uid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_permission(Permission.VIEW, "account")),
    session: AsyncSession = Depends(get_db),
):
    """
    List organizations in an account.

    Requires ACCOUNT_VIEW permission.
    """
    account_repo = AccountRepository(session)
    org_repo = OrganizationRepository(session)

    # Verify account exists
    account = await account_repo.find_by_uid(uid)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Get organizations
    orgs = await org_repo.find_by_account(
        account_id=account.id,
        limit=limit,
        offset=offset,
    )

    org_summaries = [
        OrganizationSummary(
            id=org.uid,
            name=org.name,
            description=org.description,
            created_at=org.created_at,
        )
        for org in orgs
    ]

    return AccountOrganizations(
        organizations=org_summaries,
        total=len(org_summaries),
    )
