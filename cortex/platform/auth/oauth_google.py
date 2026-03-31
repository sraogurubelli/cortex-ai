"""Google OAuth authentication provider."""

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from cortex.platform.config import get_settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GoogleOAuthProvider:
    """Google OAuth 2.0 authentication provider (stateless, no session needed)."""

    def __init__(self):
        settings = get_settings()

        if not settings.google_oauth_enabled:
            raise ValueError("Google OAuth is not enabled")

        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri

    def get_authorization_url(self) -> str:
        """Build the Google OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Optional[dict]:
        """Exchange authorization code for tokens, then extract user info from ID token."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(GOOGLE_TOKEN_ENDPOINT, data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                })

            if resp.status_code != 200:
                logger.error(f"Google token exchange failed: {resp.status_code} {resp.text}")
                return None

            token_data = resp.json()
            id_token_str = token_data.get("id_token")
            if not id_token_str:
                logger.error("No id_token in Google token response")
                return None

            return self._extract_user_info(id_token_str)

        except Exception as e:
            logger.error(f"Google code exchange failed: {e}", exc_info=True)
            return None

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify a Google ID token directly (for clients that already have one)."""
        return self._extract_user_info(token)

    def _extract_user_info(self, id_token_str: str) -> Optional[dict]:
        try:
            id_info = id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                self.client_id,
            )

            if id_info["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
                logger.error(f"Invalid token issuer: {id_info['iss']}")
                return None

            return {
                "email": id_info["email"],
                "google_id": id_info["sub"],
                "name": id_info.get("name"),
                "picture": id_info.get("picture"),
                "email_verified": id_info.get("email_verified", False),
            }

        except Exception as e:
            logger.error(f"Failed to verify Google ID token: {e}", exc_info=True)
            return None
