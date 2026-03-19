"""
Unit tests for JWT authentication.

Tests multi-salt support, token creation/verification, and token extraction.
"""

import time
from datetime import datetime, timedelta

import jwt
import pytest

from cortex.platform.auth.jwt import JWTHandler, TokenClaims


class TestJWTHandler:
    """Test JWT handler functionality."""

    def test_create_access_token(self):
        """Test creating an access token."""
        handler = JWTHandler(secrets=["secret1"], access_token_expire_minutes=60)

        token = handler.create_access_token(
            principal_id=123,
            email="user@example.com",
            admin=False,
        )

        assert token is not None
        assert isinstance(token, str)

        # Verify token
        claims = handler.verify_token(token)
        assert claims.principal_id == 123
        assert claims.email == "user@example.com"
        assert claims.admin is False
        assert claims.token_type == "access"

    def test_create_refresh_token(self):
        """Test creating a refresh token."""
        handler = JWTHandler(secrets=["secret1"], refresh_token_expire_days=30)

        token = handler.create_refresh_token(
            principal_id=123,
            email="user@example.com",
            admin=False,
        )

        assert token is not None
        assert isinstance(token, str)

        # Verify token
        claims = handler.verify_token(token)
        assert claims.principal_id == 123
        assert claims.email == "user@example.com"
        assert claims.token_type == "refresh"

    def test_multi_salt_verification(self):
        """Test JWT verification with multiple salts (secret rotation)."""
        # Create handler with 3 salts
        handler = JWTHandler(
            secrets=["salt1", "salt2", "salt3"],
            access_token_expire_minutes=60,
        )

        # Create token (signed with first salt)
        token = handler.create_access_token(
            principal_id=123,
            email="user@example.com",
        )

        # Verify with all salts present
        claims = handler.verify_token(token)
        assert claims.principal_id == 123

        # Simulate rotation: remove old salt, add new salt
        handler.secrets = ["salt0", "salt1", "salt2"]  # salt3 removed, salt0 added

        # Old token should still verify (salt1 and salt2 still present)
        claims = handler.verify_token(token)
        assert claims.principal_id == 123

        # Remove all original salts
        handler.secrets = ["new_salt1", "new_salt2"]

        # Old token should fail to verify
        with pytest.raises(jwt.InvalidTokenError):
            handler.verify_token(token)

    def test_expired_token(self):
        """Test expired token verification."""
        handler = JWTHandler(secrets=["secret1"], access_token_expire_minutes=0)

        # Create token that expires immediately
        token = handler.create_access_token(
            principal_id=123,
            email="user@example.com",
        )

        # Wait a bit to ensure expiration
        time.sleep(1)

        # Verification should raise ExpiredSignatureError
        with pytest.raises(jwt.ExpiredSignatureError):
            handler.verify_token(token)

    def test_invalid_token(self):
        """Test invalid token verification."""
        handler = JWTHandler(secrets=["secret1"])

        # Invalid token format
        with pytest.raises(jwt.InvalidTokenError):
            handler.verify_token("invalid.token.format")

        # Token signed with different secret
        other_handler = JWTHandler(secrets=["different_secret"])
        token = other_handler.create_access_token(123, "user@example.com")

        with pytest.raises(jwt.InvalidTokenError):
            handler.verify_token(token)

    def test_extract_token_from_bearer_header(self):
        """Test token extraction from Bearer header."""
        handler = JWTHandler(secrets=["secret1"])

        # Valid Bearer token
        token = handler.extract_token_from_header("Bearer abc123xyz")
        assert token == "abc123xyz"

        # Case insensitive
        token = handler.extract_token_from_header("bearer abc123xyz")
        assert token == "abc123xyz"

    def test_extract_token_from_basic_header(self):
        """Test token extraction from Basic auth header."""
        handler = JWTHandler(secrets=["secret1"])

        # Basic auth: base64(token:)
        import base64

        credentials = base64.b64encode(b"mytoken:").decode("utf-8")
        token = handler.extract_token_from_header(f"Basic {credentials}")
        assert token == "mytoken"

    def test_extract_token_invalid_header(self):
        """Test token extraction from invalid headers."""
        handler = JWTHandler(secrets=["secret1"])

        # No space
        assert handler.extract_token_from_header("Bearertoken") is None

        # Empty header
        assert handler.extract_token_from_header("") is None
        assert handler.extract_token_from_header(None) is None

        # Unknown scheme
        assert handler.extract_token_from_header("Unknown token") is None

    def test_is_token_expired(self):
        """Test checking if token is expired."""
        handler = JWTHandler(secrets=["secret1"], access_token_expire_minutes=60)

        # Create valid token
        token = handler.create_access_token(123, "user@example.com")
        assert handler.is_token_expired(token) is False

        # Create expired token
        handler_expired = JWTHandler(secrets=["secret1"], access_token_expire_minutes=0)
        token_expired = handler_expired.create_access_token(123, "user@example.com")
        time.sleep(1)
        assert handler.is_token_expired(token_expired) is True

        # Invalid token
        assert handler.is_token_expired("invalid") is True

    def test_get_token_expiry(self):
        """Test getting token expiration time."""
        handler = JWTHandler(secrets=["secret1"], access_token_expire_minutes=60)

        token = handler.create_access_token(123, "user@example.com")
        expiry = handler.get_token_expiry(token)

        assert expiry is not None
        assert isinstance(expiry, datetime)

        # Expiry should be approximately 60 minutes from now
        expected = datetime.now() + timedelta(minutes=60)
        diff = abs((expiry - expected).total_seconds())
        assert diff < 5  # Within 5 seconds

        # Invalid token
        assert handler.get_token_expiry("invalid") is None

    def test_extra_claims(self):
        """Test adding extra claims to token."""
        handler = JWTHandler(secrets=["secret1"])

        token = handler.create_access_token(
            principal_id=123,
            email="user@example.com",
            extra_claims={"custom_field": "custom_value", "role": "admin"},
        )

        # Decode without verification to check claims
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["custom_field"] == "custom_value"
        assert payload["role"] == "admin"

    def test_no_secrets_raises_error(self):
        """Test that initializing without secrets raises error."""
        with pytest.raises(ValueError, match="At least one JWT secret is required"):
            JWTHandler(secrets=[])

    def test_token_claims_model(self):
        """Test TokenClaims pydantic model."""
        now = int(time.time())

        claims = TokenClaims(
            sub="user@example.com",
            exp=now + 3600,
            iat=now,
            token_type="access",
            principal_id=123,
            email="user@example.com",
            admin=True,
        )

        assert claims.sub == "user@example.com"
        assert claims.principal_id == 123
        assert claims.admin is True
        assert claims.token_type == "access"
