"""
Integration tests for the Auth API.

Tests the full signup → login → refresh → me → logout flow.

Uses ``client`` (unauthenticated) for signup/login/refresh endpoints
and ``authed_client`` (dependency-override auth) for protected ones.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_creates_user(client: AsyncClient):
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": "alice@example.com", "display_name": "Alice"},
    )
    assert res.status_code == 201
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    email = "dup@example.com"
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "First"},
    )
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Second"},
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_login_existing_user(client: AsyncClient):
    email = "login_test@example.com"
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Login Test"},
    )
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_flow(client: AsyncClient):
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "refresh@example.com", "display_name": "Refresh"},
    )
    refresh_token = signup.json()["refresh_token"]

    res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "bad.token.here"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_info(authed_client: AsyncClient):
    """GET /me should return the authenticated user's info."""
    res = await authed_client.get("/api/v1/auth/me")
    assert res.status_code == 200
    body = res.json()
    assert "id" in body
    assert "email" in body
    assert body["principal_type"] == "user"


@pytest.mark.asyncio
async def test_me_without_auth(client: AsyncClient):
    res = await client.get("/api/v1/auth/me")
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_logout(authed_client: AsyncClient):
    res = await authed_client.post("/api/v1/auth/logout")
    assert res.status_code == 204
