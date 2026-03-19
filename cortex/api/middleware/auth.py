"""
Authentication Middleware for FastAPI

Extracts and verifies JWT tokens from multiple sources:
- Authorization header (Bearer <token>)
- Basic auth (username=token)
- Query parameter (?token=<token>)
- Cookie (token=<token>)

Adapted from harness-code/gitness/app/auth/authn/jwt.go
"""

from typing import Optional

import jwt
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from sqlalchemy import select

from cortex.platform.auth.jwt import JWTHandler, TokenClaims
from cortex.platform.config import get_settings
from cortex.platform.database import Principal, get_db_manager


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and verify JWT tokens.

    Adds `request.state.principal` if authentication succeeds.
    """

    def __init__(self, app, jwt_handler: Optional[JWTHandler] = None):
        """
        Initialize auth middleware.

        Args:
            app: FastAPI application
            jwt_handler: JWT handler instance (optional, will create from settings)
        """
        super().__init__(app)

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

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Process request and extract authentication.

        Args:
            request: FastAPI request
            call_next: Next middleware

        Returns:
            Response
        """
        # Extract token from multiple sources
        token = self._extract_token(request)

        if token:
            try:
                # Verify token
                claims = self.jwt_handler.verify_token(token)

                # Load principal from database
                principal = await self._load_principal(claims)

                if principal:
                    # Check if principal is blocked
                    if principal.blocked:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Account is blocked",
                        )

                    # Attach principal to request state
                    request.state.principal = principal
                    request.state.token_claims = claims

            except jwt.ExpiredSignatureError:
                # Token expired - do not raise, just don't set principal
                # This allows endpoints to handle unauthenticated requests
                pass
            except jwt.InvalidTokenError:
                # Invalid token - do not raise, just don't set principal
                pass
            except Exception:
                # Other errors - do not raise, just don't set principal
                pass

        # Continue to next middleware
        response = await call_next(request)
        return response

    def _extract_token(self, request: Request) -> Optional[str]:
        """
        Extract token from request.

        Checks in order:
        1. Authorization header (Bearer <token>)
        2. Authorization header (Basic <base64(token:)>)
        3. Query parameter (?token=<token>)
        4. Cookie (token=<token>)

        Args:
            request: FastAPI request

        Returns:
            Token string or None
        """
        # 1. Authorization header
        authorization = request.headers.get("Authorization")
        if authorization:
            token = self.jwt_handler.extract_token_from_header(authorization)
            if token:
                return token

        # 2. Query parameter
        token_param = request.query_params.get("token")
        if token_param:
            return token_param

        # 3. Cookie
        token_cookie = request.cookies.get("token")
        if token_cookie:
            return token_cookie

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


def get_current_principal(request: Request) -> Optional[Principal]:
    """
    Get current authenticated principal from request.

    Usage:
        from fastapi import Depends

        @app.get("/protected")
        async def protected_endpoint(
            principal: Principal = Depends(get_current_principal)
        ):
            if not principal:
                raise HTTPException(403, "Authentication required")
            ...

    Args:
        request: FastAPI request

    Returns:
        Principal instance or None
    """
    return getattr(request.state, "principal", None)


def require_authentication(request: Request) -> Principal:
    """
    Require authentication for an endpoint.

    Raises 401 if not authenticated.

    Usage:
        from fastapi import Depends

        @app.get("/protected")
        async def protected_endpoint(
            principal: Principal = Depends(require_authentication)
        ):
            # principal is guaranteed to be non-None here
            ...

    Args:
        request: FastAPI request

    Returns:
        Principal instance

    Raises:
        HTTPException: 401 if not authenticated
    """
    principal = getattr(request.state, "principal", None)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_admin(request: Request) -> Principal:
    """
    Require admin authentication for an endpoint.

    Raises 401 if not authenticated, 403 if not admin.

    Usage:
        from fastapi import Depends

        @app.get("/admin")
        async def admin_endpoint(
            principal: Principal = Depends(require_admin)
        ):
            # principal is guaranteed to be admin here
            ...

    Args:
        request: FastAPI request

    Returns:
        Principal instance

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    principal = require_authentication(request)
    if not principal.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return principal
