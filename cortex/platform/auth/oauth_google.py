"""Google OAuth authentication provider."""

import logging
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from starlette.config import Config
from starlette.requests import Request

from cortex.platform.config import get_settings

logger = logging.getLogger(__name__)


class GoogleOAuthProvider:
    """Google OAuth 2.0 authentication provider."""

    def __init__(self):
        """Initialize Google OAuth provider."""
        settings = get_settings()

        if not settings.google_oauth_enabled:
            raise ValueError("Google OAuth is not enabled")

        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri

        # Initialize OAuth client
        config = Config(environ={
            "GOOGLE_CLIENT_ID": self.client_id,
            "GOOGLE_CLIENT_SECRET": self.client_secret,
        })

        self.oauth = OAuth(config)
        self.oauth.register(
            name="google",
            client_id=self.client_id,
            client_secret=self.client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid email profile",
            },
        )

    async def get_authorization_url(self, request: Request) -> str:
        """
        Get Google OAuth authorization URL.

        Args:
            request: Starlette request object

        Returns:
            Authorization URL to redirect user to
        """
        redirect_uri = self.redirect_uri
        return await self.oauth.google.authorize_redirect(request, redirect_uri)

    async def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify Google ID token and extract user info.

        Args:
            token: Google ID token (JWT)

        Returns:
            User info dict with keys: email, google_id, name, picture, email_verified
            None if verification fails
        """
        try:
            # Verify token with Google
            id_info = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                self.client_id,
            )

            # Verify issuer
            if id_info["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
                logger.error(f"Invalid token issuer: {id_info['iss']}")
                return None

            # Extract user info
            return {
                "email": id_info["email"],
                "google_id": id_info["sub"],
                "name": id_info.get("name"),
                "picture": id_info.get("picture"),
                "email_verified": id_info.get("email_verified", False),
            }

        except Exception as e:
            logger.error(f"Failed to verify Google token: {e}", exc_info=True)
            return None

    async def exchange_code_for_token(self, request: Request, code: str) -> Optional[dict]:
        """
        Exchange authorization code for access token.

        Args:
            request: Starlette request
            code: Authorization code from Google callback

        Returns:
            Token dict or None if exchange fails
        """
        try:
            token = await self.oauth.google.authorize_access_token(request)
            return token
        except Exception as e:
            logger.error(f"Failed to exchange code for token: {e}", exc_info=True)
            return None
