"""
WebSocket Authentication

Extracts and verifies JWT tokens for WebSocket connections.

Token sources (in order):
1. Query parameter (?token=<token>)
2. Sec-WebSocket-Protocol header (for token passing)

Note: WebSocket connections can't set custom headers in browsers,
so we rely on query parameters for authentication.

Usage:
    from fastapi import WebSocket, Depends

    @app.websocket("/ws/chat/{conversation_id}")
    async def websocket_chat(
        websocket: WebSocket,
        principal: Principal = Depends(get_websocket_principal),
    ):
        if not principal:
            await websocket.close(code=1008, reason="Authentication required")
            return
        ...
"""

import logging
from typing import Optional

import jwt
from fastapi import WebSocket, status
from sqlalchemy import select

from cortex.platform.auth.jwt import JWTHandler, TokenClaims
from cortex.platform.config import get_settings
from cortex.platform.database import Principal, get_db_manager

logger = logging.getLogger(__name__)


class WebSocketAuthenticator:
    """
    Authenticator for WebSocket connections.

    Extracts and verifies JWT tokens from WebSocket connections.
    """

    def __init__(self, jwt_handler: Optional[JWTHandler] = None):
        """
        Initialize WebSocket authenticator.

        Args:
            jwt_handler: JWT handler instance (optional, will create from settings)
        """
        if jwt_handler is None:
            settings = get_settings()
            jwt_handler = JWTHandler(
                secrets=settings.jwt_secrets,
                algorithm=settings.jwt_algorithm,
                access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
                refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
            )

        self.jwt_handler = jwt_handler
        self.db_manager = get_db_manager()

    def _extract_token(self, websocket: WebSocket) -> Optional[str]:
        """
        Extract token from WebSocket connection.

        Checks in order:
        1. Query parameter (?token=<token>)
        2. Sec-WebSocket-Protocol header

        Args:
            websocket: WebSocket connection

        Returns:
            Token string or None
        """
        # 1. Query parameter (most common for WebSocket)
        token_param = websocket.query_params.get("token")
        if token_param:
            return token_param

        # 2. Sec-WebSocket-Protocol header (alternative method)
        # Some clients send token as subprotocol
        protocols = websocket.headers.get("sec-websocket-protocol", "")
        if protocols:
            # Format: "token, <jwt-token>"
            parts = [p.strip() for p in protocols.split(",")]
            if len(parts) == 2 and parts[0] == "token":
                return parts[1]

        return None

    async def authenticate(self, websocket: WebSocket) -> Optional[Principal]:
        """
        Authenticate WebSocket connection.

        Args:
            websocket: WebSocket connection

        Returns:
            Principal instance or None if authentication fails
        """
        # Extract token
        token = self._extract_token(websocket)
        if not token:
            logger.debug("No token found in WebSocket connection")
            return None

        try:
            # Verify token
            claims = self.jwt_handler.verify_token(token)

            # Load principal from database
            principal = await self._load_principal(claims)

            if principal:
                # Check if principal is blocked
                if principal.blocked:
                    logger.warning(f"Blocked principal attempted WebSocket connection: {principal.id}")
                    return None

                logger.info(f"WebSocket authenticated: principal_id={principal.id}")
                return principal
            else:
                logger.warning(f"Principal not found: {claims.principal_id}")
                return None

        except jwt.ExpiredSignatureError:
            logger.debug("WebSocket token expired")
            return None
        except jwt.InvalidTokenError:
            logger.debug("WebSocket token invalid")
            return None
        except Exception as e:
            logger.error(f"WebSocket authentication error: {e}", exc_info=True)
            return None

    async def _load_principal(self, claims: TokenClaims) -> Optional[Principal]:
        """
        Load principal from database based on token claims.

        Args:
            claims: Token claims

        Returns:
            Principal instance or None
        """
        if not claims.principal_id:
            return None

        async with self.db_manager.session() as session:
            result = await session.execute(
                select(Principal).where(Principal.id == claims.principal_id)
            )
            return result.scalar_one_or_none()


# ============================================================================
# Global Authenticator Instance
# ============================================================================

_authenticator: Optional[WebSocketAuthenticator] = None


def get_websocket_authenticator() -> WebSocketAuthenticator:
    """
    Get or create global WebSocket authenticator.

    Returns:
        WebSocketAuthenticator instance
    """
    global _authenticator
    if _authenticator is None:
        _authenticator = WebSocketAuthenticator()
    return _authenticator


async def get_websocket_principal(websocket: WebSocket) -> Optional[Principal]:
    """
    Get authenticated principal from WebSocket connection.

    FastAPI dependency for WebSocket endpoints.

    Usage:
        @app.websocket("/ws/chat/{conversation_id}")
        async def websocket_chat(
            websocket: WebSocket,
            principal: Principal = Depends(get_websocket_principal),
        ):
            if not principal:
                await websocket.close(code=1008, reason="Authentication required")
                return
            # principal is authenticated

    Args:
        websocket: WebSocket connection

    Returns:
        Principal instance or None if authentication fails
    """
    authenticator = get_websocket_authenticator()
    return await authenticator.authenticate(websocket)


async def require_websocket_authentication(websocket: WebSocket) -> Principal:
    """
    Require authentication for WebSocket endpoint.

    Closes connection with 1008 (Policy Violation) if not authenticated.

    Usage:
        @app.websocket("/ws/chat/{conversation_id}")
        async def websocket_chat(
            websocket: WebSocket,
            principal: Principal = Depends(require_websocket_authentication),
        ):
            # principal is guaranteed to be non-None here
            await websocket.accept()
            ...

    Args:
        websocket: WebSocket connection

    Returns:
        Principal instance

    Raises:
        Closes WebSocket connection if authentication fails
    """
    principal = await get_websocket_principal(websocket)

    if not principal:
        logger.warning("WebSocket connection rejected: authentication required")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        # FastAPI will raise an exception after close, which is expected
        # We just need to satisfy the type checker
        raise RuntimeError("Authentication required")

    return principal
