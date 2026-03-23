"""
Root conftest.py — shared fixtures for all cortex-ai tests.

Provides:
  - ``app``         : a FastAPI application backed by a file-based SQLite DB
  - ``client``      : an unauthenticated ``httpx.AsyncClient``
  - ``authed_client``: an ``httpx.AsyncClient`` whose requests are injected
                       with a valid principal via a pure-ASGI middleware
  - ``db_session``  : a raw ``AsyncSession`` for manual test data
  - ``auth_headers``: convenience dict ``{"Authorization": "Bearer …"}``

**Auth strategy**: ``BaseHTTPMiddleware`` does not reliably propagate
``request.state`` with ``httpx.ASGITransport``.  For ``authed_client``,
we wrap the app with a pure-ASGI middleware that injects a test principal
into ``scope["state"]``.  This makes both ``require_authentication`` and
``require_permission`` work transparently.
"""

import os
import tempfile
import uuid as _uuid

_test_db_dir = tempfile.mkdtemp(prefix="cortex_test_")
_test_db_path = os.path.join(_test_db_dir, "test.db")
_TEST_DB_URL = f"sqlite+aiosqlite:///{_test_db_path}"

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-testing-only-32b"
os.environ["JWT_SECRETS"] = '["test-jwt-secret-key-for-ci-32bytes!"]'
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["APP_ENV"] = "development"
os.environ["RBAC_ENABLED"] = "false"

import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from cortex.platform.database.models import Base
from cortex.platform.database import session as db_session_module


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _engine():
    engine = create_async_engine(_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
    try:
        os.unlink(_test_db_path)
        os.rmdir(_test_db_dir)
    except OSError:
        pass


@pytest_asyncio.fixture()
async def db_session(_engine):
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


class _TestDBManager:
    def __init__(self, engine):
        self.engine = engine
        self.session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    @asynccontextmanager
    async def session(self):
        async with self.session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def close(self):
        pass


@asynccontextmanager
async def _noop_lifespan(app):
    yield


# ---------------------------------------------------------------------------
# App + clients
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def app(_engine):
    """Build a FastAPI app with the test database."""
    test_mgr = _TestDBManager(_engine)
    db_session_module._db_manager = test_mgr

    from cortex.api.main import create_app

    test_app = create_app()
    test_app.router.lifespan_context = _noop_lifespan
    yield test_app
    db_session_module._db_manager = None


@pytest_asyncio.fixture()
async def client(app):
    """Unauthenticated test client — for signup, login, and public routes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Sign up a test user and return Bearer headers."""
    email = f"test_{_uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Test User"},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def authed_client(app, _engine):
    """Client whose requests are pre-authenticated via scope injection.

    Creates a real Principal row, then wraps the app with a pure-ASGI
    middleware that injects the principal into ``scope["state"]`` so
    that ``require_authentication`` / ``require_permission`` find it.
    """
    from cortex.platform.database import (
        Principal, PrincipalType, Account, AccountStatus,
        SubscriptionTier, Organization, Membership, Role,
    )

    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        principal = Principal(
            uid=f"usr_{_uuid.uuid4().hex[:12]}",
            email=f"authed_{_uuid.uuid4().hex[:8]}@test.com",
            display_name="Authed Test User",
            principal_type=PrincipalType.USER,
            admin=False,
            blocked=False,
        )
        session.add(principal)
        await session.flush()

        account = Account(
            uid=f"acc_{_uuid.uuid4().hex[:12]}",
            name="Test Account",
            billing_email=principal.email,
            status=AccountStatus.TRIAL,
            subscription_tier=SubscriptionTier.FREE,
            owner_id=principal.id,
        )
        session.add(account)
        await session.flush()

        org = Organization(
            uid=f"org_{_uuid.uuid4().hex[:12]}",
            account_id=account.id,
            name="Test Organization",
            owner_id=principal.id,
        )
        session.add(org)
        await session.flush()

        for resource_type, resource_id in [
            ("account", account.uid),
            ("organization", org.uid),
        ]:
            m = Membership(
                principal_id=principal.id,
                resource_type=resource_type,
                resource_id=resource_id,
                role=Role.OWNER,
            )
            session.add(m)

        await session.commit()
        await session.refresh(principal)

    class _InjectPrincipalMiddleware:
        """Pure ASGI middleware that injects a test principal."""

        def __init__(self, inner_app):
            self.app = inner_app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                if "state" not in scope:
                    scope["state"] = {}
                scope["state"]["principal"] = principal
            await self.app(scope, receive, send)

    wrapped = _InjectPrincipalMiddleware(app)
    transport = ASGITransport(app=wrapped)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
