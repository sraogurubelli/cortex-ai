"""
JWT Authentication Module

JWT-based authentication with multi-salt support for secret rotation.
Adapted from harness-code/gitness/app/auth/authn/jwt.go
"""

import time
from datetime import datetime, timedelta
from typing import Any

import jwt
from pydantic import BaseModel


class TokenClaims(BaseModel):
    """JWT token claims."""

    sub: str  # Subject (principal ID or email)
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    token_type: str = "access"  # "access" or "refresh"
    principal_id: int | None = None
    email: str | None = None
    admin: bool = False


class JWTHandler:
    """
    JWT token handler with multi-salt support.

    Supports secret rotation by accepting multiple salts.
    Tokens signed with any of the salts will be valid.
    """

    def __init__(
        self,
        secrets: list[str],
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 30,
    ):
        """
        Initialize JWT handler.

        Args:
            secrets: List of JWT signing secrets (supports rotation)
            algorithm: JWT signing algorithm (default: HS256)
            access_token_expire_minutes: Access token expiration in minutes
            refresh_token_expire_days: Refresh token expiration in days
        """
        if not secrets:
            raise ValueError("At least one JWT secret is required")

        self.secrets = secrets
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    def create_access_token(
        self,
        principal_id: int,
        email: str,
        admin: bool = False,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """
        Create an access token.

        Args:
            principal_id: Principal ID
            email: User email
            admin: Is admin user
            extra_claims: Additional claims to include

        Returns:
            Encoded JWT token
        """
        now = int(time.time())
        expires_at = now + (self.access_token_expire_minutes * 60)

        claims = {
            "sub": email,
            "exp": expires_at,
            "iat": now,
            "token_type": "access",
            "principal_id": principal_id,
            "email": email,
            "admin": admin,
        }

        if extra_claims:
            claims.update(extra_claims)

        # Always use the first (newest) secret for signing
        return jwt.encode(claims, self.secrets[0], algorithm=self.algorithm)

    def create_refresh_token(
        self,
        principal_id: int,
        email: str,
        admin: bool = False,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a refresh token.

        Args:
            principal_id: Principal ID
            email: User email
            admin: Is admin user
            extra_claims: Additional claims to include

        Returns:
            Encoded JWT token
        """
        now = int(time.time())
        expires_at = now + (self.refresh_token_expire_days * 24 * 60 * 60)

        claims = {
            "sub": email,
            "exp": expires_at,
            "iat": now,
            "token_type": "refresh",
            "principal_id": principal_id,
            "email": email,
            "admin": admin,
        }

        if extra_claims:
            claims.update(extra_claims)

        # Always use the first (newest) secret for signing
        return jwt.encode(claims, self.secrets[0], algorithm=self.algorithm)

    def verify_token(self, token: str) -> TokenClaims:
        """
        Verify and decode a JWT token.

        Supports multi-salt verification for secret rotation.
        Tries each secret in order until one succeeds.

        Args:
            token: JWT token to verify

        Returns:
            TokenClaims if valid

        Raises:
            jwt.InvalidTokenError: If token is invalid with all secrets
            jwt.ExpiredSignatureError: If token is expired
        """
        errors = []

        # Try each secret in order (newest to oldest)
        for secret in self.secrets:
            try:
                payload = jwt.decode(
                    token,
                    secret,
                    algorithms=[self.algorithm],
                    options={"verify_exp": True},
                )
                return TokenClaims(**payload)
            except jwt.ExpiredSignatureError:
                # Token is expired - no need to try other secrets
                raise
            except jwt.InvalidTokenError as e:
                # Try next secret
                errors.append(str(e))
                continue

        # None of the secrets worked
        raise jwt.InvalidTokenError(
            f"Token verification failed with all secrets. Errors: {', '.join(errors)}"
        )

    def extract_token_from_header(self, authorization: str | None) -> str | None:
        """
        Extract token from Authorization header.

        Supports formats:
        - Bearer <token>
        - Basic <base64(token:)>

        Args:
            authorization: Authorization header value

        Returns:
            Extracted token or None
        """
        if not authorization:
            return None

        parts = authorization.split(" ", 1)
        if len(parts) != 2:
            return None

        scheme, credentials = parts

        if scheme.lower() == "bearer":
            return credentials

        if scheme.lower() == "basic":
            # Basic auth: base64(username:password)
            # For token auth, username is the token, password is empty
            try:
                import base64

                decoded = base64.b64decode(credentials).decode("utf-8")
                username, _, _ = decoded.partition(":")
                return username if username else None
            except Exception:
                return None

        return None

    def is_token_expired(self, token: str) -> bool:
        """
        Check if token is expired without full verification.

        Args:
            token: JWT token

        Returns:
            True if expired, False otherwise
        """
        try:
            # Decode without verification to check expiration
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
            )
            exp = payload.get("exp")
            if exp is None:
                return True

            return int(time.time()) >= exp
        except Exception:
            return True

    def get_token_expiry(self, token: str) -> datetime | None:
        """
        Get token expiration time without full verification.

        Args:
            token: JWT token

        Returns:
            Expiration datetime or None
        """
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
            )
            exp = payload.get("exp")
            if exp is None:
                return None

            return datetime.fromtimestamp(exp)
        except Exception:
            return None
