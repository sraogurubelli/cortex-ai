"""
JWT Authentication Module

JWT-based authentication with multi-secret support for secret rotation.
Principal IDs are UUIDs serialized as strings in JWT claims.
"""

import time
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from pydantic import BaseModel


class TokenClaims(BaseModel):
    """JWT token claims."""

    sub: str
    exp: int
    iat: int
    token_type: str = "access"
    principal_id: str | None = None  # UUID serialized as string
    email: str | None = None
    admin: bool = False

    @property
    def principal_uuid(self) -> UUID | None:
        """Return principal_id as UUID object."""
        if self.principal_id:
            return UUID(self.principal_id)
        return None


class JWTHandler:
    """JWT token handler with multi-secret support for rotation."""

    def __init__(
        self,
        secrets: list[str],
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 30,
    ):
        if not secrets:
            raise ValueError("At least one JWT secret is required")
        self.secrets = secrets
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    def create_access_token(
        self,
        principal_id: UUID | str,
        email: str,
        admin: bool = False,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time())
        expires_at = now + (self.access_token_expire_minutes * 60)

        claims = {
            "sub": email,
            "exp": expires_at,
            "iat": now,
            "token_type": "access",
            "principal_id": str(principal_id),
            "email": email,
            "admin": admin,
        }
        if extra_claims:
            claims.update(extra_claims)
        return jwt.encode(claims, self.secrets[0], algorithm=self.algorithm)

    def create_refresh_token(
        self,
        principal_id: UUID | str,
        email: str,
        admin: bool = False,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time())
        expires_at = now + (self.refresh_token_expire_days * 24 * 60 * 60)

        claims = {
            "sub": email,
            "exp": expires_at,
            "iat": now,
            "token_type": "refresh",
            "principal_id": str(principal_id),
            "email": email,
            "admin": admin,
        }
        if extra_claims:
            claims.update(extra_claims)
        return jwt.encode(claims, self.secrets[0], algorithm=self.algorithm)

    def create_magic_link_token(
        self,
        email: str,
        expire_minutes: int = 30,
    ) -> str:
        """Create a short-lived token for magic link authentication."""
        now = int(time.time())
        expires_at = now + (expire_minutes * 60)
        claims = {
            "sub": email,
            "exp": expires_at,
            "iat": now,
            "token_type": "magic_link",
            "email": email,
        }
        return jwt.encode(claims, self.secrets[0], algorithm=self.algorithm)

    def verify_token(self, token: str) -> TokenClaims:
        """Verify and decode a JWT token, trying each secret for rotation support."""
        errors = []
        for secret in self.secrets:
            try:
                payload = jwt.decode(
                    token, secret, algorithms=[self.algorithm],
                    options={"verify_exp": True},
                )
                return TokenClaims(**payload)
            except jwt.ExpiredSignatureError:
                raise
            except jwt.InvalidTokenError as e:
                errors.append(str(e))
                continue

        raise jwt.InvalidTokenError(
            f"Token verification failed with all secrets. Errors: {', '.join(errors)}"
        )

    def extract_token_from_header(self, authorization: str | None) -> str | None:
        if not authorization:
            return None
        parts = authorization.split(" ", 1)
        if len(parts) != 2:
            return None
        scheme, credentials = parts
        if scheme.lower() == "bearer":
            return credentials
        if scheme.lower() == "basic":
            try:
                import base64
                decoded = base64.b64decode(credentials).decode("utf-8")
                username, _, _ = decoded.partition(":")
                return username if username else None
            except Exception:
                return None
        return None

    def is_token_expired(self, token: str) -> bool:
        try:
            payload = jwt.decode(
                token, options={"verify_signature": False, "verify_exp": False},
            )
            exp = payload.get("exp")
            if exp is None:
                return True
            return int(time.time()) >= exp
        except Exception:
            return True

    def get_token_expiry(self, token: str) -> datetime | None:
        try:
            payload = jwt.decode(
                token, options={"verify_signature": False, "verify_exp": False},
            )
            exp = payload.get("exp")
            if exp is None:
                return None
            return datetime.fromtimestamp(exp)
        except Exception:
            return None
